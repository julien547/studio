"""Adaptateur d'entraînement des murs : données, mesure, entraînement de bout en bout (CPU), export ONNX conforme."""
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

torch = pytest.importorskip('torch')

from segmentation import run_onnx
from segmentation.walls_training import CLASSES, bundle
from segmentation.walls_training.data import WALL, augment, rasterize
from segmentation.walls_training.metrics import length_scores
from segmentation.walls_training.model import UNet

W, H = 320, 240
RECT = [[60, 50, 260, 50], [260, 50, 260, 190], [260, 190, 60, 190], [60, 190, 60, 50], [160, 50, 160, 190]]


def plan_png(path, shift=0):
    image = np.full((H, W, 3), 255, np.uint8)
    for x1, y1, x2, y2 in RECT:
        cv2.line(image, (x1 + shift, y1), (x2 + shift, y2), (20, 20, 20), 8)
    cv2.imwrite(str(path), image)


def make_bundle(tmp_path, splits=('train', 'train', 'train', 'train', 'validation', 'test'), same_document=False):
    z = tmp_path / 'b.zip'
    with zipfile.ZipFile(z, 'w') as out:
        rows = []
        for k, split in enumerate(splits):
            png = tmp_path / f'p{k}.png'; plan_png(png, shift=k % 3)
            out.write(png, f'images/p{k}.png')
            rows.append({'ref': f'P{k}', 'image': f'images/p{k}.png', 'width': W, 'height': H, 'split': split,
                         'document_sha256': ('a' if same_document else f'{k:064x}')[:64].ljust(64, '0'),
                         'segments': [[x1 + k % 3, y1, x2 + k % 3, y2] for x1, y1, x2, y2 in RECT]})
        out.writestr('walls.jsonl', '\n'.join(json.dumps(r) for r in rows) + '\n')
    return z


def test_rasterize_marks_exactly_the_wall_pixels_in_the_squeezed_frame():
    mask = rasterize([[0, 100, 200, 100]], 200, 200, 64, thickness=20)
    assert mask.shape == (64, 64) and mask[32, 5] == WALL and mask[5, 5] == 0 and mask[60, 32] == 0
    squeezed = rasterize([[0, 50, 100, 50]], 100, 100, 64, thickness=1)     # image non carrée -> repère déformé comme run_onnx
    assert squeezed[32].all() or squeezed[31].all() or squeezed[33].any()


def test_augmentation_moves_image_and_mask_together():
    image = np.full((128, 128, 3), 255, np.uint8); image[60:68, 10:118] = 10
    mask = np.zeros((128, 128), np.uint8); mask[60:68, 10:118] = WALL
    for seed in range(8):
        im, m = augment(image, mask, np.random.default_rng(seed))
        assert m.any() and abs(float(im[m == WALL].mean()) - float(im[m == 0].mean())) > 40      # le mur reste sombre sous le masque


def test_bundle_validates_splits_and_refuses_document_leaks(tmp_path):
    records = bundle.unpack(make_bundle(tmp_path), tmp_path / 'ok')
    assert {k: len(v) for k, v in records.items()} == {'train': 4, 'validation': 1, 'test': 1}
    with pytest.raises(ValueError, match='plusieurs splits'):
        (tmp_path / 'x').mkdir()
        bundle.unpack(make_bundle(tmp_path / 'x', same_document=True), tmp_path / 'leak')
    with pytest.raises(ValueError, match='au moins un plan'):
        bundle.unpack(make_bundle(tmp_path, splits=('train',) * 6), tmp_path / 'empty')


def test_bundle_refuses_unsafe_archive_paths(tmp_path):
    z = tmp_path / 'evil.zip'
    with zipfile.ZipFile(z, 'w') as out:
        out.writestr('../evil.png', b'x')
    with pytest.raises(ValueError, match='dangereux'):
        bundle.unpack(z, tmp_path / 'u')


def test_length_scores_are_one_for_identical_and_low_for_displaced_or_empty():
    same = length_scores(RECT, RECT, W, H)
    assert same['f1'] > .99 and same['f1_strict'] > .99 and abs(same['length_ratio'] - 1) < .05
    moved = length_scores([[x1, y1 + 40, x2, y2 + 40] for x1, y1, x2, y2 in RECT], RECT, W, H)
    assert moved['f1'] < .5
    empty = length_scores([], RECT, W, H)
    assert empty['f1'] == 0. and empty['length_ratio'] == 0.


def test_a_model_that_floods_the_plan_with_segments_is_not_credited():
    from segmentation.walls_training.metrics import honest
    flood = [[x, 0, x, H] for x in range(0, W, 6)] + [[0, y, W, y] for y in range(0, H, 6)]      # quadrillage dense
    scores = length_scores(flood, RECT, W, H)
    assert scores['length_ratio'] > 4 and not honest(scores, baseline_f1=0.)
    assert honest(length_scores(RECT, RECT, W, H), baseline_f1=.38)


def test_model_outputs_one_logit_map_per_engine_class():
    out = UNet(base=4, depth=3)(torch.rand(2, 3, 64, 64))
    assert tuple(out.shape) == (2, len(CLASSES), 64, 64) and CLASSES[1] == 'wall'


def test_end_to_end_training_exports_a_valid_onnx_and_a_manifest_the_engine_accepts(tmp_path):
    pytest.importorskip('onnx'); pytest.importorskip('onnxruntime')
    from segmentation.walls_training.train import main
    out = tmp_path / 'run'
    report = main(['--bundle', str(make_bundle(tmp_path)), '--out', str(out), '--size', '128', '--epochs', '3', '--base', '4',
                   '--batch', '2', '--repeat', '2', '--device', 'cpu', '--workers', '0', '--eval-every', '1', '--lr', '3e-3'])
    for name in ('best.pt', 'walls.onnx', 'manifest.json', 'report.json'):
        assert (out / name).is_file()
    assert report['history'][-1]['loss'] < report['history'][0]['loss']
    assert set(report['metrics']) == {'validation', 'test'} and {'f1', 'recall', 'precision', 'dice'} <= set(report['metrics']['test'])
    assert report['baseline_before_training']['test']['f1'] == .38 and 'credible_improvement' in report['verdict']
    manifest = json.loads((out / 'manifest.json').read_text())
    with pytest.raises(ValueError, match='Droits commerciaux non validés : code'):       # AUCUNE revue de droits simulée
        run_onnx.checked_manifest(out / 'walls.onnx', out / 'manifest.json')
    for part in manifest['rights'].values():
        part.update(commercial_use=True, evidence_url='https://example.test/revue', reviewed_by='test')
    approved = out / 'approved.json'; approved.write_text(json.dumps(manifest))
    assert run_onnx.checked_manifest(out / 'walls.onnx', approved)['classes'] == CLASSES        # empreinte, contrat, classes : OK


def test_reconstruct_mask_turns_a_predicted_wall_raster_into_segments(tmp_path):
    from segmentation.walls_training.evaluate import labels_to_segments
    labels = np.zeros((H, W), np.uint8)
    cv2.rectangle(labels, (60, 50), (260, 190), 1, 8)
    png = tmp_path / 'p.png'; plan_png(png)
    record = {'path': str(png), 'width': W, 'height': H}
    segments = labels_to_segments(labels, record, 'a' * 64)
    assert len(segments) >= 4
    assert length_scores(segments, [r for r in RECT if r != RECT[-1]], W, H)['recall'] > .9
