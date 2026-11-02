"""A single source frame and revision history for walls and equipment annotations."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from doemo_releves.api import create_app
from doemo_releves.exchange import validate_state
from doemo_releves.models import ProjectState, StructurePage
from doemo_releves.queue import process_one
from doemo_releves import structure


def fixture(tmp_path):
    app = create_app(tmp_path / 'private')
    client = TestClient(app, headers={'X-Doemo-User': 'designer', 'X-Doemo-Role': 'dessinateur'})
    project = client.post('/projects', json={'name': 'Synthetic unified document'}).json()
    ident = project['id']
    did = 'source1'
    directory = app.state.store.root / 'documents' / did
    directory.mkdir(parents=True)
    Image.new('RGB', (600, 400), 'white').save(directory / 'page-1.png')
    original = (directory / 'page-1.png').read_bytes()
    (directory / 'original').write_bytes(original)
    document = {'id': did, 'name': 'source.png', 'role': 'survey', 'sha256': hashlib.sha256(original).hexdigest(),
                'pages': [{'number': 1, 'width': 600, 'height': 400, 'pdf_size_pt': None}]}
    with app.state.store.connect() as db:
        db.execute('INSERT INTO documents VALUES(?,?,?)',
                   (did, ident, json.dumps({k: v for k, v in document.items() if k != 'id'})))
    return client, client.get('/projects/' + ident).json(), document


def page(document):
    return {'source_document_id': document['id'], 'source_page': 1, 'source_sha256': document['sha256'],
            'width': 600, 'height': 400, 'unit': 'px', 'analysis_ids': [], 'warnings': [],
            'walls': [{'id': 'manual1', 'a': [100, 100], 'b': [400, 100], 'thickness': None,
                       'openings': [], 'method': 'manual', 'confidence': 0, 'status': 'pending'}]}


def annotation(document):
    return {'id': 'equipment1', 'source_document_id': document['id'], 'source_page': 1,
            'bbox': {'x': .2, 'y': .3, 'w': .05, 'h': .05}, 'anchor': {'x': .25, 'y': .3},
            'text': 'EXT', 'equipment_type': 'EXT_PORTATIF'}


def result(document, wall_id='analysis1'):
    p = page(document)
    p['walls'][0].update(id=wall_id, method='parallel_boundaries', thickness=6)
    return {'structure_page': p, 'annotations': [], 'warnings': [], 'observations': []}


@pytest.mark.parametrize('change', [
    {'width': float('inf')}, {'unit': 'mm'}, {'width': 0},
    {'walls': [{'id': 'bad', 'a': [0, 0], 'b': [601, 10]}]},
    {'walls': [{'id': 'bad', 'a': [0, 0], 'b': [0, 0]}]},
    {'walls': [{'id': 'bad', 'a': [0, 0], 'b': [3, float('nan')]}]},
    {'walls': [{'id': 'bad', 'a': [0, 0], 'b': [50, 0], 'openings': [{'start': .8, 'end': .2, 'kind': 'door'}]}]},
    {'walls': [{'id': 'bad', 'a': [0, 0], 'b': [50, 0], 'openings': [
        {'start': .1, 'end': .5, 'kind': 'door'}, {'start': .3, 'end': .7, 'kind': 'window'}]}]},
])
def test_structure_refuses_nonfinite_outside_degenerate_and_overlapping_geometry(change):
    raw = page({'id': 'source1', 'sha256': 'a' * 64})
    raw.update(change)
    with pytest.raises(ValueError):
        StructurePage.model_validate(raw)


def test_source_frame_and_hash_are_checked_against_stored_document(tmp_path):
    _, p, d = fixture(tmp_path)
    for key, value in [('source_document_id', 'other'), ('source_sha256', 'a' * 64),
                       ('source_page', 2), ('width', 599), ('height', 401), ('unit', 'pt')]:
        raw = page(d)
        raw[key] = value
        state = ProjectState(revision=0, structure_pages=[raw])
        with pytest.raises(ValueError):
            validate_state(state, p['documents'])
    assert validate_state(ProjectState(revision=0, structure_pages=[page(d)]), p['documents'])


def test_existing_frame_cannot_switch_from_pixels_to_pdf_points(tmp_path):
    c, p, d = fixture(tmp_path)
    ident = p['id']
    d['pages'][0]['pdf_size_pt'] = [300, 200]
    with c.app.state.store.connect() as db:
        db.execute('UPDATE documents SET metadata=? WHERE id=?',
                   (json.dumps({k: v for k, v in d.items() if k != 'id'}), d['id']))
    s = page(d)
    s['walls'][0].update(a=[50, 50], b=[200, 50], status='approved')
    p['state']['structure_pages'] = [s]
    response = c.put(f'/projects/{ident}/state', json=p['state'])
    assert response.status_code == 200, response.text
    saved = response.json()['state']
    changed = copy.deepcopy(saved)
    changed['structure_pages'][0].update(unit='pt', width=300, height=200)
    # This frame is valid for the PDF and all endpoints remain in bounds, but
    # reinterpreting them would move the wall relative to its source equipment.
    assert c.put(f'/projects/{ident}/state', json=changed).status_code == 422
    assert c.get(f'/projects/{ident}').json()['state'] == saved


def test_manual_save_reopen_and_old_client_preserve_both_layers(tmp_path, monkeypatch):
    monkeypatch.delenv('DOEMO_STRUCTURE_PYTHON', raising=False)
    monkeypatch.delenv('DOEMO_STRUCTURE_MODULE_PATH', raising=False)
    c, p, d = fixture(tmp_path)
    ident = p['id']
    state = p['state']
    state['annotations'] = [annotation(d)]
    state['structure_pages'] = [page(d)]
    response = c.put(f'/projects/{ident}/state', json=state)
    assert response.status_code == 200, response.text
    saved = response.json()['state']
    old_client = copy.deepcopy(saved)
    old_client.pop('structure_pages')
    old_client['annotations'][0]['text'] = 'EXT confirmé'
    response = c.put(f'/projects/{ident}/state', json=old_client)
    assert response.status_code == 200, response.text
    reopened = c.get(f'/projects/{ident}').json()['state']
    assert reopened['structure_pages'] == saved['structure_pages']
    assert reopened['annotations'][0]['anchor'] == {'x': .25, 'y': .3}
    assert reopened['annotations'][0]['text'] == 'EXT confirmé'
    assert c.get(f'/projects/{ident}/history/1').json()['structure_pages'] == saved['structure_pages']
    assert c.put(f'/projects/{ident}/state', json=state).status_code == 409
    assert c.put(f'/projects/{ident}/state', json=reopened, headers={'X-Doemo-User': 'other'}).status_code == 404


def test_unconfigured_analysis_is_honest_and_does_not_enqueue(tmp_path, monkeypatch):
    monkeypatch.delenv('DOEMO_STRUCTURE_PYTHON', raising=False)
    monkeypatch.delenv('DOEMO_STRUCTURE_MODULE_PATH', raising=False)
    c, p, d = fixture(tmp_path)
    status = c.get('/projects/structure-status').json()
    assert status['configured'] is False and status['status'] == 'not_configured'
    response = c.post(f"/projects/{p['id']}/jobs", json={'engine': 'structure', 'document_id': d['id'], 'page': 1})
    assert response.status_code == 422 and 'non configurée' in response.json()['detail']
    assert c.get(f"/projects/{p['id']}/jobs").json() == []
    assert c.get('/projects/structure-status', headers={'X-Doemo-Role': 'client'}).status_code == 403


def configure_fake(monkeypatch, data):
    monkeypatch.setattr(structure, 'configuration', lambda: (Path(sys.executable), Path('/unused')))
    monkeypatch.setattr(structure, 'analyze', lambda *a: copy.deepcopy(data))


def test_durable_job_apply_preserves_edits_annotations_and_retry_is_idempotent(tmp_path, monkeypatch):
    c, p, d = fixture(tmp_path)
    configure_fake(monkeypatch, result(d))
    ident = p['id']
    p['state']['structure_pages'] = [page(d)]
    p['state']['annotations'] = [annotation(d)]
    p = c.put(f'/projects/{ident}/state', json=p['state']).json()
    request = {'engine': 'structure', 'document_id': d['id'], 'page': 1}
    job = c.post(f'/projects/{ident}/jobs', json=request).json()['id']
    assert process_one(c.app.state.store)
    assert c.get(f'/projects/{ident}/jobs').json()[0]['status'] == 'completed'
    assert len(c.get(f'/projects/{ident}').json()['state']['structure_pages'][0]['walls']) == 1
    assert c.post(f'/projects/{ident}/jobs/{job}/apply', json={'revision': 0}).status_code == 409
    response = c.post(f'/projects/{ident}/jobs/{job}/apply', json={'revision': p['state']['revision']})
    assert response.status_code == 200, response.text
    p = response.json()
    assert len(p['state']['annotations']) == 1
    assert len(p['state']['structure_pages'][0]['walls']) == 2
    wall = p['state']['structure_pages'][0]['walls'][1]
    wall['b'] = [450, 100]
    p = c.put(f'/projects/{ident}/state', json=p['state']).json()
    repeated = c.post(f'/projects/{ident}/jobs/{job}/apply', json={'revision': p['state']['revision']}).json()
    assert repeated == p
    job2 = c.post(f'/projects/{ident}/jobs', json=request).json()['id']
    assert process_one(c.app.state.store)
    p = c.post(f'/projects/{ident}/jobs/{job2}/apply', json={'revision': p['state']['revision']}).json()
    assert len(p['state']['structure_pages'][0]['walls']) == 2
    assert p['state']['structure_pages'][0]['walls'][1]['b'] == [450, 100]
    assert p['state']['structure_pages'][0]['analysis_ids'] == [job, job2]


def test_rejected_edited_wall_survives_history_restore_and_a_new_analysis(tmp_path, monkeypatch):
    c, p, d = fixture(tmp_path)
    configure_fake(monkeypatch, result(d))
    ident = p['id']
    p['state']['structure_pages'] = [page(d)]
    p['state']['annotations'] = [annotation(d)]
    p = c.put(f'/projects/{ident}/state', json=p['state']).json()
    historical = copy.deepcopy(p['state'])
    request = {'engine': 'structure', 'document_id': d['id'], 'page': 1}
    job = c.post(f'/projects/{ident}/jobs', json=request).json()['id']
    assert process_one(c.app.state.store)
    p = c.post(f'/projects/{ident}/jobs/{job}/apply', json={'revision': p['state']['revision']}).json()
    p['state']['structure_pages'][0]['walls'][0]['b'] = [480, 100]
    rejected = p['state']['structure_pages'][0]['walls'][1]
    rejected.update(b=[450, 100], status='rejected')
    p = c.put(f'/projects/{ident}/state', json=p['state']).json()

    # The UI's history restoration restores old geometry but retains the current
    # analysis ledger and tombstones walls that did not exist in that revision.
    restoration = copy.deepcopy(historical)
    restoration['revision'] = p['state']['revision']
    restored_page = restoration['structure_pages'][0]
    restored_page['analysis_ids'] = p['state']['structure_pages'][0]['analysis_ids']
    restored_page['walls'].append(copy.deepcopy(p['state']['structure_pages'][0]['walls'][1]))
    response = c.put(f'/projects/{ident}/state', json=restoration)
    assert response.status_code == 200, response.text
    p = response.json()
    assert p['state']['structure_pages'][0]['walls'][0]['b'] == [400, 100]
    assert p['state']['structure_pages'][0]['walls'][1]['status'] == 'rejected'
    assert c.post(f'/projects/{ident}/jobs/{job}/apply', json={'revision': p['state']['revision']}).json() == p

    job2 = c.post(f'/projects/{ident}/jobs', json=request).json()['id']
    assert process_one(c.app.state.store)
    response = c.post(f'/projects/{ident}/jobs/{job2}/apply', json={'revision': p['state']['revision']})
    assert response.status_code == 200, response.text
    p = response.json()
    walls = p['state']['structure_pages'][0]['walls']
    assert len(walls) == 2 and walls[1]['id'] == 'analysis1'
    assert walls[1]['status'] == 'rejected' and walls[1]['b'] == [450, 100]
    assert p['state']['structure_pages'][0]['analysis_ids'] == [job, job2]
    assert p['state']['annotations'][0]['anchor'] == {'x': .25, 'y': .3}


def test_analyzed_page_cannot_be_erased_but_legacy_client_omission_is_safe(tmp_path, monkeypatch):
    c, p, d = fixture(tmp_path)
    configure_fake(monkeypatch, result(d))
    ident = p['id']
    job = c.post(f'/projects/{ident}/jobs', json={'engine': 'structure', 'document_id': d['id'], 'page': 1}).json()['id']
    assert process_one(c.app.state.store)
    p = c.post(f'/projects/{ident}/jobs/{job}/apply', json={'revision': 0}).json()
    state = copy.deepcopy(p['state'])
    state['structure_pages'] = []
    response = c.put(f'/projects/{ident}/state', json=state)
    assert response.status_code == 422 and 'historique' in response.json()['detail']
    assert c.get(f'/projects/{ident}').json() == p
    state.pop('structure_pages')
    response = c.put(f'/projects/{ident}/state', json=state)
    assert response.status_code == 200, response.text
    assert response.json()['state']['structure_pages'] == p['state']['structure_pages']


def test_approval_invalidated_on_edit_and_analysis_history_not_forged(tmp_path):
    c, p, d = fixture(tmp_path)
    ident = p['id']
    p['state']['structure_pages'] = [page(d)]
    p['state']['structure_pages'][0]['walls'][0]['status'] = 'approved'
    p = c.put(f'/projects/{ident}/state', json=p['state']).json()
    p['state']['structure_pages'][0]['walls'][0]['b'] = [410, 100]
    p = c.put(f'/projects/{ident}/state', json=p['state']).json()
    assert p['state']['structure_pages'][0]['walls'][0]['status'] == 'pending'
    p['state']['structure_pages'][0]['analysis_ids'] = ['invented']
    assert c.put(f'/projects/{ident}/state', json=p['state']).status_code == 422


def test_opening_approval_can_be_saved_but_geometry_change_requires_review(tmp_path):
    c, p, d = fixture(tmp_path)
    ident = p['id']
    p['state']['structure_pages'] = [page(d)]
    wall = p['state']['structure_pages'][0]['walls'][0]
    wall['openings'] = [{'start': .2, 'end': .4, 'kind': 'door', 'status': 'pending'}]
    p = c.put(f'/projects/{ident}/state', json=p['state']).json()
    wall = p['state']['structure_pages'][0]['walls'][0]
    wall['status'] = wall['openings'][0]['status'] = 'approved'
    p = c.put(f'/projects/{ident}/state', json=p['state']).json()
    wall = p['state']['structure_pages'][0]['walls'][0]
    assert wall['status'] == wall['openings'][0]['status'] == 'approved'
    wall['openings'][0]['end'] = .5
    p = c.put(f'/projects/{ident}/state', json=p['state']).json()
    wall = p['state']['structure_pages'][0]['walls'][0]
    assert wall['status'] == wall['openings'][0]['status'] == 'pending'


def test_job_result_bound_to_source_and_other_owner_cannot_apply(tmp_path, monkeypatch):
    c, p, d = fixture(tmp_path)
    data = result(d)
    data['structure_page']['source_sha256'] = 'b' * 64
    configure_fake(monkeypatch, data)
    ident = p['id']
    job = c.post(f'/projects/{ident}/jobs', json={'engine': 'structure', 'document_id': d['id'], 'page': 1}).json()['id']
    assert process_one(c.app.state.store)
    assert c.post(f'/projects/{ident}/jobs/{job}/apply', json={'revision': 0}, headers={'X-Doemo-User': 'other'}).status_code == 404
    assert c.post(f'/projects/{ident}/jobs/{job}/apply', json={'revision': 0}).status_code == 422
    assert c.get(f'/projects/{ident}').json()['state']['structure_pages'] == []


def test_converter_preserves_upright_frame_stable_ids_and_unknown_ai_width(tmp_path):
    _, _, d = fixture(tmp_path)
    raw = {'source': {'sha256': 'a' * 64}, 'models': {'segmentation': 'b' * 64},
           'levels': [{'source_page': 1, 'unit': 'px', 'width': 600, 'height': 400, 'walls': [
               {'id': 'random-engine-id', 'a': [12, 30], 'b': [550, 30], 'thickness': 10,
                'method': 'architectural_mask_medial_axis', 'confidence': .7,
                'openings': [{'start': .2, 'end': .3, 'kind': 'door', 'status': 'approved'}]}]}]}
    a = structure.convert_result(raw, d, 1, 'a' * 64)
    raw['levels'][0]['walls'][0]['id'] = 'different-random-id'
    b = structure.convert_result(raw, d, 1, 'a' * 64)
    assert a == b
    wall = a['structure_page']['walls'][0]
    assert wall['a'] == [12, 30] and wall['thickness'] is None
    assert wall['status'] == 'pending' and wall['openings'][0]['status'] == 'pending'
    raw['levels'][0]['width'] = 400
    with pytest.raises(ValueError, match='repère'):
        structure.convert_result(raw, d, 1, 'a' * 64)


def test_pdf_second_page_uses_exact_raster_frame_and_never_invents_native_extraction(tmp_path):
    _, _, d = fixture(tmp_path)
    d['pages'].append({'number': 2, 'width': 900, 'height': 1200, 'pdf_size_pt': [450, 600]})
    raw = {'source': {'sha256': 'a' * 64}, 'models': {'segmentation': 'not_configured'},
           'levels': [{'source_page': 1, 'unit': 'px', 'width': 900, 'height': 1200, 'walls': [
               {'a': [225, 300], 'b': [675, 300], 'thickness': 4, 'openings': [], 'method': 'parallel_boundaries'}]}]}
    converted = structure.convert_result(raw, d, 2, 'a' * 64)
    page2 = converted['structure_page']
    assert page2['source_page'] == 2 and page2['source_document_id'] == d['id']
    assert page2['walls'][0]['a'][0] / page2['width'] == .25
    assert page2['walls'][0]['a'][1] / page2['height'] == .25
    assert any('vectoriels natifs' in w for w in page2['warnings'])
    assert converted['model_sha256'] is None


def test_exif_source_and_structure_share_the_same_upright_frame(tmp_path):
    c, _, _ = fixture(tmp_path)
    p = c.post('/projects', json={'name': 'Rotated photograph'}).json()
    image = Image.new('RGB', (120, 80), 'white')
    exif = Image.Exif()
    exif[274] = 6
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', exif=exif)
    response = c.post(f"/projects/{p['id']}/documents", data={'role': 'survey'},
                      files={'file': ('rotated.jpg', buffer.getvalue(), 'image/jpeg')})
    assert response.status_code == 200, response.text
    p = response.json()
    d = p['documents'][0]
    assert [d['pages'][0]['width'], d['pages'][0]['height']] == [80, 120]
    structure_page = page(d)
    structure_page.update(width=80, height=120)
    structure_page['walls'][0].update(a=[20, 30], b=[60, 30])
    p['state']['structure_pages'] = [structure_page]
    a = annotation(d)
    a['anchor'] = {'x': .25, 'y': .25}
    p['state']['annotations'] = [a]
    saved = c.put(f"/projects/{p['id']}/state", json=p['state'])
    assert saved.status_code == 200, saved.text
    s = saved.json()['state']
    wall = s['structure_pages'][0]['walls'][0]
    anchor = s['annotations'][0]['anchor']
    assert wall['a'] == [anchor['x'] * 80, anchor['y'] * 120]


def test_runner_uses_configured_engine_and_exact_png_without_leaking_errors(tmp_path, monkeypatch):
    c, p, d = fixture(tmp_path)
    modules = tmp_path / 'engine'
    package = modules / 'doemo_reconstruction'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('')
    (package / 'extract.py').write_text('''
import hashlib
from PIL import Image
def reconstruct(source, pages):
    assert pages == [1]
    with Image.open(source) as im:
        w, h = im.size
    return {'source': {'sha256': hashlib.sha256(source.read_bytes()).hexdigest()},
            'levels': [{'source_page': 1, 'width': w, 'height': h, 'unit': 'px',
                        'walls': [{'id': 'one', 'a': [10, 20], 'b': [90, 20], 'thickness': 4,
                                   'method': 'parallel_boundaries', 'openings': []}]}]}
''')
    monkeypatch.setenv('DOEMO_STRUCTURE_PYTHON', sys.executable)
    monkeypatch.setenv('DOEMO_STRUCTURE_MODULE_PATH', str(modules))
    output = structure.analyze(c.app.state.store, p['id'], d['id'], 1)
    assert output['structure_page']['width'] == 600
    assert output['structure_page']['walls'][0]['a'] == [10, 20]
    assert output['structure_page']['source_sha256'] == d['sha256']
    (package / 'extract.py').write_text('raise RuntimeError("SECRET_FAKE_TEST_VALUE")')
    with pytest.raises(ValueError) as error:
        structure.analyze(c.app.state.store, p['id'], d['id'], 1)
    assert 'SECRET' not in str(error.value) and str(modules) not in str(error.value)
