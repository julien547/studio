"""Bounded adapter to the existing reconstruction engine, on the exact source preview.

No engine/model is installed or downloaded here. Server operators explicitly select
the existing engine environment. The browser cannot choose paths or executables.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile

from .models import StructurePage, StructureWall, StructureOpening


class StructureUnavailable(ValueError):
    pass


def configuration():
    python = os.environ.get('DOEMO_STRUCTURE_PYTHON', '')
    modules = os.environ.get('DOEMO_STRUCTURE_MODULE_PATH', '')
    if not python or not modules:
        raise StructureUnavailable('Analyse des murs non configurée. Le dessin manuel et les annotations restent disponibles.')
    python, modules = Path(python), Path(modules)
    if (not python.is_absolute() or not python.is_file() or not os.access(python, os.X_OK)
            or not modules.is_absolute() or not (modules / 'doemo_reconstruction' / 'extract.py').is_file()):
        raise StructureUnavailable('Moteur de murs indisponible. Faire vérifier sa configuration serveur.')
    return python, modules


def public_status():
    try:
        configuration()
    except StructureUnavailable as exc:
        return {'configured': False, 'status': 'not_configured', 'message': str(exc)}
    return {'configured': True, 'status': 'available',
            'message': 'Moteur de murs configuré. Les propositions restent à vérifier sur la source.'}


def _wall_id(document_id, page, wall):
    # Independent of engine UUIDs/job retries. An edited wall keeps its original ID.
    geometry = {key: wall[key] for key in ('a', 'b', 'thickness', 'openings')}
    raw = json.dumps([document_id, page, geometry], sort_keys=True, separators=(',', ':'), allow_nan=False)
    return 'structure-' + hashlib.sha256(raw.encode()).hexdigest()[:32]


def convert_result(raw, source, number, image_digest):
    """Reject wrong frames; proposals cannot carry engine approval into the project."""
    page = source['pages'][number - 1]
    if raw.get('source', {}).get('sha256') != image_digest or len(raw.get('levels', [])) != 1:
        raise ValueError('Le moteur a renvoyé une autre source')
    level = raw['levels'][0]
    if (level.get('source_page') != 1 or level.get('unit') != 'px'
            or level.get('width') != page['width'] or level.get('height') != page['height']):
        raise ValueError('Le moteur a changé le repère de la page')
    if not isinstance(level.get('walls'), list) or len(level['walls']) > 10000:
        raise ValueError('Trop de murs dans le résultat')
    walls = []
    identifiers = set()
    synthetic_width = False
    for candidate in level['walls']:
        method = candidate.get('method', 'reconstruction')
        thickness = candidate.get('thickness')
        if method == 'architectural_mask_medial_axis':
            # A fixed-width learning target does not measure real architectural thickness.
            synthetic_width = True
            thickness = None
        openings = [StructureOpening.model_validate({**o, 'status': 'pending'}) for o in candidate.get('openings', [])]
        geometry = {'a': candidate['a'], 'b': candidate['b'], 'thickness': thickness,
                    'openings': [o.model_dump() for o in openings]}
        ident = _wall_id(source['id'], number, geometry)
        if ident in identifiers:
            continue
        identifiers.add(ident)
        walls.append(StructureWall(id=ident, **geometry, status='pending', method=method,
                                   confidence=candidate.get('confidence', 0)))
    segmentation = raw.get('models', {}).get('segmentation')
    model_sha256 = segmentation if isinstance(segmentation, str) and re.fullmatch(r'[a-f0-9]{64}', segmentation) else None
    warnings = ['Propositions dans le repère exact du document source ; vérifier les murs, les angles et les passages.']
    if model_sha256:
        warnings.append('Modèle de segmentation local utilisé ; aucune géométrie validée automatiquement.')
    else:
        warnings.append('Moteur géométrique utilisé ; le modèle de segmentation n’a pas été appliqué.')
    if synthetic_width:
        warnings.append('Épaisseurs des murs IA inconnues : la largeur du masque ne constitue pas une mesure.')
    if page.get('pdf_size_pt'):
        warnings.append('Analyse de l’aperçu PDF ; les tracés vectoriels natifs ne sont pas extraits par ce raccordement.')
    if not walls:
        warnings.append('Aucun mur identifié sur cette page ; le dessin manuel reste disponible.')
    structure = StructurePage(source_document_id=source['id'], source_page=number,
                              source_sha256=source['sha256'], width=page['width'], height=page['height'],
                              unit='px', walls=walls, warnings=warnings)
    return {'structure_page': structure.model_dump(mode='json'), 'annotations': [],
            'warnings': warnings, 'observations': [], 'analysis_image_sha256': image_digest,
            'model_sha256': model_sha256}


def analyze(store, project_id, document_id, number):
    python, modules = configuration()
    # Recheck source membership in the worker, not just in the HTTP submission.
    with store.connect() as c:
        row = c.execute('SELECT metadata FROM documents WHERE id=? AND project_id=?',
                        (document_id, project_id)).fetchone()
    if not row:
        raise ValueError('Document de structure inaccessible')
    source = dict(id=document_id, **json.loads(row['metadata']))
    if source.get('role') != 'survey' or type(number) is not int or not 1 <= number <= len(source['pages']):
        raise ValueError('Page de relevé invalide')
    image_path = store.root / 'documents' / document_id / f'page-{number}.png'
    image_digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    page = source['pages'][number - 1]
    with tempfile.TemporaryDirectory(prefix='doemo-structure-') as tmp:
        args, output = Path(tmp) / 'input.json', Path(tmp) / 'result.json'
        args.write_text(json.dumps({'module_path': str(modules), 'source': str(image_path),
            'source_sha256': image_digest, 'width': page['width'], 'height': page['height'], 'output': str(output)}))
        runner = Path(__file__).with_name('structure_runner.py')
        try:
            run = subprocess.Popen([str(python), str(runner), str(args)], start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1'))
            try:
                run.wait(timeout=190)
            except subprocess.TimeoutExpired:
                # The reconstruction engine may have spawned the isolated ONNX worker.
                os.killpg(run.pid, signal.SIGKILL)
                run.wait()
                raise
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError('Analyse des murs interrompue : moteur indisponible ou délai dépassé.') from exc
        if run.returncode or not output.is_file() or output.stat().st_size > 16 * 1024**2:
            raise ValueError('Analyse des murs interrompue : vérifier le moteur ou corriger manuellement.')
        try:
            raw = json.loads(output.read_text())
        except (ValueError, OSError) as exc:
            raise ValueError('Résultat de structure illisible') from exc
    return convert_result(raw, source, number, image_digest)


def apply_result(state, result, job_id, source, page_number):
    proposal = StructurePage.model_validate(result['structure_page'])
    if (proposal.source_document_id != source['id'] or proposal.source_page != page_number
            or proposal.source_sha256 != source['sha256']):
        raise ValueError('La proposition ne correspond pas au document analysé')
    previous = next((p for p in state.structure_pages if
                     (p.source_document_id, p.source_page) == (proposal.source_document_id, proposal.source_page)), None)
    if previous and job_id in previous.analysis_ids:
        return False
    if previous and (previous.width, previous.height, previous.unit) != (proposal.width, proposal.height, proposal.unit):
        raise ValueError('Repères de structure différents : conserver les corrections existantes')
    for wall in proposal.walls:
        wall.status = 'pending'
        for opening in wall.openings:
            opening.status = 'pending'
    if previous:
        known = {wall.id for wall in previous.walls}
        previous.walls.extend(wall for wall in proposal.walls if wall.id not in known)
        previous.analysis_ids.append(job_id)
        previous.warnings = list(dict.fromkeys(previous.warnings + proposal.warnings))
    else:
        proposal.analysis_ids = [job_id]
        state.structure_pages.append(proposal)
    state.workflow = 'review'
    # Validate global limits after appending; model assignment itself is not validated.
    checked = type(state).model_validate(state.model_dump())
    state.structure_pages = checked.structure_pages
    return True
