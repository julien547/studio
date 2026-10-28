"""Real generated PDFs: paint semantics, coordinates, gaps and mixed pages."""
import base64
import io
import xml.etree.ElementTree as ET

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfWriter
from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                           FloatObject, NameObject, NumberObject, RectangleObject)

from doemo_reconstruction.extract import reconstruct
from doemo_reconstruction.geometry import validate
from doemo_reconstruction.export import export_svg


@pytest.fixture(autouse=True)
def no_external_ocr(monkeypatch):
    monkeypatch.setattr('doemo_reconstruction.extract.ocr_texts', lambda *args: [])


def pdf(tmp_path, content, *, resources=None, crop=None, rotation=0, size=(240, 160)):
    writer = PdfWriter()
    page = writer.add_blank_page(*size)
    stream = DecodedStreamObject()
    stream.set_data(content)
    page[NameObject('/Contents')] = writer._add_object(stream)
    if resources:
        page[NameObject('/Resources')] = resources(writer)
    if crop:
        page.cropbox = RectangleObject(crop)
    if rotation:
        page.rotate(rotation)
    path = tmp_path / 'generated.pdf'
    writer.write(path)
    doc = reconstruct(path)
    validate(doc)
    return doc['levels'][0]


def endpoints(w):
    return sorted((w['a'], w['b']))


def test_one_native_stroke_is_one_axis_with_unknown_physical_thickness(tmp_path):
    level = pdf(tmp_path, b'8 w 10 20 m 100 20 l S')
    assert level['method'] == 'vector' and len(level['walls']) == 1
    w = level['walls'][0]
    assert endpoints(w) == [[10, 140], [100, 140]]
    assert w['thickness'] is None and w['confidence'] == 0 and w['status'] == 'pending'
    assert w['evidence'][0]['stroke_width_pdf_local'] == 8
    assert w['evidence'][0]['semantic_status'] == 'unknown'
    assert level['scale'] is None
    assert not ET.fromstring(export_svg(level)).findall('.//{http://www.w3.org/2000/svg}path')
    w['status'] = 'approved'
    paths = ET.fromstring(export_svg(level)).findall('.//{http://www.w3.org/2000/svg}path')
    assert len(paths) == 1 and paths[0].get('stroke') == '#000000'
    assert paths[0].get('fill') == 'none' and 'Z' not in paths[0].get('d').upper()
    assert paths[0].get('stroke-dasharray') is None


def test_subpaths_keep_real_gap_and_polyline_corner_without_joining(tmp_path):
    level = pdf(tmp_path, b'2 w 10 20 m 50 20 l 50 50 l 70 20 m 110 20 l S')
    assert sorted(endpoints(w) for w in level['walls']) == [
        [[10, 140], [50, 140]], [[50, 110], [50, 140]], [[70, 140], [110, 140]]]


def test_exact_repaint_is_one_axis_with_both_sources(tmp_path):
    level = pdf(tmp_path, b'2 w 10 20 m 100 20 l S 100 20 m 10 20 l S')
    assert len(level['walls']) == 1
    assert len(level['walls'][0]['evidence']) == 2
    assert len(level['raw_vectors']) == 2


@pytest.mark.parametrize('paint', [b'f', b'S', b'B'])
def test_long_rectangle_gives_one_median_not_its_edges(tmp_path, paint):
    level = pdf(tmp_path, b'0 g 0 G 1 w 10 20 100 6 re '+paint)
    assert len(level['walls']) == 1
    w = level['walls'][0]
    assert endpoints(w) == [[10, 137], [110, 137]]
    assert w['thickness'] == 6 and w['method'] == 'native_pdf_rectangle'
    assert w['status'] == 'pending' and w['confidence'] == 0


@pytest.mark.parametrize('content,reason', [
    (b'[10 4] 0 d 10 20 m 200 20 l S', 'dashed_or_unknown_stroke'),
    (b'1 0 0 RG 10 20 m 200 20 l S', 'non_dark_or_transparent_paint'),
    (b'1 g 10 20 100 6 re f', 'non_dark_or_transparent_paint'),
    (b'10 20 m 50 80 100 80 200 20 c S', 'curved_path'),
    (b'30 10 50 40 re W n 10 20 m 200 20 l S', 'clipped_path'),
    (b'10 20 100 6 re 40 20 20 6 re f*', 'complex_closed_or_filled_path'),
    (b'10 20 m 100 20 l 70 26 l 10 26 l h f', 'complex_closed_or_filled_path'),
])
def test_unsupported_paths_remain_reference_not_continuous_native_walls(tmp_path, content, reason):
    level = pdf(tmp_path, content)
    assert level['method'] == 'vector' and not level['walls']
    assert level['raw_vectors'][0]['deferred_reason'] == reason
    assert level['reference'].startswith('data:image/png;base64,')
    assert any('sans axe vectoriel automatique' in s for s in level['warnings'])


def test_unpainted_pdf_path_does_not_become_a_wall(tmp_path):
    level = pdf(tmp_path, b'10 20 m 200 20 l n')
    assert level['method'] == 'vector' and not level['walls']


@pytest.mark.parametrize('alpha', [0, .5])
def test_transparent_native_stroke_is_not_recovered(tmp_path, alpha):
    def resources(writer):
        state = DictionaryObject({NameObject('/CA'): FloatObject(alpha)})
        return DictionaryObject({NameObject('/ExtGState'): DictionaryObject({NameObject('/G'): writer._add_object(state)})})
    level = pdf(tmp_path, b'/G gs 10 20 m 200 20 l S', resources=resources)
    assert not level['walls']
    assert level['raw_vectors'][0]['deferred_reason'] == 'non_dark_or_transparent_paint'


@pytest.mark.parametrize('rotation,expected,size', [
    (0, [[10, 90], [90, 90]], [200, 120]),
    (90, [[30, 10], [30, 90]], [120, 200]),
    (180, [[110, 30], [190, 30]], [200, 120]),
    (270, [[90, 110], [90, 190]], [120, 200]),
])
def test_crop_rotation_and_object_matrix_match_the_rendered_reference(tmp_path, rotation, expected, size):
    # Source (5, 10) -> (20, 50) and (45, 10) -> (100, 50).
    level = pdf(tmp_path, b'2 0 0 3 10 20 cm 2 w 5 10 m 45 10 l S',
                crop=(10, 20, 210, 140), rotation=rotation)
    assert [level['width'], level['height']] == size
    w = level['walls'][0]
    assert endpoints(w) == expected
    image = Image.open(io.BytesIO(base64.b64decode(level['reference'].split(',')[1]))).convert('RGB')
    for t in (.1, .5, .9):
        p = [w['a'][k]+t*(w['b'][k]-w['a'][k]) for k in (0, 1)]
        pixel = image.getpixel((int(p[0]*image.width/level['width']), int(p[1]*image.height/level['height'])))
        assert max(pixel) < 30


def test_diagonal_stroke_keeps_its_exact_axis(tmp_path):
    level = pdf(tmp_path, b'2 w 10 20 m 100 90 l S')
    assert endpoints(level['walls'][0]) == [[10, 140], [100, 70]]


def test_form_matrix_is_preserved_raw_but_form_bbox_is_not_ignored(tmp_path):
    def resources(writer):
        form = DecodedStreamObject()
        form.set_data(b'2 w 10 20 m 100 20 l S')
        form.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Form'),
                     NameObject('/BBox'): ArrayObject([NumberObject(x) for x in (20, 0, 50, 80)]),
                     NameObject('/Resources'): DictionaryObject()})
        return DictionaryObject({NameObject('/XObject'): DictionaryObject({NameObject('/F'): writer._add_object(form)})})
    level = pdf(tmp_path, b'2 0 0 2 10 15 cm /F Do', resources=resources)
    path = level['raw_vectors'][0]
    assert [s['point'] for s in path['segments']] == [[30, 105], [210, 105]]
    assert not level['walls']
    assert path['in_form'] and path['deferred_reason'] == 'form_visibility_requires_review'


def raster_resources(writer):
    image = Image.new('L', (240, 160), 255)
    ImageDraw.Draw(image).rectangle((20, 100, 180, 106), fill=0)
    stream = DecodedStreamObject()
    stream.set_data(image.tobytes())
    stream.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                   NameObject('/Width'): NumberObject(240), NameObject('/Height'): NumberObject(160),
                   NameObject('/ColorSpace'): NameObject('/DeviceGray'), NameObject('/BitsPerComponent'): NumberObject(8)})
    return DictionaryObject({NameObject('/XObject'): DictionaryObject({NameObject('/I'): writer._add_object(stream)})})


def test_lone_vector_annotation_never_hides_raster_plan(tmp_path):
    level = pdf(tmp_path, b'q 240 0 0 160 0 0 cm /I Do Q 2 w 10 140 m 100 140 l S',
                resources=raster_resources)
    assert level['method'] == 'mixed'
    assert any(w['method'] == 'native_pdf_stroke' for w in level['walls'])
    assert any(99 < (w['a'][1]+w['b'][1])/2 < 107 for w in level['walls'])
    assert all(w['status'] == 'pending' for w in level['walls'])
    assert any('Page mixte' in warning for warning in level['warnings'])


def test_raster_only_pdf_keeps_existing_baseline(tmp_path):
    level = pdf(tmp_path, b'q 240 0 0 160 0 0 cm /I Do Q', resources=raster_resources)
    assert level['method'] == 'raster_baseline' and not level['raw_vectors']
    assert level['walls'] and all(w['method'] != 'native_pdf_stroke' for w in level['walls'])
