"""Scan cleanup: fragments of one wall are joined, doors and distinct walls are not, page frames are dropped."""
import math

import pytest
from PIL import Image

from doemo_reconstruction.extract import reconstruct, MERGE_GAP_FRACTION, MERGE_OFFSET_FRACTION
from doemo_reconstruction.geometry import (distance, drop_page_frames, merge_collinear_fragments, pair_boundaries,
                                           validate, wall)


def raster(a, b, thickness=6., **kwargs):
    return wall(a, b, thickness, method='parallel_boundaries', confidence=0.,
                evidence=[{'algorithm': 'unused_boundary_intervals/1', 'lines': [0, 1]}], **kwargs)


def lengths(walls):
    return sorted(round(distance(w['a'], w['b']), 3) for w in walls)


def test_overlapping_and_touching_fragments_become_one_wall_with_all_evidence():
    walls = [raster([0, 100], [50, 100]), raster([40, 100.5], [120, 100.5]), raster([120, 100], [200, 100])]
    merged, report = merge_collinear_fragments(walls, 3., 5.)
    assert len(merged) == 1 and report == {'input': 3, 'output': 1, 'merged_groups': 1}
    w = merged[0]
    assert math.isclose(w['a'][0], 0, abs_tol=1e-6) and math.isclose(w['b'][0], 200, abs_tol=1e-6)
    assert math.isclose(w['a'][1], 100.1667, abs_tol=.2)
    assert w['status'] == 'pending' and w['method'] == 'parallel_boundaries' and w['openings'] == []
    record = w['evidence'][-1]
    assert record['algorithm'] == 'collinear_fragment_merge/1'
    assert sorted(record['merged_wall_ids']) == sorted(x['id'] for x in walls)
    assert len(w['evidence']) == 4          # three original evidences + the merge record


def test_a_gap_wider_than_max_gap_is_never_bridged_so_doors_stay_open():
    walls = [raster([0, 50], [100, 50]), raster([120, 50], [220, 50])]      # 20 unit opening
    merged, report = merge_collinear_fragments(walls, 3., 5.)
    assert len(merged) == 2 and report['merged_groups'] == 0
    assert lengths(merged) == [100., 100.]


def test_small_scan_gap_is_joined():
    merged, _ = merge_collinear_fragments([raster([0, 50], [100, 50]), raster([103, 50], [200, 50])], 3., 5.)
    assert len(merged) == 1 and math.isclose(distance(merged[0]['a'], merged[0]['b']), 200)


def test_parallel_but_offset_walls_stay_distinct():
    merged, _ = merge_collinear_fragments([raster([0, 50], [100, 50]), raster([0, 70], [100, 70])], 3., 5.)
    assert len(merged) == 2


def test_very_different_thickness_is_not_merged():
    merged, _ = merge_collinear_fragments([raster([0, 50], [100, 50], 4.), raster([100, 50], [200, 50], 14.)], 3., 5.)
    assert len(merged) == 2


def test_corner_is_not_merged():
    merged, _ = merge_collinear_fragments([raster([0, 0], [100, 0]), raster([100, 0], [100, 100])], 3., 5.)
    assert len(merged) == 2


def test_oblique_fragments_are_merged_along_their_own_axis():
    d = math.sqrt(.5)
    merged, _ = merge_collinear_fragments([raster([0, 0], [50*d, 50*d]), raster([50*d+1, 50*d+1], [100*d, 100*d])], 3., 5.)
    assert len(merged) == 1 and math.isclose(distance(merged[0]['a'], merged[0]['b']), 100, abs_tol=2.)


def test_only_pending_raster_candidates_are_touched_and_order_is_kept():
    manual = wall([0, 10], [100, 10], 5., method='manual')
    approved = raster([0, 20], [100, 20]); approved['status'] = 'approved'
    opened = raster([0, 30], [100, 30]); opened['openings'] = [{'kind': 'door', 'status': 'pending'}]
    twins = [raster([0, 40], [60, 40]), raster([60, 40], [120, 40])]
    out, _ = merge_collinear_fragments([manual, approved, opened] + twins, 3., 5.)
    assert out[:3] == [manual, approved, opened] and len(out) == 4


def test_endpoints_are_clamped_to_the_page_and_result_validates():
    walls = [raster([0, 100], [60, 100]), raster([60, 100], [200.2, 100])]
    merged, _ = merge_collinear_fragments(walls, 3., 5., bounds=(200., 200.))
    assert merged[0]['b'][0] == 200.
    validate({'schema': 'doemo.architecture/1', 'revision': 0,
              'levels': [{'id': 'p', 'width': 200., 'height': 200., 'walls': merged}]})


def test_merging_is_idempotent_and_ignores_unrelated_walls():
    walls = [raster([0, 5], [80, 5]), raster([80, 5], [160, 5]), raster([0, 90], [10, 90])]
    once, _ = merge_collinear_fragments(walls, 3., 5.)
    twice, report = merge_collinear_fragments(once, 3., 5.)
    assert len(once) == 2 and len(twice) == 2 and report['merged_groups'] == 0


@pytest.mark.parametrize('args', [(-1., 5.), (3., float('nan'))])
def test_invalid_tolerances_are_rejected(args):
    with pytest.raises(ValueError):
        merge_collinear_fragments([], *args)


def test_page_frame_lines_are_dropped_but_inner_and_decided_walls_are_not():
    frame_top, frame_left = raster([54, 33], [1141, 34]), raster([54, 33], [55, 800])
    inner_long = raster([300, 400], [1100, 400])                  # long but in the middle of the sheet
    near_edge_short = raster([60, 40], [200, 40])                 # near the edge but not a frame
    decided = raster([54, 33], [1141, 33]); decided['status'] = 'approved'
    kept, dropped = drop_page_frames([frame_top, frame_left, inner_long, near_edge_short, decided], 1190., 842.)
    assert dropped == 2 and kept == [inner_long, near_edge_short, decided]


def test_reconstruct_joins_scan_fragments_keeps_the_door_and_drops_the_frame(tmp_path, monkeypatch):
    monkeypatch.setattr('doemo_reconstruction.extract.ocr_texts', lambda *args: [])
    path = tmp_path / 'scan.png'
    Image.new('RGB', (1000, 800), 'white').save(path)
    sides = []
    def face(y, x0, x1):
        sides.extend([([x0, y], [x1, y]), ([x0, y+8], [x1, y+8])])    # one wall = two faces 8 apart
    face(300, 100, 250); face(300, 252, 400); face(300, 520, 700)    # scan cut + a real 120-unit door gap
    face(20, 40, 970)                                                  # sheet frame
    monkeypatch.setattr('doemo_reconstruction.extract.raster_lines', lambda *args, **kw: sides)
    level = reconstruct(path)['levels'][0]
    walls = level['walls']
    assert len(walls) == 2 and lengths(walls) == [180., 300.]
    assert any('Nettoyage du scan' in text for text in level['warnings'])
    assert any('cadre' in text for text in level['warnings'])
    assert MERGE_OFFSET_FRACTION == .004 and MERGE_GAP_FRACTION == .006
