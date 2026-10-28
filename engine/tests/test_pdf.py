from pathlib import Path
import json

import pikepdf
import pytest

from doemo_pdf.cli import main
from doemo_pdf.geometry import Rect
from doemo_pdf.pdf import compose_diagnostic, file_hash, inspect_pdf, open_pdf


def fixture_pdf(path, *, name='Source', hidden=False, rotate=0, pages=1,
                vector=True, interactive=False, image=False, crop=None, template_ctm=False):
    pdf = pikepdf.Pdf.new()
    ocg = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.OCG, Name=name))
    pdf.Root.OCProperties = pikepdf.Dictionary(OCGs=pikepdf.Array([ocg]), D=pikepdf.Dictionary(
        Order=pikepdf.Array([ocg]), ON=pikepdf.Array([] if hidden else [ocg]),
        OFF=pikepdf.Array([ocg] if hidden else [])))
    for _ in range(pages):
        p = pdf.add_blank_page(page_size=(400,600))
        p.obj.Rotate = rotate
        if crop:
            p.obj.CropBox = pikepdf.Array(crop)
        p.obj.Group = pikepdf.Dictionary(S=pikepdf.Name.Transparency, I=True, K=False)
        p.Resources.Properties = pikepdf.Dictionary(Layer=ocg)
        p.Resources.Font = pikepdf.Dictionary(F1=pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)))
        content = b'/OC /Layer BDC\n'
        if vector:
            content += b'0.1 0.2 0.7 rg 20 30 200 300 re f\n'
        content += b'BT /F1 12 Tf 30 60 Td (PE V) Tj ET\nEMC\n'
        if image:
            im=pdf.make_stream(b'\xff\x00\x00')
            im.Type=pikepdf.Name.XObject
            im.Subtype=pikepdf.Name.Image
            im.Width=1; im.Height=1; im.BitsPerComponent=8
            im.ColorSpace=pikepdf.Name.DeviceRGB
            p.Resources.XObject=pikepdf.Dictionary(Im1=im)
            content += b'q 10 0 0 10 10 10 cm /Im1 Do Q\n'
        if template_ctm:
            content += b'2 0 0 2 50 50 cm\n'
        p.Contents=pdf.make_stream(content)
    if interactive:
        pdf.Root.OpenAction=pikepdf.Dictionary(S=pikepdf.Name.JavaScript,JS='app.alert("test")')
    pdf.save(path)
    return path


@pytest.fixture
def inputs(tmp_path):
    return (fixture_pdf(tmp_path/'source.pdf', image=True),
            fixture_pdf(tmp_path/'template.pdf',name='Template',hidden=True,template_ctm=True))


def test_inspect_real_content_and_candidates(inputs):
    report=inspect_pdf(inputs[0])
    assert report['source_unchanged']
    assert report['pages'][0]['vector_evidence']['path_paint_operators']==1
    assert report['pages'][0]['vector_evidence']['image_resources']==1
    assert report['pages'][0]['label_candidates'][0]['status']=='label_only_not_verified_vei'
    assert report['pages'][0]['label_candidates'][0]['direction'] is None
    assert report['production_ready'] is False


@pytest.mark.parametrize('direction', [(0,1),(1,0),(0,-1),(-1,0),(3,7)])
def test_composition_keeps_resources_visibility_and_sources(inputs,tmp_path,direction):
    source,template=inputs
    before=[file_hash(p) for p in inputs]
    dest=tmp_path/'diagnostic.pdf'
    report=compose_diagnostic(source,template,dest,Rect(10,10,390,590),direction)
    assert [file_hash(p) for p in inputs]==before
    assert report['production_ready'] is False
    assert report['status']=='diagnostic_nonconforming'
    assert report['checks']['embedded_resource_streams_unchanged']=='passed'
    assert report['checks']['single_active_vei']=='not_satisfied'
    assert json.loads(dest.with_suffix('.report.json').read_text())==report
    with pikepdf.Pdf.open(dest) as pdf:
        page=pdf.pages[0]
        assert list(page.mediabox)==[0,0,400,600]
        src=page.Resources.XObject.DOEMO_SOURCE
        assert src.Group.S==pikepdf.Name.Transparency
        assert src.Resources.XObject.Im1.read_bytes()==b'\xff\x00\x00'
        layers=pdf.Root.OCProperties
        assert {str(o.Name) for o in layers.OCGs}=={'Source','Template'}
        assert {str(o.Name) for o in layers.D.OFF}=={'Template'}
        assert {str(o.Name) for o in layers.D.ON}=={'Source'}
        data=b''.join(c.read_bytes() for c in page.Contents)
        assert data.startswith(b'q\n')
        assert b'2 0 0 2 50 50 cm' in data
        assert b'Q\nq\n' in data
        assert 'DIAGNOSTIC' in str(pdf.docinfo.Title)


def test_hidden_source_layer_stays_hidden(tmp_path):
    source=fixture_pdf(tmp_path/'s.pdf',hidden=True)
    template=fixture_pdf(tmp_path/'t.pdf',name='Template')
    dest=tmp_path/'o.pdf'
    compose_diagnostic(source,template,dest,Rect(0,0,400,600),(0,1))
    with pikepdf.Pdf.open(dest) as pdf:
        assert {str(o.Name) for o in pdf.Root.OCProperties.D.OFF}=={'Source'}


def test_nonzero_crop_origin_and_page_selection(tmp_path):
    source=fixture_pdf(tmp_path/'s.pdf',crop=[10,20,300,500],pages=2)
    template=fixture_pdf(tmp_path/'t.pdf')
    report=compose_diagnostic(source,template,tmp_path/'o.pdf',Rect(0,0,400,600),(1,1),source_page=1)
    assert report['source']['page']==2
    assert report['source_bounds']==[10,20,300,500]


@pytest.mark.parametrize('case',['output_exists','report_exists','invalid_zone','invalid_direction','bad_page'])
def test_invalid_requests_leave_sources_untouched(inputs,tmp_path,case):
    dest=tmp_path/'o.pdf'; zone=Rect(10,10,390,590); direction=(0,1); page=0
    if case=='output_exists':dest.write_bytes(b'existing document')
    if case=='report_exists':dest.with_suffix('.report.json').write_text('existing report')
    if case=='invalid_zone':zone=Rect(-5,0,400,600)
    if case=='invalid_direction':direction=(0,0)
    if case=='bad_page':page=10
    before=[file_hash(p) for p in inputs]
    with pytest.raises(ValueError):compose_diagnostic(*inputs,dest,zone,direction,source_page=page)
    assert [file_hash(p) for p in inputs]==before
    if case=='output_exists':assert dest.read_bytes()==b'existing document'
    else:assert not dest.exists()


@pytest.mark.parametrize('kwargs',[{'rotate':90},{'interactive':True},{'vector':False}])
def test_unvalidated_documents_blocked(tmp_path,kwargs):
    source=fixture_pdf(tmp_path/'s.pdf',**kwargs)
    template=fixture_pdf(tmp_path/'t.pdf')
    with pytest.raises(ValueError):
        compose_diagnostic(source,template,tmp_path/'o.pdf',Rect(0,0,400,600),(0,1))
    assert not (tmp_path/'o.pdf').exists()


def test_native_ai_without_pdf_rejected(tmp_path):
    p=tmp_path/'drawing.ai';p.write_bytes(b'%!PS-Adobe-3.0')
    with pytest.raises(ValueError,match='représentation PDF'):open_pdf(p)


def test_corrupt_pdf_rejected(tmp_path):
    p=tmp_path/'bad.pdf';p.write_bytes(b'%PDF-1.6\ntruncated')
    with pytest.raises(pikepdf.PdfError):open_pdf(p)


def test_cli_blocked_status_and_production_command_absent(tmp_path,capsys):
    p=tmp_path/'bad.ai';p.write_text('not PDF')
    assert main(['inspect',str(p)])==2
    assert json.loads(capsys.readouterr().err)['status']=='blocked'
    with pytest.raises(SystemExit) as error:main(['produce'])
    assert error.value.code==2
