"""Branchement du modèle de murs : inactif par défaut, repli lisible, jamais d'exception vers la page."""
import json
import sys
import textwrap

import cv2
import numpy as np
import pytest
from PIL import Image

from doemo_reconstruction import semantic_walls
from doemo_reconstruction.extract import reconstruct
from doemo_reconstruction.geometry import validate

FAKE = textwrap.dedent('''
    import os, sys
    import cv2, numpy as np
    from PIL import Image
    model, manifest, image, output = sys.argv[1:5]
    mode = os.environ.get("FAKE_MODE", "rect")
    if mode == "fail":
        raise SystemExit("Droits commerciaux non validés : weights")
    w, h = Image.open(image).size
    labels = np.zeros((h, w), np.uint8)
    if mode == "rect":
        cv2.rectangle(labels, (int(.2*w), int(.2*h)), (int(.8*w), int(.8*h)), 1, max(3, w // 60))
    elif mode == "flood":
        labels[:] = 1
    np.savez_compressed(output, labels=labels, model_sha256="a"*64, classes=np.array(["x"]), status="pending")
''')


@pytest.fixture(autouse=True)
def no_external_ocr(monkeypatch):
    monkeypatch.setattr('doemo_reconstruction.extract.ocr_texts', lambda *args: [])
    for name in ('DOEMO_WALLS_MODEL_DIR', 'DOEMO_WALLS_PYTHON', 'DOEMO_WALLS_WORKER', 'DOEMO_WALLS_MODE', 'DOEMO_WALLS_TIMEOUT', 'FAKE_MODE'):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def model_dir(tmp_path, monkeypatch):
    directory = tmp_path / 'model'; directory.mkdir()
    (directory / 'walls.onnx').write_bytes(b'x'); (directory / 'manifest.json').write_text('{}')
    worker = tmp_path / 'fake_worker.py'; worker.write_text(FAKE)
    monkeypatch.setenv('DOEMO_WALLS_MODEL_DIR', str(directory)); monkeypatch.setenv('DOEMO_WALLS_PYTHON', sys.executable)
    monkeypatch.setenv('DOEMO_WALLS_WORKER', str(worker))
    return directory


@pytest.fixture
def scan(tmp_path, monkeypatch):
    path = tmp_path / 'scan.png'; Image.new('RGB', (400, 300), 'white').save(path)
    lines = [([60, 60], [340, 60]), ([60, 66], [340, 66])]
    monkeypatch.setattr('doemo_reconstruction.extract.raster_lines', lambda *a, **k: lines)
    return path


def methods(level):
    return {w['method'] for w in level['walls']}


def test_without_configuration_the_engine_is_exactly_the_geometric_baseline(scan):
    assert not semantic_walls.configured()
    doc = reconstruct(scan); level = doc['levels'][0]
    assert methods(level) == {'parallel_boundaries'} and doc['models']['segmentation'] == 'not_configured'
    assert not any('modèle' in w.lower() for w in level['warnings'])


def test_configured_model_replaces_the_raster_proposals_and_records_provenance(scan, model_dir):
    doc = reconstruct(scan); level = doc['levels'][0]
    validate(doc)
    assert methods(level) == {'architectural_mask_medial_axis'} and len(level['walls']) >= 4
    assert doc['models']['segmentation'] == 'a' * 64
    assert any('modèle de segmentation entraîné' in w and 'aucun n\'est validé' in w for w in level['warnings'])
    xs = [p[0] for w in level['walls'] for p in (w['a'], w['b'])]
    assert min(xs) == pytest.approx(80, abs=4) and max(xs) == pytest.approx(320, abs=4)       # 20 % et 80 % de 400 px
    assert all(w['status'] == 'pending' and w['evidence'][0]['model_sha256'] == 'a' * 64 for w in level['walls'])


def test_mode_add_keeps_both_sources(scan, model_dir, monkeypatch):
    monkeypatch.setenv('DOEMO_WALLS_MODE', 'add')
    level = reconstruct(scan)['levels'][0]
    assert methods(level) == {'parallel_boundaries', 'architectural_mask_medial_axis'}


@pytest.mark.parametrize('mode, reason', [('fail', 'Droits commerciaux non validés'), ('flood', 'masque inondé'), ('empty', 'aucun mur')])
def test_any_failure_falls_back_to_the_baseline_with_a_visible_reason(scan, model_dir, monkeypatch, mode, reason):
    monkeypatch.setenv('FAKE_MODE', mode)
    doc = reconstruct(scan); level = doc['levels'][0]
    assert methods(level) == {'parallel_boundaries'} and doc['models']['segmentation'] == 'not_configured'
    assert any('Modèle de murs non utilisé' in w and reason in w for w in level['warnings'])


@pytest.mark.parametrize('missing', ['DOEMO_WALLS_PYTHON', 'walls.onnx', 'manifest.json'])
def test_missing_pieces_are_reported_not_raised(scan, model_dir, monkeypatch, missing):
    if missing.startswith('DOEMO'):
        monkeypatch.delenv(missing)
    else:
        (model_dir / missing).unlink()
    level = reconstruct(scan)['levels'][0]
    assert methods(level) == {'parallel_boundaries'} and any('Modèle de murs non utilisé' in w for w in level['warnings'])


def test_timeout_is_a_fallback(scan, model_dir, monkeypatch, tmp_path):
    slow = tmp_path / 'slow.py'; slow.write_text('import time; time.sleep(30)')
    monkeypatch.setenv('DOEMO_WALLS_WORKER', str(slow)); monkeypatch.setenv('DOEMO_WALLS_TIMEOUT', '0.5')
    level = reconstruct(scan)['levels'][0]
    assert any('délai dépassé' in w for w in level['warnings']) and methods(level) == {'parallel_boundaries'}


def test_real_worker_refuses_a_model_whose_rights_are_not_validated(scan, model_dir, monkeypatch):
    monkeypatch.delenv('DOEMO_WALLS_WORKER')                       # vrai segmentation/run_onnx.py
    manifest = {
        'sha256': '0' * 64, 'input_contract': 'rgb_nchw_0_1', 'output_contract': 'nchw_logits', 'input_size': [64, 64],
        'classes': semantic_walls.CLASSES,
        'rights': {k: {'commercial_use': False, 'evidence_url': '', 'reviewed_by': ''} for k in ('code', 'weights', 'training_data')}}
    (model_dir / 'manifest.json').write_text(json.dumps(manifest))
    level = reconstruct(scan)['levels'][0]
    assert methods(level) == {'parallel_boundaries'} and any('Droits commerciaux non validés' in w for w in level['warnings'])


def test_walls_are_scaled_from_image_pixels_to_document_units_and_text_is_excluded(model_dir):
    image = Image.new('RGB', (400, 300), 'white')
    walls, sha, reason = semantic_walls.propose(image, 800, 600, 'b' * 64)
    assert reason is None and sha == 'a' * 64
    assert max(p[0] for w in walls for p in (w['a'], w['b'])) == pytest.approx(640, abs=8)      # 80 % de 800 : document = 2 x image
    over_text = semantic_walls.propose(image, 800, 600, 'b' * 64, text_boxes=[{'bbox': [0, 0, 800, 600]}])
    assert over_text[0] is None                                                              # tout le raster masqué par l'OCR


def chain(points, chain_id=0, thickness=6., kind='wall'):
    from doemo_reconstruction.geometry import wall
    walls = []
    for index, (a, b) in enumerate(zip(points, points[1:])):
        w = wall(a, b, thickness, method='architectural_mask_medial_axis', confidence=0.,
                 evidence=[{'chain': chain_id, 'segment': index, 'source_sha256': 's' * 64, 'model_sha256': 'm' * 64}])
        w['kind'] = kind
        walls.append(w)
    return walls


def test_a_staircase_of_micro_segments_becomes_one_wall_with_provenance():
    points = [[x, 100 + (x % 2) * .4] for x in range(0, 200)]                  # 199 segments de 1 unité, léger zigzag
    merged, dropped = semantic_walls.simplify_chains(chain(points), epsilon=2., min_length=14.)
    assert dropped == 0 and len(merged) == 1
    w = merged[0]
    assert w['a'] == [0, 100] and w['b'][0] == 199 and w['thickness'] == pytest.approx(6.) and w['kind'] == 'wall'
    assert w['evidence'][0]['simplified_from_segments'] == 199 and w['evidence'][0]['model_sha256'] == 'm' * 64


def test_an_l_shaped_chain_keeps_its_corner_and_dust_is_dropped():
    path = [[x, 50] for x in range(0, 100)] + [[100, y] for y in range(50, 150)]
    dust = [[10, 10], [11, 10], [12, 11], [13, 11]]
    merged, dropped = semantic_walls.simplify_chains(chain(path, 0) + chain(dust, 1), epsilon=2., min_length=14.)
    assert dropped == 1 and len(merged) == 2
    assert {tuple(w['b']) for w in merged} >= {(100, 50), (100, 149)}


def test_a_broken_chain_is_not_bridged_and_partition_kind_follows_the_majority():
    first = chain([[x, 20] for x in range(0, 60)], 0, kind='partition')
    second = chain([[x, 20] for x in range(80, 140)], 0, kind='partition')
    second = [w for w in second]
    for k, w in enumerate(second):
        w['evidence'][0]['segment'] = 100 + k                                      # même chaîne, après un trou de 20 unités
    merged, _ = semantic_walls.simplify_chains(first + second, epsilon=2., min_length=14.)
    assert len(merged) == 2 and all(w['kind'] == 'partition' for w in merged)
    assert merged[0]['b'][0] == 59 and merged[1]['a'][0] == 80


def test_the_page_reports_how_many_skeleton_segments_became_walls(scan, model_dir):
    level = reconstruct(scan)['levels'][0]
    assert any('Nettoyage du modèle' in w and 'micro-segments' in w for w in level['warnings'])
