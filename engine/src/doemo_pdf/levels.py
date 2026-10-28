"""Closed vector selections. Source drawing streams are never rewritten."""
import copy
import hashlib
import json
import math
from pathlib import Path
import re

import pathops
import pikepdf

from .pdf import open_pdf, file_hash, resources_fingerprint, copy_optional_content

MAX_JSON = 4 * 1024 * 1024
WARNING = 'Des murs, textes ou pictogrammes traversant le contour peuvent être partiellement masqués. Contrôle visuel obligatoire.'


def source_descriptor(source):
    digest = file_hash(source)
    with open_pdf(source) as pdf:
        pages = [{'page': i+1, 'media_box': list(map(float, p.mediabox)),
                  'crop_box': list(map(float, p.cropbox)),
                  'rotation': int(p.obj.get('/Rotate', 0)) % 360,
                  'user_unit': float(p.obj.get('/UserUnit', 1))}
                 for i, p in enumerate(pdf.pages)]
    if file_hash(source) != digest:
        raise ValueError('Le BAT a changé pendant sa lecture.')
    return {'sha256': digest, 'pages': pages}


def new_document(source):
    return {'schema_version': 1, 'revision': 0, 'source': source_descriptor(source),
            'levels': [], 'markers': [], 'review_acknowledged': False}


def read_document(path):
    if Path(path).stat().st_size > MAX_JSON:
        raise ValueError('Sélections trop volumineuses (4 Mio maximum).')
    return json.loads(Path(path).read_text(encoding='utf-8'))


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e7:
        raise ValueError('Coordonnée invalide.')
    return float(value)


def point(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('Point PDF invalide.')
    return [number(x) for x in value]


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value):
        raise ValueError('Identifiant de sélection invalide.')
    return value


def contour_path(contour):
    path = pathops.Path()
    path.fillType = pathops.FillType.EVEN_ODD if contour['fill_rule'] == 'evenodd' else pathops.FillType.WINDING
    nodes = contour['nodes']
    path.moveTo(nodes[0]['x'], nodes[0]['y'])
    for a, b in zip(nodes, nodes[1:] + nodes[:1]):
        if a.get('out') is not None or b.get('in') is not None:
            path.cubicTo(*(a.get('out') or [a['x'], a['y']]),
                         *(b.get('in') or [b['x'], b['y']]), b['x'], b['y'])
        else:
            path.lineTo(b['x'], b['y'])
    path.close()
    return path


def level_path(level):
    """Union of all additions, minus the union of exclusions, never XOR overlap."""
    result = pathops.Path()
    for contour in level['contours']:
        if contour['role'] == 'include':
            result = pathops.op(result, contour_path(contour), pathops.PathOp.UNION)
    for contour in level['contours']:
        if contour['role'] == 'exclude':
            result = pathops.op(result, contour_path(contour), pathops.PathOp.DIFFERENCE)
    return result


def validate_document(source, document):
    if not isinstance(document, dict) or document.get('schema_version') != 1:
        raise ValueError('Version de sélections non prise en charge.')
    actual = source_descriptor(source)
    if document.get('source') != actual:
        raise ValueError('BAT incompatible : empreinte, pages ou repère PDF différents. Les zones ne sont pas réutilisées.')
    levels = document.get('levels')
    markers = document.get('markers', [])
    if not isinstance(levels, list) or len(levels) > 200 or not isinstance(markers, list) or len(markers) > 2000:
        raise ValueError('Liste de niveaux ou de VEI invalide.')
    doc = copy.deepcopy(document)
    doc['source'] = actual
    ids, assigned, marker_ids = set(), set(), set()
    total_nodes = 0
    def unique(value):
        value = identifier(value)
        if value in ids: raise ValueError('Identifiants de contours/niveaux dupliqués.')
        ids.add(value)
    for marker in markers:
        if not isinstance(marker, dict): raise ValueError('VEI invalide.')
        key = identifier(marker.get('id'))
        if key in marker_ids: raise ValueError('VEI dupliqué.')
        marker_ids.add(key)
        if type(marker.get('page')) is not int or not 1 <= marker['page'] <= len(actual['pages']):
            raise ValueError('Page de VEI invalide.')
        if marker.get('point') is not None: point(marker['point'])
    markers_by_id = {m['id']: m for m in markers}
    reports = []
    for level in doc['levels']:
        if not isinstance(level, dict): raise ValueError('Niveau invalide.')
        unique(level.get('id'))
        if not isinstance(level.get('name'), str) or not level['name'].strip() or len(level['name']) > 120:
            raise ValueError('Nom de niveau requis (120 caractères maximum).')
        if type(level.get('page')) is not int or not 1 <= level['page'] <= len(actual['pages']):
            raise ValueError('Page de niveau invalide.')
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(level.get('color', ''))):
            raise ValueError('Couleur de niveau invalide.')
        contours = level.get('contours')
        if not isinstance(contours, list) or len(contours) > 100:
            raise ValueError('Liste de contours invalide.')
        for contour in contours:
            if not isinstance(contour, dict): raise ValueError('Contour invalide.')
            unique(contour.get('id'))
            if contour.get('role') not in ('include', 'exclude') or contour.get('fill_rule') not in ('nonzero', 'evenodd'):
                raise ValueError('Rôle ou règle de remplissage invalide.')
            nodes = contour.get('nodes')
            if not isinstance(nodes, list) or not 3 <= len(nodes) <= 5000:
                raise ValueError('Un contour fermé requiert entre 3 et 5000 sommets.')
            total_nodes += len(nodes)
            if total_nodes > 20000: raise ValueError('Trop de sommets dans le projet.')
            for node in nodes:
                if not isinstance(node, dict): raise ValueError('Sommet invalide.')
                number(node.get('x')); number(node.get('y'))
                for handle in ('in', 'out'):
                    if node.get(handle) is not None: point(node[handle])
        vei_ids = level.get('vei_ids', [])
        if not isinstance(vei_ids, list): raise ValueError('Associations VEI invalides.')
        for key in vei_ids:
            identifier(key)
            if key in assigned or key not in markers_by_id or markers_by_id[key]['page'] != level['page']:
                raise ValueError('VEI inconnu, sur une autre page ou associé à plusieurs niveaux.')
            assigned.add(key)
        try:
            shape = level_path(level)
            edge = pathops.Path(shape)
            edge.stroke(6, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4)
            status = []
            for key in vei_ids:
                p = markers_by_id[key].get('point')
                status.append({'id': key, 'position': 'unknown' if p is None else
                               'near_boundary' if edge.contains(tuple(p)) else
                               'inside' if shape.contains(tuple(p)) else 'outside'})
            reports.append({'id': level['id'], 'empty': not bool(list(shape)),
                            'vei_checks': status, 'boundary_objects': 'manual_review_required'})
        except pathops.PathOpsError as error:
            raise ValueError('Opération de contours impossible ; corriger le contour indiqué.') from error
    if type(doc.get('revision', 0)) is not int or doc.get('revision', 0) < 0:
        raise ValueError('Révision de projet invalide.')
    if type(doc.get('review_acknowledged', False)) is not bool:
        raise ValueError('Accusé de contrôle visuel invalide.')
    return {'document': doc, 'report': {'levels': reports, 'warning': WARNING,
                                      'production_ready': False}}


def pdf_path(path):
    """Serialize the boolean result as PDF lines/cubics; never polygonize curves."""
    lines = []
    cursor = (0, 0)
    fmt = lambda values: ' '.join(format(float(v), '.9f').rstrip('0').rstrip('.') or '0' for v in values)
    for verb, pts in path:
        if verb == pathops.PathVerb.MOVE:
            cursor = pts[0]; lines.append(fmt(cursor) + ' m')
        elif verb == pathops.PathVerb.LINE:
            cursor = pts[0]; lines.append(fmt(cursor) + ' l')
        elif verb == pathops.PathVerb.CUBIC:
            lines.append(fmt([v for p in pts for v in p]) + ' c'); cursor = pts[-1]
        elif verb == pathops.PathVerb.QUAD:
            control, end = pts
            a = [cursor[i] + 2/3*(control[i]-cursor[i]) for i in range(2)]
            b = [end[i] + 2/3*(control[i]-end[i]) for i in range(2)]
            lines.append(fmt(a+b+list(end)) + ' c'); cursor = end
        elif verb == pathops.PathVerb.CLOSE:
            lines.append('h')
        else:
            raise ValueError('Type de courbe de découpage non pris en charge.')
    # The result uses nonzero winding from PathOps fix_winding=True.
    return ('\n'.join(lines) + '\nW n\n').encode('ascii')


def clip_preview(source, document, output_path, mode='PE', level_id=None):
    validated = validate_document(source, document)
    if mode not in ('PE', 'PI'): raise ValueError('Type PE ou PI requis.')
    level = next((l for l in document['levels'] if l['id'] == level_id), None)
    if mode == 'PE' and level is None: raise ValueError('Choisir un niveau pour le PE.')
    if mode == 'PE' and not list(level_path(level)):
        raise ValueError('La sélection du niveau est vide.')
    output_path = Path(output_path)
    if output_path.suffix.lower() != '.pdf' or output_path.exists():
        raise ValueError('Destination PDF nouvelle requise.')
    if output_path.resolve() == Path(source).resolve(): raise ValueError('Le BAT ne peut pas être écrasé.')
    source_hash = file_hash(source)
    expected = []
    with open_pdf(source) as original, pikepdf.Pdf.new() as output:
        copy_optional_content(original, output)
        if '/OutputIntents' in original.Root:
            output.Root.OutputIntents = output.copy_foreign(original.make_indirect(original.Root.OutputIntents))
        indices = [level['page']-1] if mode == 'PE' else list(range(len(original.pages)))
        for index in indices:
            page = original.pages[index]
            if float(page.obj.get('/UserUnit', 1)) != 1 or page.obj.get('/Annots'):
                raise ValueError('Unité personnalisée ou annotations : aperçu de découpage non pris en charge.')
            form = page.as_form_xobject(handle_transformations=False)
            expected.append((hashlib.sha256(form.read_bytes()).hexdigest(), resources_fingerprint(form)))
            target = output.add_blank_page()
            target.obj.MediaBox = pikepdf.Array(page.mediabox)
            target.obj.CropBox = pikepdf.Array(page.cropbox)
            target.obj.Rotate = int(page.obj.get('/Rotate', 0))
            for box in ('/TrimBox', '/BleedBox', '/ArtBox'):
                if box in page.obj: target.obj[box] = pikepdf.Array(page.obj[box])
            target.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Source=output.copy_foreign(form)))
            clipping = pdf_path(level_path(level)) if mode == 'PE' else b''
            target.Contents = output.make_stream(b'q\n' + clipping + b'/Source Do\nQ\n')
        output.docinfo['/Title'] = 'DOEMO — aperçu vectoriel des niveaux, pas une déclinaison finale'
        output_path.parent.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            with output_path.open('xb') as handle:
                created = True
                output.save(handle)
            with open_pdf(output_path) as check:
                for page, (digest, resources) in zip(check.pages, expected):
                    form = page.Resources.XObject.Source
                    if hashlib.sha256(form.read_bytes()).hexdigest() != digest or resources_fingerprint(form) != resources:
                        raise ValueError('Le contenu source a changé pendant le découpage.')
            if file_hash(source) != source_hash: raise ValueError('Le BAT a changé pendant le découpage.')
        except Exception:
            if created: output_path.unlink(missing_ok=True)
            raise
    return {'status': 'clipping_preview', 'mode': mode, 'page_count': len(indices),
            'production_ready': False, 'source_unchanged': True, 'source_streams_unchanged': True,
            'warning': WARNING, 'review': validated['report'],
            'note': 'PE : contours du niveau. PI : toutes les pages originales, sans découpage ni réorganisation. Aucun VEI masqué ni objet redressé par cet aperçu.'}
