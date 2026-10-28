import copy
import json

import pikepdf
import pytest

from doemo_pdf.levels import (clip_preview, contour_path, level_path, new_document,
                              pdf_path, read_document, validate_document)
from doemo_pdf.pdf import vector_stats


def source_pdf(path, pages=1, rotated=False):
    pdf = pikepdf.Pdf.new()
    for index in range(pages):
        page = pdf.add_blank_page(page_size=(200, 200))
        page.Contents = pdf.make_stream(f'1 0 0 rg 0 0 200 200 re f\n0 0 1 RG 2 w 0 {80+index} m 200 80 l S\n'.encode())
        if rotated: page.obj.Rotate = 90
    pdf.save(path)
    return path


def contour(points, name='c1', role='include'):
    return {'id': name, 'role': role, 'fill_rule': 'nonzero',
            'nodes': [{'x': x, 'y': y} for x, y in points]}


def document(source, contours):
    doc = new_document(source)
    doc['levels'] = [{'id': 'rdc', 'name': 'RDC', 'page': 1, 'color': '#2563eb',
                      'contours': contours, 'vei_ids': []}]
    return doc


SHAPES = [
    ('rectangle', [(20, 20), (180, 20), (180, 180), (20, 180)], 25600),
    ('L', [(20, 20), (180, 20), (180, 80), (80, 80), (80, 180), (20, 180)], 15600),
    ('U', [(20, 20), (180, 20), (180, 180), (130, 180), (130, 70), (70, 70), (70, 180), (20, 180)], 19000),
    ('diagonal', [(20, 20), (180, 20), (100, 180)], 12800),
]


@pytest.mark.parametrize('name,points,area', SHAPES)
def test_nonrectangular_clip_keeps_source_operators_and_uses_actual_path(tmp_path, name, points, area):
    source = source_pdf(tmp_path/'source.pdf')
    original = source.read_bytes()
    doc = document(source, [contour(points)])
    assert abs(level_path(doc['levels'][0]).area - area) < 0.001
    output = tmp_path/f'{name}.pdf'
    report = clip_preview(source, doc, output, 'PE', 'rdc')
    assert report['source_streams_unchanged'] and report['source_unchanged']
    with pikepdf.Pdf.open(output) as pdf, pikepdf.Pdf.open(source) as original_pdf:
        assert pdf.pages[0].Resources.XObject.Source.read_bytes() == original_pdf.pages[0].Contents.read_bytes()
        assert b'W n' in pdf.pages[0].Contents.read_bytes()
        assert vector_stats(pdf.pages[0])['image_resources'] == 0
        assert vector_stats(pdf.pages[0])['path_paint_operators'] == 2
    assert source.read_bytes() == original


def test_cubic_contour_remains_a_curve(tmp_path):
    source = source_pdf(tmp_path/'source.pdf')
    c = contour([(20, 20), (180, 20), (180, 180), (20, 180)])
    c['nodes'][1]['out'] = [80, 40]
    c['nodes'][2]['in'] = [80, 160]
    doc = document(source, [c])
    validated = validate_document(source, doc)
    assert validated['document']['levels'][0]['contours'][0]['nodes'] == c['nodes']
    assert b' c\n' in pdf_path(level_path(doc['levels'][0]))
    assert not level_path(doc['levels'][0]).contains((170, 100))
    clip_preview(source, doc, tmp_path/'curve.pdf', 'PE', 'rdc')


def test_disconnected_zones_union_overlap_and_global_exclusion(tmp_path):
    source = source_pdf(tmp_path/'source.pdf')
    a = contour([(10, 10), (100, 10), (100, 100), (10, 100)])
    b = contour([(50, 10), (150, 10), (150, 100), (50, 100)], 'c2')
    island = contour([(160, 160), (190, 160), (190, 190), (160, 190)], 'c3')
    hole = contour([(60, 30), (90, 30), (90, 70), (60, 70)], 'hole', 'exclude')
    doc = document(source, [a, b, island, hole])
    shape = level_path(doc['levels'][0])
    assert shape.area == pytest.approx(140*90+30*30-30*40)
    assert shape.contains((70, 20))  # overlap is included, not XOR
    assert shape.contains((170, 170))
    assert not shape.contains((75, 50))  # cut through the overlap of TWO additions
    assert not shape.contains((130, 140))
    clip_preview(source, doc, tmp_path/'compound.pdf', 'PE', 'rdc')


def test_fill_rules_for_a_double_wound_path():
    c = contour([(10, 10), (90, 10), (90, 90), (10, 90)]*2)
    assert contour_path(c).contains((50, 50))
    c['fill_rule'] = 'evenodd'
    assert not contour_path(c).contains((50, 50))


def test_pi_preserves_all_pages_and_never_applies_pe_clip(tmp_path):
    source = source_pdf(tmp_path/'source.pdf', pages=2, rotated=True)
    doc = document(source, [contour(SHAPES[1][1])])
    doc['levels'].append({**copy.deepcopy(doc['levels'][0]), 'id': 'r1', 'page': 2,
                          'contours': [contour(SHAPES[2][1], 'c2')]})
    output = tmp_path/'pi.pdf'
    result = clip_preview(source, doc, output, 'PI', 'rdc')
    assert result['page_count'] == 2
    with pikepdf.Pdf.open(source) as original, pikepdf.Pdf.open(output) as exported:
        for before, after in zip(original.pages, exported.pages):
            assert after.obj.Rotate == before.obj.Rotate == 90
            assert list(after.cropbox) == list(before.cropbox)
            assert after.Resources.XObject.Source.read_bytes() == before.Contents.read_bytes()
            assert b'W' not in after.Contents.read_bytes()
    pe = tmp_path/'pe2.pdf'
    clip_preview(source, doc, pe, 'PE', 'r1')
    with pikepdf.Pdf.open(pe) as pdf: assert len(pdf.pages) == 1


def test_boundary_vei_warns_without_claiming_whole_object_preservation(tmp_path):
    source = source_pdf(tmp_path/'source.pdf')
    doc = document(source, [contour(SHAPES[0][1])])
    doc['markers'] = [{'id': 'near', 'page': 1, 'point': [21, 100]},
                      {'id': 'outside', 'page': 1, 'point': [190, 100]},
                      {'id': 'unknown', 'page': 1, 'point': None}]
    doc['levels'][0]['vei_ids'] = ['near', 'outside', 'unknown']
    result = validate_document(source, doc)
    assert [x['position'] for x in result['report']['levels'][0]['vei_checks']] == ['near_boundary', 'outside', 'unknown']
    assert 'partiellement masqués' in result['report']['warning']
    assert result['report']['levels'][0]['boundary_objects'] == 'manual_review_required'


@pytest.mark.parametrize('change', ['hash', 'box', 'rotation', 'unit', 'pages'])
def test_incompatible_source_never_reuses_coordinates(tmp_path, change):
    source = source_pdf(tmp_path/'source.pdf')
    doc = document(source, [contour(SHAPES[0][1])])
    if change == 'hash': doc['source']['sha256'] = '0'*64
    elif change == 'box': doc['source']['pages'][0]['crop_box'][0] = 1
    elif change == 'rotation': doc['source']['pages'][0]['rotation'] = 90
    elif change == 'unit': doc['source']['pages'][0]['user_unit'] = 2
    else: doc['source']['pages'].append(copy.deepcopy(doc['source']['pages'][0]))
    with pytest.raises(ValueError, match='incompatible'): validate_document(source, doc)


def test_exact_json_roundtrip_and_no_overwrite(tmp_path):
    source = source_pdf(tmp_path/'source.pdf')
    doc = document(source, [contour([(20.123456789, 20.1), (180, 20), (170.25, 170.75)])])
    saved = tmp_path/'levels.json'; saved.write_text(json.dumps(doc))
    assert validate_document(source, read_document(saved))['document'] == doc
    output = tmp_path/'keep.pdf'; output.write_bytes(b'keep')
    with pytest.raises(ValueError): clip_preview(source, doc, output, 'PE', 'rdc')
    assert output.read_bytes() == b'keep'


@pytest.mark.parametrize('value', [float('nan'), float('inf'), True, '25'])
def test_invalid_coordinates_rejected(tmp_path, value):
    source = source_pdf(tmp_path/'source.pdf')
    doc = document(source, [contour(SHAPES[0][1])])
    doc['levels'][0]['contours'][0]['nodes'][0]['x'] = value
    with pytest.raises(ValueError, match='Coordonnée'): validate_document(source, doc)
