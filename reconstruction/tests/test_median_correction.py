import copy

import pytest

from doemo_reconstruction.geometry import axis_points, edit, merge_parallel_faces, wall
from test_reconstruction import document


def test_human_selected_parallel_faces_become_one_pending_axis():
    first, second = wall([10, 20], [100, 20], 1), wall([100, 26], [10, 26], 1)
    first['status'] = second['status'] = 'approved'
    before = copy.deepcopy([first, second])
    result = merge_parallel_faces(first, second)
    assert len(result) == 1
    assert result[0]['a'] == [10, 23] and result[0]['b'] == [100, 23]
    assert result[0]['thickness'] == 6 and result[0]['status'] == 'pending'
    assert result[0]['method'] == 'manual_parallel_faces'
    assert [first, second] == before


def test_unmatched_tails_are_preserved_instead_of_extending_the_median():
    first, second = wall([10, 20], [110, 20], 1), wall([40, 24], [80, 24], 1)
    result = merge_parallel_faces(first, second)
    assert len(result) == 3
    assert axis_points(result[0]) == [[40, 22], [80, 22]]
    assert [axis_points(w) for w in result[1:]] == [[[10, 20], [40, 20]], [[80, 20], [110, 20]]]
    assert len({w['id'] for w in result}) == 3
    assert all(w['status'] == 'pending' for w in result)


def test_diagonal_correction_stays_diagonal():
    result = merge_parallel_faces(wall([10, 10], [60, 60], 1), wall([12, 8], [62, 58], 1))
    assert len(result) == 1
    assert result[0]['a'] == pytest.approx([11, 9])
    assert result[0]['b'] == pytest.approx([61, 59])
    assert result[0]['thickness'] == pytest.approx(8**.5)


@pytest.mark.parametrize('other', [([110, 24], [150, 24]), ([10, 20], [10, 70]),
                                  ([10, 20], [100, 20]), ([10, 70], [100, 70])])
def test_ambiguous_parallel_merge_is_rejected(other):
    with pytest.raises(ValueError):
        merge_parallel_faces(wall([10, 20], [100, 20], 1), wall(*other, 1))


def test_existing_openings_are_transferred_pending_without_mutating_sources():
    first, second = wall([10, 20], [100, 20], 1), wall([10, 24], [100, 24], 1)
    first['openings'] = [{'start': .3, 'end': .5, 'kind': 'door', 'status': 'approved'}]
    before = copy.deepcopy(first)
    result = merge_parallel_faces(first, second)
    assert result[0]['openings'] == [{'start': .3, 'end': .5, 'kind': 'door', 'status': 'pending'}]
    assert result[0]['evidence'][0]['opening_transfer'][0]['sources'][0]['wall_id'] == first['id']
    assert first == before


def test_correction_is_journaled_and_does_not_alter_other_walls_or_scale():
    doc = document()
    first = doc['levels'][0]['walls'][0]
    other = wall([10, 24], [100, 24], 1)
    untouched = wall([120, 60], [180, 60], 6)
    untouched['status'] = 'approved'
    doc['levels'][0]['walls'].extend([other, untouched])
    out = edit(doc, 'L', {'op': 'merge_parallel_faces', 'id': first['id'], 'other_id': other['id']}, 'Dessinateur')
    assert len(out['levels'][0]['walls']) == 2
    assert out['levels'][0]['walls'][0] == untouched
    assert out['levels'][0]['scale'] is None
    assert out['history'][-1]['actor'] == 'Dessinateur'
    assert out['revision'] == 1 and doc['revision'] == 0
