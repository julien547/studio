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

from .geometry import distance, wall
from .wall_module import CLASSES, reconstruct_mask

SIMPLIFY_FRACTION = .0025   # tolérance de simplification d'une chaîne, en fraction du grand côté de la page
MIN_CHAIN_FRACTION = .012   # une chaîne plus courte (poussière, éperon du squelette) n'est pas proposée
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
    if report is not None:
        report.update(skeleton_segments=len(result['walls']), proposed=len(walls), dropped_chains=dropped)
    if not walls:
        return None, None, 'aucun mur après reconstruction'
    return walls, model_sha, None
