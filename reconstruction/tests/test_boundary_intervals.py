import math
import random

import pytest

from doemo_reconstruction.geometry import distance, pair_boundaries


def shape(walls):
    return sorted(tuple(round(v, 6) for point in sorted((w['a'], w['b'])) for v in point)
                  for w in walls)


def assert_supported_once(walls):
    used = {}
    for w in walls:
        evidence = w['evidence'][0]
        for source, interval in zip(evidence['sides'], evidence['source_intervals']):
            key = tuple(tuple(p) for p in source)
            assert 0 <= interval[0] < interval[1] <= 1
            for lo, hi in used.setdefault(key, []):
                assert min(hi, interval[1])-max(lo, interval[0]) <= 1e-8
            used[key].append(interval)
        for endpoint, p, q in zip((w['a'], w['b']), *evidence['paired_sides']):
            assert endpoint == pytest.approx([(p[k]+q[k])/2 for k in (0, 1)])


@pytest.mark.parametrize('angle', [0, 30, 45, 89.8, 90, 135, 180])
def test_one_long_face_can_support_two_fragments_without_closing_the_gap(angle):
    theta = math.radians(angle)
    def rotate(p):
        x, y = p
        return [150+x*math.cos(theta)-y*math.sin(theta), 150+x*math.sin(theta)+y*math.cos(theta)]
    lines = [([0, 0], [100, 0]), ([0, 4], [40, 4]), ([60, 4], [100, 4])]
    walls = pair_boundaries([(rotate(a), rotate(b)) for a, b in lines])
    expected = [{'a': rotate([0, 2]), 'b': rotate([40, 2])},
                {'a': rotate([60, 2]), 'b': rotate([100, 2])}]
    assert shape(walls) == shape(expected)
    assert all(w['status'] == 'pending' and w['thickness'] == pytest.approx(4) for w in walls)
    assert_supported_once(walls)


def test_both_fragmented_faces_keep_the_intersection_not_the_union():
    walls = pair_boundaries([([0, 0], [45, 0]), ([55, 0], [100, 0]),
                             ([0, 4], [40, 4]), ([60, 4], [100, 4])])
    assert shape(walls) == [(0., 2., 40., 2.), (60., 2., 100., 2.)]
    assert_supported_once(walls)


def test_long_face_retains_both_tails_after_pairing_its_middle():
    walls = pair_boundaries([([0, 0], [100, 0]), ([30, 2], [70, 2]),
                             ([0, 4], [30, 4]), ([70, 4], [100, 4])])
    assert shape(walls) == [(0., 2., 30., 2.), (30., 1., 70., 1.), (70., 2., 100., 2.)]
    assert_supported_once(walls)


def test_consumed_overlap_is_not_reused_by_a_second_pair():
    walls = pair_boundaries([([0, 0], [100, 0]), ([0, 2], [50, 2]), ([25, 4], [100, 4])])
    assert shape(walls) == [(0., 1., 50., 1.), (50., 2., 100., 2.)]
    assert_supported_once(walls)


def test_slightly_nonparallel_faces_use_both_actual_endpoints():
    walls = pair_boundaries([([0, 0], [100, 0]), ([0, 4], [100, 4.4])])
    assert len(walls) == 1
    assert_supported_once(walls)
    # The median follows the mild taper instead of using a constant offset.
    w = walls[0]
    assert abs(w['a'][1]-w['b'][1]) > .19
    assert w['thickness'] == pytest.approx(4.2, abs=.001)


def test_input_permutation_direction_and_exact_duplicates_do_not_change_geometry():
    original = [([0, 0], [100, 0]), ([0, 4], [40, 4]), ([60, 4], [100, 4])]
    expected = shape(pair_boundaries(original))
    rng = random.Random(547)
    for _ in range(30):
        lines = [(a, b) if rng.choice((True, False)) else (b, a) for a, b in original]
        lines.extend(lines[:2])
        rng.shuffle(lines)
        assert shape(pair_boundaries(lines)) == expected


def test_short_unmatched_tails_are_not_extended_or_connected():
    walls = pair_boundaries([([0, 0], [100, 0]), ([5, 4], [40, 4]), ([60, 4], [95, 4])])
    assert shape(walls) == [(5., 2., 40., 2.), (60., 2., 95., 2.)]
    assert sum(distance(w['a'], w['b']) for w in walls) == pytest.approx(70)


def test_unqualified_pairing_does_not_claim_probability_or_semantic_detection():
    walls = pair_boundaries([([0, 0], [100, 0]), ([0, 4], [100, 4])])
    assert walls[0]['confidence'] == 0
    assert walls[0]['evidence'][0]['semantic_status'] == 'unknown'
    assert walls[0]['status'] == 'pending'


def test_native_pdf_strokes_keep_their_own_fragments_and_gap(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    from doemo_reconstruction.extract import reconstruct
    writer = PdfWriter()
    page = writer.add_blank_page(120, 100)
    stream = DecodedStreamObject()
    stream.set_data(b'0 0 0 RG 10 20 m 110 20 l S 10 24 m 50 24 l S 70 24 m 110 24 l S')
    page[NameObject('/Contents')] = writer._add_object(stream)
    path = tmp_path / 'fragmented.pdf'
    with path.open('wb') as out:
        writer.write(out)
    doc = reconstruct(path)
    level = doc['levels'][0]
    assert level['method'] == 'vector'
    assert shape(level['walls']) == [(10., 76., 50., 76.), (10., 80., 110., 80.), (70., 76., 110., 76.)]
    assert level['scale'] is None and level['source_page'] == 1
