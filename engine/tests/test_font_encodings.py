from io import BytesIO
from types import SimpleNamespace
import base64

import pikepdf
import pytest
from fontTools.ttLib import TTFont

from doemo_pdf.scene import FontMetrics, Scene, cmyk_color
from doemo_pdf.textframes import bind_text_frames
from test_generation import font


def cid_font(pdf, identity=False):
    simple=font(pdf)
    tt=TTFont(BytesIO(simple.FontDescriptor.FontFile2.read_bytes()))
    gid=tt.getGlyphID('A');space=tt.getGlyphID('space')
    mapping=bytearray(604);mapping[600:602]=gid.to_bytes(2,'big');mapping[602:604]=space.to_bytes(2,'big')
    descendant=pikepdf.Dictionary(Type=pikepdf.Name.Font,Subtype=pikepdf.Name.CIDFontType2,
        BaseFont=pikepdf.Name.Fixture,FontDescriptor=simple.FontDescriptor,
        CIDSystemInfo=pikepdf.Dictionary(Registry='Adobe',Ordering='Identity',Supplement=0),
        CIDToGIDMap=pikepdf.Name.Identity if identity else pdf.make_stream(bytes(mapping)),
        DW=800,W=pikepdf.Array([300,pikepdf.Array([500,250]),302,303,700]))
    cmap=pdf.make_stream(b'1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n1 beginbfchar\n<012C> <0041>\nendbfchar\n1 beginbfrange\n<012D> <012E> [<0020> <0056>]\nendbfrange')
    return pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font,Subtype=pikepdf.Name.Type0,
        BaseFont=pikepdf.Name.Fixture,Encoding=pikepdf.Name('/Identity-H'),
        DescendantFonts=pikepdf.Array([descendant]),ToUnicode=cmap)),gid


def test_identity_h_maps_cids_to_embedded_glyphs_and_unicode():
    pdf=pikepdf.Pdf.new();f,_=cid_font(pdf);metrics=FontMetrics(f)
    assert metrics.decode(bytes.fromhex('012c012d012e'))=='A V'
    assert metrics.glyph(300)==((0.,0.,400.,700.),500.)
    assert metrics.glyph(301)==(None,250.)
    assert metrics.glyph(302)[1]==700 and metrics.glyph(500)[1]==800
    _,advance=metrics.measure([pikepdf.String(bytes.fromhex('012c012d'))],dict(size=10,Tz=100,Ts=0,Tc=.2,Tw=100))
    assert advance==pytest.approx(7.9)  # Word spacing does not apply to two-byte codes.
    with pytest.raises(ValueError,match='tronqué'):metrics.decode(b'\x01')


def test_identity_gid_and_original_pdf_text_stream_are_preserved():
    pdf=pikepdf.Pdf.new();f,gid=cid_font(pdf,identity=True);metrics=FontMetrics(f)
    assert metrics.glyph(gid)[0]==(0.,0.,400.,700.)
    pg=pdf.add_blank_page(page_size=(200,200));pg.Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F=f))
    command=f'<{gid:04x}> Tj'.encode()
    pg.Contents=pdf.make_stream(b'BT /F 10 Tf 1 0 0 1 20 30 Tm '+command+b' ET')
    item=Scene(pg).items[0]
    assert item.bounds==pytest.approx((20,30,24,37))
    assert command in item.stream


@pytest.mark.parametrize('encoding,raw,expected',[('/MacRomanEncoding',b'\x88','à'),('/StandardEncoding',b'A','A')])
def test_named_simple_font_encodings(encoding,raw,expected):
    pdf=pikepdf.Pdf.new();f=font(pdf);f.Encoding=pikepdf.Name(encoding);metrics=FontMetrics(f)
    assert metrics.decode(raw)==expected
    assert metrics.glyph(raw[0])[0] is not None


def test_differences_decode_using_glyph_name():
    pdf=pikepdf.Pdf.new();f=font(pdf)
    f.Encoding=pikepdf.Dictionary(BaseEncoding=pikepdf.Name.WinAnsiEncoding,Differences=[65,pikepdf.Name('/agrave')])
    assert FontMetrics(f).decode(b'A')=='à'


def text_document():
    data=b'/1 << /1 [ << /0 << /0 (AA\nBB\n) >> /1 [ << /99 /G /5 [10 10 1] >> << /99 /G /5 [11 11 1] >> ] >> ] >>'
    return '%AI11_BeginTextDocument\n%'+base64.a85encode(data).decode()+'~>\n%AI11_EndTextDocument'


def test_multiline_native_glyphs_share_one_rotation_anchor():
    items=[SimpleNamespace(glyph_ids=(10,10),bounds=(10,30,30,37),matrix=(7,0,0,7,10,30),text_anchor=None),
           SimpleNamespace(glyph_ids=(11,11),bounds=(12,21.6,28,28.6),matrix=(7,0,0,7,12,21.6),text_anchor=None)]
    block='/AI11Text :\n0 /FreeUndo ,\n0 /StoryIndex ,\n'
    bind_text_frames(text_document(),block,items)
    assert items[0].text_anchor==items[1].text_anchor==pytest.approx((20,29.3))
    assert [it.text for it in items]==['AA','BB']
    items[1].glyph_ids=(12,12)
    with pytest.raises(ValueError,match='glyphes PDF'):bind_text_frames(text_document(),block,items)


def test_expanded_native_glyph_run_recovers_level_title():
    data=b'/1 << /1 [ << /0 << /0 (NIVEAU 0\n) >> /1 [ << /99 /G /21 << /0 [15 10 23 6 2 22 1 1087 1] >> >> ] >> ] >>'
    raw='%AI11_BeginTextDocument\n%'+base64.a85encode(data).decode()+'~>\n%AI11_EndTextDocument'
    item=SimpleNamespace(glyph_ids=(15,10,23,6,2,22,1,1087),bounds=(10,30,80,42),matrix=(12,0,0,12,10,30),text_anchor=None)
    bind_text_frames(raw,'/AI11Text :\n0 /FreeUndo ,\n0 /StoryIndex ,\n',[item])
    assert item.text=='NIVEAU 0' and item.text_anchor==(45,36)


def test_icc_and_spot_colour_identification_does_not_rewrite_stream():
    pdf=pikepdf.Pdf.new();profile=pdf.make_stream(b'test only');profile.N=4
    icc=pikepdf.Array([pikepdf.Name.ICCBased,profile]);spot=pikepdf.Array([pikepdf.Name.Separation,pikepdf.Name.Blue,icc,
        pikepdf.Dictionary(FunctionType=2,Domain=[0,1],C0=[0,0,0,0],C1=[.91,.697,.011,0],N=1)])
    pg=pdf.add_blank_page();pg.Resources=pikepdf.Dictionary(ColorSpace=pikepdf.Dictionary(Blue=spot))
    pg.Contents=pdf.make_stream(b'/Blue CS 1 SCN 1 w 10 20 m 30 40 l S')
    item=Scene(pg).items[0]
    assert item.stroke==(.91,.697,.011,0)
    assert b'/Blue CS\n1 SCN' in item.stream
    assert cmyk_color(spot,[.5],pg.Resources)==pytest.approx((.455,.3485,.0055,0))


def test_repeated_unicode_labels_do_not_create_false_frame_ambiguity():
    story=b'<< /0 << /0 (BUREAU\n) >> /1 [ << /99 /G /5 [37 56 53 40 36 56 3] >> ] >>'
    data=b'/1 << /1 [ '+story+b' '+story+b' ] >>'
    raw='%AI11_BeginTextDocument\n%'+base64.a85encode(data).decode()+'~>\n%AI11_EndTextDocument'
    block='/AI11Text :\n0 /FreeUndo ,\n0 /StoryIndex ,\n/AI11Text :\n0 /FreeUndo ,\n1 /StoryIndex ,\n'
    items=[SimpleNamespace(glyph_ids=(),text='BUREAU',bounds=(x,30,x+40,37),matrix=(7,0,0,7,x,30),text_anchor=None) for x in (10,100)]
    bind_text_frames(raw,block,items)
    assert items[0].text_anchor==(30,33.5) and items[1].text_anchor==(120,33.5)


def test_unicode_multiline_label_uses_one_anchor_with_font_specific_terminator():
    data=b'/1 << /1 [ << /0 << /0 (SALLE DE\nPAUSE\n) >> /1 [ << /99 /G /5 [54 36 47 47 40 3 39 40 3] >> << /99 /G /5 [51 36 56 54 40 3] >> ] >> ] >>'
    raw='%AI11_BeginTextDocument\n%'+base64.a85encode(data).decode()+'~>\n%AI11_EndTextDocument'
    block='/AI11Text :\n0 /FreeUndo ,\n0 /StoryIndex ,\n'
    items=[SimpleNamespace(glyph_ids=(),text='SALLE DE',bounds=(10,30,50,37),matrix=(10,0,0,10,10,30),text_anchor=None),
           SimpleNamespace(glyph_ids=(),text='PAUSE',bounds=(18,18,42,25),matrix=(10,0,0,10,18,18),text_anchor=None)]
    bind_text_frames(raw,block,items)
    assert items[0].text_anchor==items[1].text_anchor==(30,27.5)


def test_illustrator_export_layer_titles_and_hidden_metadata():
    pdf=pikepdf.Pdf.new();page=pdf.add_blank_page()
    hidden=pdf.make_stream(b'0 0 100 100 re f')
    page.Resources=pikepdf.Dictionary(Properties=pikepdf.Dictionary(
        L=pikepdf.Dictionary(Title=pikepdf.String('Relevé'.encode('utf-8'))),
        H=pikepdf.Dictionary(AIType=pikepdf.Name.HiddenLayer,Contents=hidden)))
    page.Contents=pdf.make_stream(b'/Layer /L BDC /AltAI8 /H BDC EMC 0 G 1 w 10 20 m 30 40 l S EMC')
    scene=Scene(page)
    assert len(scene.items)==1 and scene.items[0].layer=='Relevé'
    assert scene.items[0].operator=='S'  # The alternate stream is never painted.
