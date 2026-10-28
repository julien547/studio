import copy
import json
from pathlib import Path
import random
import subprocess
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from doemo_reconstruction.geometry import (
    axis_points, edit, median_openings, merge_parallel_faces, project_openings,
    solid_intervals, wall,
)
from doemo_reconstruction.export import connector_payload, export_svg, training_records
from test_reconstruction import document
from test_ovh_workbench import ready_project
from doemo_reconstruction.workbench import Workbench, create_app


def opening(start, end, kind='door'):
    return {'start': start, 'end': end, 'kind': kind, 'status': 'approved'}


def faces():
    first, second = wall([10, 20], [110, 20], 4), wall([10, 24], [110, 24], 4)
    first['id'], second['id'] = 'first', 'second'
    return first, second


@pytest.mark.parametrize('interval,expected', [
    ((0, 1), (.2, .4)), ((1, 0), (.6, .8)),
    ((.3, .7), (0, .25)), ((.7, .3), (.75, 1)),
    ((0, .3), (2/3, 1)), ((.5, 1), None),
])
def test_opening_projection_preserves_orientation_and_clips_at_boundaries(interval, expected):
    first, _ = faces()
    first['openings'] = [opening(.2, .4)]
    result = project_openings(first, *interval)
    if expected is None:
        assert result == []
    else:
        index, projected = result[0]
        assert index == 0 and projected['status'] == 'pending'
        assert (projected['start'], projected['end']) == pytest.approx(expected)
    assert first['openings'][0]['status'] == 'approved'


def test_matching_openings_on_reversed_faces_remain_one_gap_with_both_sources():
    first, second = faces()
    first['openings'] = [opening(.2, .4)]
    second['a'], second['b'] = second['b'], second['a']
    second['openings'] = [opening(.6, .8)]
    result = merge_parallel_faces(first, second)[0]
    assert len(result['openings']) == 1
    gap = result['openings'][0]
    assert (gap['start'], gap['end']) == pytest.approx((.2, .4))
    audit = result['evidence'][0]['opening_transfer'][0]
    assert {s['wall_id'] for s in audit['sources']} == {'first', 'second'}
    assert not audit['type_conflict'] and gap['status'] == 'pending'


def test_overlapping_gaps_union_but_positive_solid_intervals_are_never_removed():
    first, second = faces()
    first['openings'] = [opening(.1, .2), opening(.6, .7)]
    second['openings'] = [opening(.15, .3), opening(.700001, .8)]
    result = merge_parallel_faces(first, second)[0]
    assert [(o['start'], o['end']) for o in result['openings']] == [(.1, .3), (.6, .7), (.700001, .8)]
    assert (.7, .700001) in solid_intervals(result)
    assert all(o['status'] == 'pending' for o in result['openings'])


def test_conflicting_types_remain_an_explicit_pending_gap_with_source_evidence():
    first, second = faces()
    first['openings'] = [opening(.2, .4, 'door')]
    second['openings'] = [opening(.3, .5, 'window')]
    result = merge_parallel_faces(first, second)[0]
    assert result['openings'] == [{'start': .2, 'end': .5, 'kind': 'passage', 'status': 'pending'}]
    audit = result['evidence'][0]['opening_transfer'][0]
    assert audit['type_conflict'] and audit['source_kinds'] == ['door', 'window']
    assert [s['source_interval'] for s in audit['sources']] == [[.2, .4], [.3, .5]]


def test_opening_crossing_the_overlap_boundary_is_kept_on_axis_and_unmatched_tail():
    first = wall([0, 20], [100, 20], 4)
    second = wall([30, 24], [70, 24], 4)
    first['openings'] = [opening(.2, .4), opening(.8, .9, 'window')]
    before = copy.deepcopy([first, second])
    center, left, right = merge_parallel_faces(first, second)
    assert center['a'] == [30, 22] and center['b'] == [70, 22]
    assert center['openings'][0]['start'] == 0
    assert center['openings'][0]['end'] == pytest.approx(.25)
    actual = [axis_points(w, lo, hi) for w in (center, left, right) for lo, hi in solid_intervals(w)]
    expected = [[[40, 22], [70, 22]], [[0, 20], [20, 20]],
                [[70, 20], [80, 20]], [[90, 20], [100, 20]]]
    for segment, wanted in zip(actual, expected, strict=True):
        for point, target in zip(segment, wanted):
            assert point == pytest.approx(target)
    assert all(o['status'] == 'pending' for w in (center, left, right) for o in w['openings'])
    assert [first, second] == before


def test_full_overlap_excluded_by_openings_refuses_merge_without_changes():
    first, second = faces()
    first['openings'] = [opening(0, .5)]
    second['openings'] = [opening(.5, 1)]
    before = copy.deepcopy([first, second])
    with pytest.raises(ValueError, match='aucune portion pleine'):
        merge_parallel_faces(first, second)
    assert [first, second] == before


def test_malformed_overlapping_source_openings_are_not_silently_repaired():
    first, second = faces()
    first['openings'] = [opening(.1, .4), opening(.3, .5)]
    with pytest.raises(ValueError, match='Ouvertures'):
        merge_parallel_faces(first, second)


def test_review_each_transferred_opening_then_wall_before_svg_illustrator_or_learning():
    doc = document()
    first, second = faces()
    first['openings'] = [opening(.2, .4)]
    doc['levels'][0]['walls'] = [first, second]
    out = edit(doc, 'L', {'op': 'merge_parallel_faces', 'id': 'first', 'other_id': 'second'}, 'Dessinateur')
    center = out['levels'][0]['walls'][0]
    assert '<path' not in export_svg(out['levels'][0])
    assert training_records(out) == []
    with pytest.raises(ValueError, match='ouvertures'):
        edit(out, 'L', {'op': 'approve', 'id': center['id']}, 'Dessinateur')
    out = edit(out, 'L', {'op': 'approve_opening', 'id': center['id'], 'index': 0}, 'Dessinateur')
    assert out['levels'][0]['walls'][0]['status'] == 'pending'
    out = edit(out, 'L', {'op': 'approve', 'id': center['id']}, 'Dessinateur')
    out['levels'][0]['floor_validated'] = True
    svg = ET.fromstring(export_svg(out['levels'][0]))
    paths = svg.findall('.//{http://www.w3.org/2000/svg}path')
    assert len(paths) == 2
    assert all(p.attrib['stroke'] == '#000000' and p.attrib['fill'] == 'none' for p in paths)
    payload = connector_payload(out)['levels'][0]['walls'][0]
    assert payload['paths'] == [[[10, 22], [30, 22]], [[50, 22], [110, 22]]]
    records = training_records(out)
    assert len(records) == 1 and records[0]['validated_by'] == 'Dessinateur'
    assert records[0]['wall']['evidence'][0]['opening_transfer']
    assert out['levels'][0]['scale'] is None
    assert doc['revision'] == 0


def test_ovh_save_reload_keeps_pending_openings_and_refuses_premature_approval(tmp_path):
    bench = Workbench(tmp_path)
    ids, doc = ready_project(bench)
    first, second = faces()
    first['openings'] = [opening(.2, .4)]
    level = doc['levels'][0]
    level['walls'] = [first, second]
    with bench.db() as db:
        db.execute('UPDATE projects SET document=? WHERE id=?', (json.dumps(doc), ids['id']))
    out = edit(doc, level['id'], {'op': 'merge_parallel_faces', 'id': 'first', 'other_id': 'second'}, 'alice')
    with TestClient(create_app(bench, start_worker=False)) as client:
        headers = {'X-Doemo-User': 'alice'}
        path = '/projects/' + ids['id']
        version = bench.project('alice', ids['id'])['version']
        response = client.post(path + '/save', headers=headers, json={'expected_version': version, 'document': out})
        assert response.status_code == 200
        saved = client.get(path, headers=headers).json()
        restored = saved['document']
        center = restored['levels'][0]['walls'][0]
        assert center['openings'][0]['status'] == 'pending'
        assert center['evidence'][0]['opening_transfer'] == out['levels'][0]['walls'][0]['evidence'][0]['opening_transfer']
        bad = copy.deepcopy(restored)
        bad['levels'][0]['walls'][0]['status'] = 'approved'
        assert client.post(path + '/save', headers=headers,
                           json={'expected_version': saved['version'], 'document': bad}).status_code == 422
        reviewed = edit(restored, level['id'], {'op': 'approve_opening', 'id': center['id'], 'index': 0}, 'alice')
        reviewed = edit(reviewed, level['id'], {'op': 'approve', 'id': center['id']}, 'alice')
        assert client.post(path + '/save', headers=headers,
                           json={'expected_version': saved['version'], 'document': reviewed}).status_code == 200
        svg = client.get(path + '/export/svg', headers=headers).json()['content']
        assert len(ET.fromstring(svg).findall('.//{http://www.w3.org/2000/svg}path')) == 2


def generated_cases():
    rng = random.Random(361)
    cases = []
    for _ in range(40):
        pair = faces()
        for w in pair:
            cuts = sorted(rng.sample(range(1, 100), 8))
            w['openings'] = [opening(a/100, b/100, rng.choice(['door', 'window', 'passage']))
                             for a, b in zip(cuts[::2], cuts[1::2])]
        ranges = [rng.choice([[0., 1.], [1., 0.], [.2, .8], [.8, .2]]) for _ in pair]
        cases.append((pair, ranges))
    return cases


def test_union_preserves_exactly_the_observed_gaps_for_both_orientations():
    for pair, ranges in generated_cases():
        openings, _ = median_openings(pair, ranges)
        observed_cuts = [max(0., min(1., (o[k]-start)/(end-start)))
                         for w, (start, end) in zip(pair, ranges)
                         for o in w['openings'] for k in ('start', 'end')]
        cuts = sorted({0., 1., *observed_cuts, *(o[k] for o in openings for k in ('start', 'end'))})
        for lo, hi in zip(cuts, cuts[1:]):
            t = (lo+hi)/2
            expected = any(o['start'] < start+(end-start)*t < o['end']
                           for w, (start, end) in zip(pair, ranges) for o in w['openings'])
            assert any(o['start'] < t < o['end'] for o in openings) == expected


def test_javascript_and_python_project_and_union_the_same_openings():
    template = (Path(__file__).parents[1] / 'editor/editor.html').read_text()
    code = 'const distance=(a,b)=>Math.hypot(b[0]-a[0],b[1]-a[1]);\n'
    code += template[template.index('function intervals(w)'):template.index('// END OPENING TRANSFER')]
    code += "const cases=JSON.parse(require('fs').readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(cases.map(([walls,ranges])=>medianOpenings(walls,ranges))));"
    cases = generated_cases()
    actual = json.loads(subprocess.run(['node', '-e', code], input=json.dumps(cases),
                                      text=True, capture_output=True, check=True).stdout)
    expected = [list(median_openings(pair, ranges)) for pair, ranges in cases]
    def rounded(value):
        if isinstance(value, float):return round(value, 10)
        if isinstance(value, list):return [rounded(v) for v in value]
        if isinstance(value, dict):return {k: rounded(v) for k, v in value.items()}
        return value
    assert rounded(actual) == rounded(expected)
