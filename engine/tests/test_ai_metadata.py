from pathlib import Path
import pikepdf
import pytest
import zstandard

from doemo_pdf.ai_metadata import PREFIX, inspect_ai_metadata, parse_native, ps_string


NATIVE = b'''%!PS-Adobe-3.0
%AI14_BeginSymbol
(Alarm)
%AI10_EndSymbol
%AI5_BeginLayer
1 1 1 1 0 0 Lb
(Pictos) Ln
/SymbolInstance :
(Alarm) /SymbolRef ,
1 0 0 -1 100 -200 /RTransformMatrix
;
LB
%AI5_EndLayer--
'''


def test_parse_explicit_names_and_matrices_without_interpreting_code():
    r=parse_native(NATIVE)
    assert r['symbol_definition_count']==1
    assert r['symbol_instance_count_in_layers']==1
    assert r['layers'][0]['name']=='Pictos'
    item=r['layers'][0]['symbol_instances'][0]
    assert item['symbol']=='Alarm'
    assert item['matrix_native']==[1,0,0,-1,100,-200]
    assert item['pdf_object_binding']=='unverified'
    assert r['complete_illustrator_interpretation'] is False


@pytest.mark.parametrize('newline',[b'\r',b'\n',b'\r\n'])
def test_adobe_line_endings(newline):
    assert parse_native(NATIVE.replace(b'\n',newline))['symbol_instance_count_in_layers']==1


def test_literal_names_escapes_and_parentheses():
    text=r'(Signal \(test\) (nested) \101) next'
    name,end=ps_string(text,0)
    assert name=='Signal (test) (nested) A'
    assert text[end:]==' next'


def test_symbol_matrix_missing_fails_instead_of_inventing_position():
    with pytest.raises(ValueError,match='Matrice'):
        parse_native(NATIVE.replace(b'1 0 0 -1 100 -200 /RTransformMatrix',b'/UnknownMatrix'))


def test_native_data_read_from_pdf_container_with_no_execution(tmp_path):
    pdf=pikepdf.Pdf.new();page=pdf.add_blank_page(page_size=(400,600))
    payload=PREFIX+zstandard.ZstdCompressor().compress(NATIVE)
    private=pikepdf.Dictionary(AIPrivateData1=pdf.make_stream(payload))
    page.obj.PieceInfo=pikepdf.Dictionary(Illustrator=pikepdf.Dictionary(Private=private))
    path=tmp_path/'native.ai';pdf.save(path)
    r=inspect_ai_metadata(path)
    assert r['source_unchanged']
    assert r['layers'][0]['visible_in_default_pdf'] is None


@pytest.mark.parametrize('printable', [False, True])
def test_native_printability_is_distinct_from_pdf_visibility(tmp_path, printable):
    # The supplied AI24 BAT uses 14 operands; EXT's fourth operand is zero.
    native = NATIVE.replace(b'1 1 1 1 0 0 Lb',
                            f'1 1 1 {int(printable)} 0 0 1 16 0 0 136 0 50 0 Lb'.encode())
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(400, 600))
    layer = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.OCG, Name='Pictos'))
    pdf.Root.OCProperties = pikepdf.Dictionary(
        OCGs=pikepdf.Array([layer]),
        D=pikepdf.Dictionary(BaseState=pikepdf.Name.ON, OFF=pikepdf.Array([layer])))
    page.obj.PieceInfo = pikepdf.Dictionary(Illustrator=pikepdf.Dictionary(
        Private=pikepdf.Dictionary(AIPrivateData1=pdf.make_stream(
            PREFIX + zstandard.ZstdCompressor().compress(native)))))
    path = tmp_path / 'nonprinting.ai'
    pdf.save(path)
    original = path.read_bytes()
    report = inspect_ai_metadata(path)
    assert report['layers'][0]['native_printable'] is printable
    assert report['layers'][0]['visible_in_default_pdf'] is False
    assert report['symbol_instance_count_in_layers'] == 1
    assert report['source_unchanged']
    assert path.read_bytes() == original


@pytest.mark.parametrize('record', [
    b'1 1 1 1 0 0 Lb',  # Different operand count: do not extrapolate.
    b'1 1 1 2 0 0 1 16 0 0 136 0 50 0 Lb',
    b'% no layer flags',
    b'1 1 1 0 0 0 1 16 0 0 136 0 50 0 LbExtra',
])
def test_unknown_layer_record_does_not_guess_printability(record):
    report = parse_native(NATIVE.replace(b'1 1 1 1 0 0 Lb', record))
    assert report['layers'][0]['native_printable'] is None


def test_decompression_limit_rejects_large_declared_frame(tmp_path,monkeypatch):
    import doemo_pdf.ai_metadata as module
    pdf=pikepdf.Pdf.new();page=pdf.add_blank_page(page_size=(400,600))
    payload=PREFIX+zstandard.ZstdCompressor().compress(NATIVE*100)
    page.obj.PieceInfo=pikepdf.Dictionary(Illustrator=pikepdf.Dictionary(
        Private=pikepdf.Dictionary(AIPrivateData1=pdf.make_stream(payload))))
    path=tmp_path/'native.ai';pdf.save(path)
    monkeypatch.setattr(module,'MAX_NATIVE',2048)
    with pytest.raises(ValueError,match='volumineus'):
        inspect_ai_metadata(path)
