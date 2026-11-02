import hashlib
import io
import json
import math

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, ArrayObject, TextStringObject

from doemo_releves.unified_export import make_pdf, isolated_pdf, PT_PER_MM, attach_unified_export, _solid_intervals


def vector_asset(directory):
    directory.mkdir(exist_ok=True)
    out = directory/'symbol.ai'
    writer = PdfWriter(); page = writer.add_blank_page(width=100, height=50)
    stream = DecodedStreamObject(); stream.set_data(b'1 0 0 rg 0 0 100 50 re f')
    page[NameObject('/Contents')] = writer._add_object(stream)
    # Non-graphic actions must never be carried into the combined document.
    page[NameObject('/AA')] = DictionaryObject({NameObject('/O'): DictionaryObject({NameObject('/S'): NameObject('/JavaScript'), NameObject('/JS'): TextStringObject('void(0)')})})
    writer.write(out)
    return {'id': 'ext', 'name': 'Extincteur', 'verified': True, 'approved': True, 'pictogram_candidate': True,
            'components': [{'role': 'primary', 'archive_path': 'symbol.ai', 'sha256': hashlib.sha256(out.read_bytes()).hexdigest()}]}


def annotation(ident='a', **changes):
    return {'id': ident, 'source_document_id': 'source', 'source_page': 1, 'status': 'review',
            'bbox': {'x': .1, 'y': .1, 'w': .04, 'h': .04}, 'anchor': {'x': .7, 'y': .6},
            'target': {'x': .2, 'y': .3}, 'asset_id': 'ext', 'text': 'EXT CO₂', 'floor_id': None,
            'rotation_deg': 90, 'size_mm': 10, **changes}


def input_data(tmp_path, **changes):
    return {'project_id': 'project', 'revision': 4, 'document_id': 'source', 'page': 1,
            'source_sha256': 'a'*64, 'page_data': {'width': 1000, 'height': 500}, 'paper_width_mm': 100,
            'structures': [{'source_document_id': 'source', 'source_page': 1, 'source_sha256': 'a'*64,
                'width': 1000, 'height': 500, 'unit': 'px', 'walls': [{'id': 'w', 'a': [100, 100], 'b': [900, 100],
                 'thickness': 10, 'status': 'pending', 'method': 'manual', 'confidence': 0, 'openings': []}]}],
            'annotations': [annotation()], 'library': {'id': 'lib', 'archive_verified': True, 'assets': [vector_asset(tmp_path/'library')]},
            'library_directory': str(tmp_path/'library'), **changes}


def embedded_report(reader):
    return json.loads(reader.attachments['doemo-plan-unifie.json'][0])


def test_original_resource_is_positioned_from_anchor_with_rotation_and_print_size(tmp_path):
    path = tmp_path/'combined.pdf'; data = input_data(tmp_path)
    report = make_pdf(data, path)
    reader = PdfReader(path)
    assert len(reader.pages) == 1
    assert float(reader.pages[0].mediabox.width) == pytest.approx(100*PT_PER_MM)
    assert float(reader.pages[0].mediabox.height) == pytest.approx(50*PT_PER_MM)
    assert len(reader.root_object['/OCProperties']['/OCGs']) == 3
    placed = report['placements'][0]
    assert placed['position_pt'] == pytest.approx([70*PT_PER_MM, 20*PT_PER_MM])
    assert not placed['target_override_used']
    # The crop-box centre maps exactly to the physical anchor, not text bbox.
    a,b,c,d,e,f = placed['resource_to_page_matrix']
    assert [a*50+c*25+e, b*50+d*25+f] == pytest.approx(placed['position_pt'])
    assert math.hypot(a,b)*100 == pytest.approx(10*PT_PER_MM)
    assert a == pytest.approx(0, abs=1e-12) and b < 0  # clockwise in top-left view
    form = next(iter(reader.pages[0]['/Resources']['/XObject'].values())).get_object()
    assert form['/Subtype'] == '/Form' and form.get_data() == b'1 0 0 rg 0 0 100 50 re f'
    assert '/AA' not in form and '/AA' not in reader.pages[0] and '/OpenAction' not in reader.root_object
    assert embedded_report(reader)['native_ai_created'] is False
    assert reader.metadata['/DOEMOSourceSHA256'] == 'a'*64
    assert report['unresolved'] == []


def test_missing_anchor_or_asset_is_explicit_and_never_uses_bbox_or_target(tmp_path):
    data = input_data(tmp_path, annotations=[annotation(anchor=None), annotation('missing', asset_id=None)])
    path = tmp_path/'review.pdf'; report = make_pdf(data, path)
    assert report['placements'][0]['status'] == 'missing_anchor'
    assert report['placements'][0]['position_pt'] is None
    assert report['placements'][1]['status'] == 'reference_marker'
    assert len(report['unresolved']) == 2
    reader = PdfReader(path)
    assert not reader.pages[0]['/Resources']['/XObject']
    text = reader.pages[0].extract_text()
    assert 'ANCRAGE À POINTER' in text and 'SAI À COMPLÉTER' in text


def test_resource_checksum_failure_and_non_pdf_ai_are_markers_not_rasters(tmp_path):
    data = input_data(tmp_path); asset = data['library']['assets'][0]
    (tmp_path/'library'/'symbol.ai').write_bytes(b'%!PS-not-a-PDF')
    asset['components'][0]['sha256'] = hashlib.sha256(b'%!PS-not-a-PDF').hexdigest()
    path = tmp_path/'review.pdf'; report = make_pdf(data, path)
    assert 'sans composant PDF' in report['unresolved'][0]['reason']
    asset['components'][0]['sha256'] = '0'*64
    report = make_pdf(data, path)
    assert 'empreinte' in report['unresolved'][0]['reason']
    assert not PdfReader(path).pages[0]['/Resources']['/XObject']


def test_openings_remove_material_and_windows_have_two_rails(tmp_path):
    from pypdf.generic import ContentStream
    data = input_data(tmp_path, annotations=[])
    wall = data['structures'][0]['walls'][0]
    wall['openings'] = [{'start': .25, 'end': .5, 'kind': 'door', 'status': 'pending'},
                        {'start': .75, 'end': .9, 'kind': 'window', 'status': 'pending'}]
    path = tmp_path/'openings.pdf'; make_pdf(data, path)
    reader = PdfReader(path)
    ops = ContentStream(reader.pages[0]['/Contents'], reader).operations
    assert sum(op == b'f' for _, op in ops) == 3
    assert sum(op == b'S' for _, op in ops) == 2
    starts = [list(map(float, args)) for args, op in ops if op == b'm']
    # First wall piece ends at x300; second begins at x500, leaving door white.
    assert starts[0][0] == pytest.approx(100/1000*100*PT_PER_MM)
    assert starts[1][0] == pytest.approx(500/1000*100*PT_PER_MM)
    assert _solid_intervals([{'start': .2, 'end': .4}, {'start': .3, 'end': .5}]) == [(0, .2), (.5, 1)]


def test_changing_print_width_keeps_normalized_positions_and_symbol_size(tmp_path):
    data = input_data(tmp_path)
    first = make_pdf(data, tmp_path/'one.pdf')['placements'][0]
    data['paper_width_mm'] = 200
    second = make_pdf(data, tmp_path/'two.pdf')['placements'][0]
    assert second['position_pt'] == pytest.approx([v*2 for v in first['position_pt']])
    assert second['resource_to_page_matrix'][:4] == pytest.approx(first['resource_to_page_matrix'][:4])


def test_rotated_crop_matches_preview_frame_and_nonstandard_units_are_explicit(tmp_path):
    from pypdf.generic import RectangleObject, NumberObject
    from doemo_releves.documents import render_page
    data = input_data(tmp_path)
    asset_path = tmp_path/'library'/'symbol.ai'
    reader = PdfReader(asset_path); writer = PdfWriter()
    original = writer.add_page(reader.pages[0])
    original.cropbox = RectangleObject([10, 5, 90, 45])
    original.rotate(90)
    writer.write(asset_path)
    component = data['library']['assets'][0]['components'][0]
    component['sha256'] = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    preview = render_page(asset_path, 1, max_side=256)
    report = make_pdf(data, tmp_path/'cropped.pdf')
    left,bottom,right,top = report['placements'][0]['resource_bounds_pt']
    assert (right-left)/(top-bottom) == pytest.approx(preview.width/preview.height, rel=.01)
    reader = PdfReader(asset_path); writer = PdfWriter(); original = writer.add_page(reader.pages[0])
    original[NameObject('/UserUnit')] = NumberObject(2); writer.write(asset_path)
    component['sha256'] = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    report = make_pdf(data, tmp_path/'nonstandard.pdf')
    assert report['placements'][0]['status'] == 'reference_marker'
    assert 'repère PDF non standard' in report['unresolved'][0]['reason']


def test_export_subprocess_is_functional_without_model_or_gpu(tmp_path):
    pdf, report = isolated_pdf(input_data(tmp_path, annotations=[]))
    assert pdf.startswith(b'%PDF-') and report['unresolved'] == []
    assert embedded_report(PdfReader(io.BytesIO(pdf)))['walls'] == 1


def test_export_api_checks_source_page_ownership_roles_and_work_revision(tmp_path):
    from doemo_releves.api import create_app
    app = create_app(tmp_path/'private')
    # Root backend integrates the route; make this test runnable while that work
    # is in progress without replacing the application's access checks.
    assert any(r.path.endswith('/unified-export') for r in app.routes)
    c = TestClient(app, headers={'X-Doemo-User': 'designer', 'X-Doemo-Role': 'dessinateur'})
    p = c.post('/projects', json={'name': 'Unified'}).json()
    image = io.BytesIO(); Image.new('RGB', (600, 400), 'white').save(image, 'PNG')
    p = c.post(f'/projects/{p["id"]}/documents', data={'role': 'survey'}, files={'file': ('source.png', image.getvalue())}).json()
    did = p['documents'][0]['id']; path = f'/projects/{p["id"]}/unified-export'
    params = {'document_id': did, 'page': 1, 'paper_width_mm': 297}
    response = c.get(path, params=params)
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['x-doemo-revision'] == '0'
    assert c.get(f'/projects/{p["id"]}').json()['state']['revision'] == 0
    assert c.get(path, params=params, headers={'X-Doemo-User': 'other'}).status_code == 404
    assert c.get(path, params=params, headers={'X-Doemo-Role': 'client'}).status_code == 403
    assert c.get(path, params={**params, 'page': 2}).status_code == 404
    assert c.get(path, params={**params, 'document_id': 'elsewhere'}).status_code == 404
    assert c.get(path, params={**params, 'paper_width_mm': 0}).status_code == 422
