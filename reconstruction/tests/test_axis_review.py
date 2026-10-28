import copy
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient
import pytest

from doemo_reconstruction.axis_review import close_axes, review_axes, valid_reviews
from doemo_reconstruction.geometry import edit, validate, wall
from doemo_reconstruction.export import export_svg, connector_payload, training_records
from doemo_reconstruction.workbench import Workbench, create_app
from test_reconstruction import document
from test_ovh_workbench import ready_project


def pair_doc():
    doc = document()
    first, second = wall([10, 20], [100, 20], 4), wall([100, 26], [10, 26], 4)
    first['id'], second['id'] = 'first', 'second'
    doc['levels'][0]['walls'] = [first, second]
    return doc


def approve(doc):
    for w in doc['levels'][0]['walls']:
        doc = edit(doc, 'L', {'op': 'approve', 'id': w['id']}, 'Dessinateur')
    return doc


def distinct(doc):
    return edit(doc, 'L', {'op': 'distinct_axes', 'id': 'first', 'other_id': 'second',
                          'note': 'Deux cloisons séparées, vérifiées sur le relevé'}, 'Dessinateur')


def test_potential_double_axes_are_reported_without_changing_geometry():
    doc = pair_doc()
    before = copy.deepcopy(doc)
    report = review_axes(doc['levels'][0])
    assert len(report) == 1 and not report[0]['resolved']
    assert report[0]['separation'] == 6 and report[0]['overlap'] == 90
    assert report[0]['relation'] == 'parallel' and doc == before


@pytest.mark.parametrize('second', [
    ([100, 20], [150, 20]),  # One common endpoint is not a double.
    ([105, 20], [150, 20]),  # No joining across a gap.
    ([50, 10], [50, 80]),   # Perpendicular junction.
    ([10, 50], [100, 50]),  # Outside the documented proximity tolerance.
])
def test_distinct_spans_and_junctions_are_not_reported(second):
    assert close_axes(wall([10, 20], [100, 20], 4), wall(*second, 4)) is None


def test_comparison_subtracts_openings_and_never_closes_them():
    first, second = wall([10, 20], [110, 20], 4), wall([40, 24], [70, 24], 4)
    first['openings'] = [{'start': .3, 'end': .6, 'kind': 'door', 'status': 'approved'}]
    assert close_axes(first, second) is None
    second['a'], second['b'] = [10, 24], [110, 24]
    report = close_axes(first, second)
    assert report['overlap'] == pytest.approx(70)
    assert len(report['spans']) == 2
    assert first['openings'][0]['start'] == .3


def test_approved_export_is_blocked_but_review_svg_and_saving_remain_available():
    doc = approve(pair_doc())
    level = doc['levels'][0]
    validate(doc)
    assert '<path' in export_svg(level, approved_only=False)
    with pytest.raises(ValueError, match='Doubles axes'):
        export_svg(level)
    level['floor_validated'] = True
    with pytest.raises(ValueError, match='Doubles axes'):
        connector_payload(doc)
    assert training_records(doc) == []


def test_confirming_distinct_walls_preserves_both_axes_and_records_the_reason():
    doc = approve(pair_doc())
    old_walls = copy.deepcopy(doc['levels'][0]['walls'])
    out = distinct(doc)
    level = out['levels'][0]
    assert level['walls'] == old_walls and level['scale'] is None
    assert review_axes(level)[0]['resolved']
    assert out['history'][-1]['operation']['op'] == 'distinct_axes'
    assert out['history'][-1]['actor'] == 'Dessinateur'
    assert len(training_records(out)) == 2
    assert training_records(out)[0]['axis_reviews'][0]['note'].startswith('Deux cloisons')
    svg = ET.fromstring(export_svg(level))
    paths = svg.findall('.//{http://www.w3.org/2000/svg}path')
    assert len(paths) == 2 and all(p.attrib['stroke'] == '#000000' and p.attrib['fill'] == 'none' for p in paths)
    level['floor_validated'] = True
    assert len(connector_payload(out)['levels'][0]['walls']) == 2


@pytest.mark.parametrize('operation', [
    {'op': 'update', 'id': 'first', 'a': [11, 20], 'b': [101, 20]},
    {'op': 'update', 'id': 'first', 'thickness': 8},
    {'op': 'opening', 'id': 'first', 'start': .4, 'end': .5, 'kind': 'door', 'status': 'approved'},
    {'op': 'split', 'id': 'first', 'fraction': .5},
])
def test_geometry_changes_invalidate_the_distinct_walls_decision(operation):
    doc = distinct(approve(pair_doc()))
    changed = edit(doc, 'L', operation, 'Dessinateur')
    assert not valid_reviews(changed['levels'][0])
    assert changed['levels'][0]['axis_reviews'] == []
    assert changed['history'][-1]['before']['axis_reviews']
    assert all(not p['resolved'] for p in review_axes(changed['levels'][0]))


def test_forged_or_stale_distinction_cannot_approve_superposed_axes():
    doc = distinct(approve(pair_doc()))
    first, second = doc['levels'][0]['walls']
    second['a'], second['b'] = first['a'][:], first['b'][:]
    # Even a matching snapshot cannot label exact duplicates as distinct walls.
    pair = close_axes(first, second)
    doc['levels'][0]['axis_reviews'][0]['snapshots'] = pair['snapshots']
    assert pair['relation'] == 'coincident'
    assert not review_axes(doc['levels'][0])[0]['resolved']
    with pytest.raises(ValueError, match='superposés'):
        distinct(doc)
    with pytest.raises(ValueError, match='Doubles axes'):
        export_svg(doc['levels'][0])


def test_merging_faces_leaves_one_black_axis_and_removes_the_warning():
    doc = pair_doc()
    out = edit(doc, 'L', {'op': 'merge_parallel_faces', 'id': 'first', 'other_id': 'second'}, 'Dessinateur')
    level = out['levels'][0]
    assert len(level['walls']) == 1 and not review_axes(level)
    assert level['walls'][0]['a'] == [10, 23] and level['walls'][0]['b'] == [100, 23]
    assert level['walls'][0]['status'] == 'pending'
    out = approve(out)
    assert len(ET.fromstring(export_svg(out['levels'][0])).findall('.//{http://www.w3.org/2000/svg}path')) == 1


def test_train_only_unambiguous_approved_walls():
    doc = pair_doc()
    doc['levels'][0]['walls'].append(wall([120, 80], [180, 80], 4))
    out = approve(doc)
    records = training_records(out)
    assert len(records) == 1 and records[0]['wall']['a'] == [120, 80]


def test_api_export_guard_and_authenticated_review_author(tmp_path):
    bench = Workbench(tmp_path)
    ids, initial = ready_project(bench)
    doc = approve(pair_doc())
    # Keep the actual fixture's immutable source metadata.
    doc['source'] = initial['source']
    for key in ('id', 'source_page', 'width', 'height', 'unit', 'coordinate', 'reference'):
        doc['levels'][0][key] = initial['levels'][0][key]
    with bench.db() as db:
        db.execute('UPDATE projects SET document=? WHERE id=?', (json.dumps(doc), ids['id']))
    with TestClient(create_app(bench, start_worker=False)) as client:
        headers = {'X-Doemo-User': 'alice'}
        path = '/projects/' + ids['id']
        assert client.get(path + '/export/svg', headers=headers).status_code == 422
        assert client.get(path + '/export/preview', headers=headers).status_code == 200
        reviewed = edit(doc, doc['levels'][0]['id'], {'op': 'distinct_axes', 'id': 'first',
                        'other_id': 'second', 'note': 'Deux murs vérifiés'}, 'Spoofed name')
        response = client.post(path + '/save', headers=headers,
                               json={'expected_version': bench.project('alice', ids['id'])['version'], 'document': reviewed})
        assert response.status_code == 200
        saved = response.json()['document']
        assert saved['levels'][0]['axis_reviews'][0]['validated_by'] == 'alice'
        assert saved['history'][-1]['actor'] == 'alice'
        assert saved['history'][-1]['after']['axis_reviews'][0]['validated_by'] == 'alice'
        assert client.get(path + '/export/svg', headers=headers).status_code == 200


def test_browser_and_python_agree_for_rotated_reversed_open_and_reviewed_axes():
    levels = []
    for angle in (0, 23, 45, 89, 120, 180, 230, 300):
        for reverse in (False, True):
            doc = pair_doc()
            first, second = doc['levels'][0]['walls']
            first['openings'] = [{'kind': 'door', 'start': .3, 'end': .4, 'status': 'approved'}]
            radians = math.radians(angle)
            for w in (first, second):
                for key in ('a', 'b'):
                    x, y = w[key]
                    w[key] = [200+x*math.cos(radians)-y*math.sin(radians),
                              200+x*math.sin(radians)+y*math.cos(radians)]
                if reverse:
                    w['a'], w['b'] = w['b'], w['a']
                    for opening in w['openings']:
                        opening['start'], opening['end'] = 1-opening['end'], 1-opening['start']
            level = doc['levels'][0]
            level['width'] = level['height'] = 400
            levels.append(copy.deepcopy(level))
            out = distinct(doc)
            levels.append(out['levels'][0])
    template = (Path(__file__).parents[1] / 'editor/editor.html').read_text()
    code = 'const distance=(a,b)=>Math.hypot(b[0]-a[0],b[1]-a[1]);\n'
    code += template[template.index('function intervals(w)'):template.index('function pathData')]
    code += "const levels=JSON.parse(require('fs').readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(levels.map(l=>reviewAxes(l))));"
    actual = json.loads(subprocess.run(['node', '-e', code], input=json.dumps(levels),
                                      capture_output=True, text=True, check=True).stdout)
    expected = [review_axes(l) for l in levels]
    def rounded(value):
        if isinstance(value, float):return round(value, 7)
        if isinstance(value, list):return [rounded(v) for v in value]
        if isinstance(value, dict):return {k: rounded(v) for k, v in value.items()}
        return value
    assert rounded(actual) == rounded(expected)
