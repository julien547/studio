"""Murs proposés par un modèle de segmentation entraîné, appelé via le travailleur ONNX isolé (segmentation/run_onnx.py).

INACTIF tant que DOEMO_WALLS_MODEL_DIR n'est pas défini : le comportement du moteur est alors strictement celui d'avant.
Le travailleur tourne dans SON venv (onnxruntime) ; rien n'est installé dans l'environnement du service. Il refuse tout modèle dont
les droits (code, poids, données) ou l'empreinte ne sont pas validés dans manifest.json. Toute défaillance (droits, empreinte, délai,
masque inondé ou vide, refus du moteur de géométrie) renvoie une RAISON lisible et le moteur retombe sur ses propositions géométriques :
jamais de silence, jamais d'exception vers la page.

Configuration (variables d'environnement) :
  DOEMO_WALLS_MODEL_DIR   dossier contenant walls.onnx et manifest.json (obligatoire pour activer)
  DOEMO_WALLS_PYTHON      python du venv qui a onnxruntime (obligatoire)
  DOEMO_WALLS_WORKER      chemin de run_onnx.py (défaut : segmentation/run_onnx.py de cette version)
  DOEMO_WALLS_MODE        'replace' (défaut : le modèle remplace les propositions raster) ou 'add' (les deux, superposés)
  DOEMO_WALLS_TIMEOUT     secondes (défaut 120)
"""
import os
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
from collections import defaultdict

from .geometry import distance, merge_collinear_fragments, wall
from .wall_module import CLASSES, reconstruct_mask

UPRIGHT_ANGLE = .5          # degrés : en dessous, le plan est considéré droit (inclinaison de scan négligeable)
STRAIGHT_ANGLE = 15.        # degrés : un mur à moins de 15° de l'horizontale/verticale du plan est redressé
ALIGN_FRACTION = .004       # des murs parallèles à moins de 0,4 % de la page partagent la même ordonnée/abscisse
MIN_OBLIQUE_FRACTION = .025  # un mur oblique plus court est un crochet (arc de porte, marche d'escalier), pas un mur
CORNER_FRACTION = .015      # une extrémité à moins de 1,5 % d'un mur perpendiculaire vient s'y appuyer (coin / T)
SIMPLIFY_FRACTION = .0025   # tolérance de simplification d'une chaîne, en fraction du grand côté de la page
MIN_CHAIN_FRACTION = .012   # une chaîne plus courte (poussière, éperon du squelette) n'est pas proposée
MERGE_GAP_FRACTION = .006   # même écart maximal que le nettoyage des scans : une porte n'est jamais comblée
FLOOD = .5       # plus de 50 % de pixels « mur » : masque inondé, pas une segmentation
EMPTY = .0005    # moins de 0,05 % : le modèle ne voit rien


def configured():
    return bool(os.environ.get('DOEMO_WALLS_MODEL_DIR'))


def mode():
    return 'add' if os.environ.get('DOEMO_WALLS_MODE') == 'add' else 'replace'


def _worker():
    return Path(os.environ.get('DOEMO_WALLS_WORKER') or Path(__file__).resolve().parents[1] / 'segmentation' / 'run_onnx.py')


def simplify_chains(walls, epsilon, min_length):
    """Le squelette d'un masque est découpé en micro-segments de 1 pixel : chaque marche d'escalier devient un « mur » à valider.

    On rassemble les segments successifs d'une même chaîne en polyligne, on simplifie (Douglas-Peucker, `epsilon` en unités de page)
    et on écarte les chaînes plus courtes que `min_length`. L'épaisseur est la moyenne pondérée par la longueur, la nature
    (mur/cloison) la majorité ; la preuve du premier segment est conservée avec la simplification appliquée.
    Retourne (murs, nombre de chaînes écartées)."""
    chains = defaultdict(list)
    for w in walls:
        chains[w['evidence'][0]['chain']].append(w)
    out, dropped = [], 0
    for items in chains.values():
        items.sort(key=lambda w: w['evidence'][0]['segment'])
        runs = [[items[0]]]
        for w in items[1:]:
            runs[-1].append(w) if distance(runs[-1][-1]['b'], w['a']) < 1e-6 else runs.append([w])
        for run in runs:
            if sum(distance(w['a'], w['b']) for w in run) < min_length:
                dropped += 1
                continue
            points = [run[0]['a']] + [w['b'] for w in run]
            kept = cv2.approxPolyDP(np.array(points, np.float32).reshape(-1, 1, 2), epsilon, False).reshape(-1, 2)
            # indices des sommets conservés dans la polyligne d'origine (ils en sont un sous-ensemble ordonné)
            index, cursor = [], 0
            for vertex in kept:
                while cursor < len(points) - 1 and not np.allclose(np.array(points[cursor], np.float32), vertex):
                    cursor += 1
                index.append(cursor)
                cursor += 1 if cursor < len(points) - 1 else 0
            for first, last in zip(index, index[1:]):
                members = run[first:last] or [run[min(first, len(run) - 1)]]
                weight = [distance(m['a'], m['b']) for m in members]
                thick = [(m['thickness'], g) for m, g in zip(members, weight) if m['thickness'] is not None]
                a, b = points[first], points[last]
                if distance(a, b) < 1e-6:
                    continue
                w = wall(a, b, sum(t * g for t, g in thick) / sum(g for _, g in thick) if thick else None,
                         method=members[0]['method'], confidence=0.,
                         evidence=[{**members[0]['evidence'][0], 'simplified_from_segments': len(members), 'epsilon': epsilon}])
                w['kind'] = 'partition' if sum(g for m, g in zip(members, weight) if m.get('kind') == 'partition') > sum(weight) / 2 else 'wall'
                out.append(w)
    return out, dropped


def dominant_angle(walls):
    """Orientation principale du plan (degrés, dans [-45, 45[) : pic de l'histogramme des directions modulo 90°, pondéré par la longueur,
    affiné par la moyenne pondérée des murs à moins de 4° du pic (sinon un plan parfaitement droit serait donné à 0,5°)."""
    angles, lengths = [], []
    for w in walls:
        a = np.degrees(np.arctan2(w['b'][1] - w['a'][1], w['b'][0] - w['a'][0]))
        angles.append((a + 45) % 90 - 45)
        lengths.append(distance(w['a'], w['b']))
    angles, lengths = np.array(angles), np.array(lengths)
    histogram = np.zeros(90)
    for a, l in zip(angles, lengths):
        histogram[min(89, int(a + 45))] += l
    smooth = np.convolve(np.r_[histogram[-2:], histogram, histogram[:2]], np.ones(5) / 5, mode='valid')
    peak = float(np.argmax(smooth)) - 45 + .5
    distance_to_peak = (angles - peak + 45) % 90 - 45
    near = np.abs(distance_to_peak) <= 4
    return float(peak + np.average(distance_to_peak[near], weights=lengths[near])) if near.any() else peak


def _cluster(values, weights, tolerance):
    """Regroupe des valeurs 1D à moins de `tolerance` les unes des autres ; renvoie la valeur moyenne pondérée de chaque valeur d'entrée."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out, group = [0.] * len(values), [order[0]] if order else []
    def close(g):
        mean = sum(values[i] * weights[i] for i in g) / sum(weights[i] for i in g)
        for i in g:
            out[i] = mean
    for i in order[1:]:
        if values[i] - values[group[-1]] <= tolerance:
            group.append(i)
        else:
            close(group)
            group = [i]
    if group:
        close(group)
    return out


def straighten_walls(walls, width, height):
    """Murs du modèle -> murs DROITS : le squelette d'un masque est irrégulier (pentes de 1-3°, petits crochets, coins ouverts).

    1. orientation principale du plan ; 2. tout mur à moins de STRAIGHT_ANGLE de cet axe ou de sa perpendiculaire devient exactement
    parallèle à l'axe ; 3. les murs parallèles proches partagent la même ordonnée/abscisse ; 4. les extrémités proches d'un mur
    perpendiculaire viennent s'y appuyer (coins et T). Les murs obliques (réellement obliques) ne sont pas modifiés ; aucun trou n'est comblé
    entre deux murs alignés (c'est merge_collinear_fragments, avec son propre écart maximal, qui les rassemble).
    Les petits obliques (< MIN_OBLIQUE_FRACTION de la page) sont écartés.
    Retourne (murs, angle principal)."""
    if not walls:
        return walls, 0.
    span = max(width, height)
    angle = dominant_angle(walls)
    theta = np.radians(0. if abs(angle) < UPRIGHT_ANGLE else angle)     # plan droit à moins de 0,5° près : axes exacts de l'image
    c, s = np.cos(theta), np.sin(theta)
    to_frame = lambda p: (p[0] * c + p[1] * s, -p[0] * s + p[1] * c)
    from_frame = lambda u, v: [u * c - v * s, u * s + v * c]
    items = []
    for w in walls:
        (u0, v0), (u1, v1) = to_frame(w['a']), to_frame(w['b'])
        angle = np.degrees(np.arctan2(v1 - v0, u1 - u0)) % 180
        kind = 'h' if min(angle, 180 - angle) <= STRAIGHT_ANGLE else ('v' if abs(angle - 90) <= STRAIGHT_ANGLE else 'o')
        items.append({'w': w, 'kind': kind, 'u': [u0, u1], 'v': [v0, v1], 'length': distance(w['a'], w['b'])})
    for orientation, along, across in (('h', 'u', 'v'), ('v', 'v', 'u')):
        group = [it for it in items if it['kind'] == orientation]
        if not group:
            continue
        levels = [sum(it[across]) / 2 for it in group]
        levels = _cluster(levels, [it['length'] for it in group], ALIGN_FRACTION * span)
        for it, level in zip(group, levels):
            it[across] = [level, level]
            it[along] = sorted(it[along])
    tolerance = CORNER_FRACTION * span
    horizontals = [it for it in items if it['kind'] == 'h']
    verticals = [it for it in items if it['kind'] == 'v']
    def snap(ends_owner, others, along, across):
        for it in ends_owner:
            for end in (0, 1):
                best = None
                for o in others:
                    gap = abs(it[along][end] - o[along][0])
                    inside = min(o[across]) - tolerance <= it[across][0] <= max(o[across]) + tolerance
                    if gap <= tolerance and inside and (best is None or gap < best[0]):
                        best = (gap, o[along][0])
                if best:
                    it[along][end] = best[1]
    snap(horizontals, verticals, 'u', 'v')      # extrémités gauche/droite d'un mur horizontal -> abscisse d'un mur vertical
    snap(verticals, horizontals, 'v', 'u')      # extrémités haute/basse d'un mur vertical -> ordonnée d'un mur horizontal
    out = []
    for it in items:
        w = it['w']
        if it['kind'] == 'o' and it['length'] < MIN_OBLIQUE_FRACTION * span:
            continue
        a, b = (from_frame(it['u'][0], it['v'][0]), from_frame(it['u'][1], it['v'][1])) if it['kind'] != 'o' else (w['a'], w['b'])
        a = [min(max(a[0], 0.), float(width)), min(max(a[1], 0.), float(height))]
        b = [min(max(b[0], 0.), float(width)), min(max(b[1], 0.), float(height))]
        if distance(a, b) < 1e-6:
            continue
        straight = wall(a, b, w['thickness'], method=w['method'], confidence=0.,
                        evidence=[{**w['evidence'][0], 'straightened': it['kind'] != 'o'}] + list(w['evidence'][1:]))
        straight['kind'] = w.get('kind', 'wall')
        out.append(straight)
    return out, float(np.degrees(theta))


def propose(image, width, height, source_sha256, text_boxes=(), report=None):
    """image : PIL.Image de la page rendue ; width/height : taille du document (unités de la page).

    Retourne (murs, empreinte_du_modèle, None) ou (None, None, raison)."""
    directory = Path(os.environ['DOEMO_WALLS_MODEL_DIR'])
    python = os.environ.get('DOEMO_WALLS_PYTHON')
    model, manifest, worker = directory / 'walls.onnx', directory / 'manifest.json', _worker()
    if not python or not Path(python).is_file():
        return None, None, 'DOEMO_WALLS_PYTHON absent ou introuvable'
    for path in (model, manifest, worker):
        if not path.is_file():
            return None, None, 'fichier manquant : ' + path.name
    try:
        timeout = float(os.environ.get('DOEMO_WALLS_TIMEOUT', '120'))
    except ValueError:
        timeout = 120.
    with tempfile.TemporaryDirectory(prefix='walls_') as tmp:
        png, out = Path(tmp) / 'page.png', Path(tmp) / 'labels.npz'
        image.convert('RGB').save(png)
        try:
            run = subprocess.run([python, str(worker), str(model), str(manifest), str(png), str(out)],
                                 capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, None, f'délai dépassé ({timeout:g} s)'
        except OSError as error:
            return None, None, 'lancement impossible : ' + str(error)[:120]
        if run.returncode != 0:
            lines = [line.strip() for line in run.stderr.splitlines() if line.strip()]
            return None, None, (lines[-1] if lines else 'échec du travailleur ONNX')[:200]
        try:
            with np.load(out, allow_pickle=False) as data:
                labels, model_sha = data['labels'], str(data['model_sha256'])
        except (OSError, KeyError, ValueError):
            return None, None, 'sortie du travailleur illisible'
    if labels.shape != (image.height, image.width) or len(model_sha) != 64:
        return None, None, 'sortie du modèle incohérente'
    wall_share = float((labels == 1).mean())
    if wall_share > FLOOD:
        return None, None, f'masque inondé ({wall_share:.0%} de pixels « mur »)'
    if wall_share < EMPTY:
        return None, None, 'le modèle ne détecte aucun mur'
    polygons = []
    for text in text_boxes:
        x0, y0, x1, y1 = text['bbox']
        sx, sy = image.width / width, image.height / height
        polygons.append([(x0 * sx, y0 * sy), (x1 * sx, y0 * sy), (x1 * sx, y1 * sy), (x0 * sx, y1 * sy)])
    try:
        result = reconstruct_mask(labels, classes=CLASSES, source_sha256=source_sha256, model_sha256=model_sha,
                                  document_size=(width, height),
                                  image_to_document=[width / image.width, 0, 0, height / image.height, 0, 0],
                                  text_polygons=polygons)
    except (ValueError, OverflowError) as error:
        return None, None, 'géométrie refusée : ' + str(error)[:120]
    span = max(width, height)
    walls, dropped = simplify_chains(result['walls'], SIMPLIFY_FRACTION * span, MIN_CHAIN_FRACTION * span)
    skeleton_walls = len(walls)
    if walls:
        walls, axis = straighten_walls(walls, width, height)
        walls, _ = merge_collinear_fragments(walls, ALIGN_FRACTION * span, 1.5 * MERGE_GAP_FRACTION * span, bounds=(width, height),
                                             methods=('architectural_mask_medial_axis',))
    if report is not None:
        report.update(skeleton_segments=len(result['walls']), proposed=len(walls), dropped_chains=dropped, after_simplification=skeleton_walls)
    if not walls:
        return None, None, 'aucun mur après reconstruction'
    return walls, model_sha, None
