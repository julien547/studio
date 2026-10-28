"""Real PDF engine tests, including native bindings and complete ZIP contents."""
from io import BytesIO
import hashlib
import json
from pathlib import Path
import zipfile

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
import pikepdf
import pytest
import zstandard

from doemo_pdf.ai_metadata import PREFIX
from doemo_pdf.bindings import bind, outlines_match
from doemo_pdf.generate import generate_batch, inspect_generation
from doemo_pdf.scene import Scene, multiply, instruction
from doemo_pdf.pdf import file_hash
from fontTools.agl import UV2AGL
from datetime import date
from pypdf import PdfReader


def font(pdf):
    chars=''.join(chr(c) for c in range(32,127))+'à°';names=['.notdef',*(UV2AGL[ord(c)] for c in chars)];fb=FontBuilder(1000,isTTF=True)
    fb.setupGlyphOrder(names);fb.setupCharacterMap({ord(c):UV2AGL[ord(c)] for c in chars})
    glyphs={}
    for name in names:
        pen=TTGlyphPen(None)
        if name!='space':pen.moveTo((50,0));pen.lineTo((450,0));pen.lineTo((450,700));pen.lineTo((50,700));pen.closePath()
        glyphs[name]=pen.glyph()
    fb.setupGlyf(glyphs);fb.setupHorizontalMetrics({n:(500,0) for n in names});fb.setupHorizontalHeader(ascent=800,descent=-200)
    fb.setupNameTable({'familyName':'Fixture','styleName':'Regular','uniqueFontIdentifier':'Fixture','fullName':'Fixture','psName':'Fixture'})
    fb.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200);fb.setupPost();fb.setupMaxp()
    buf=BytesIO();fb.save(buf);stream=pdf.make_stream(buf.getvalue());stream.Length1=len(buf.getvalue())
    descriptor=pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.FontDescriptor,FontName=pikepdf.Name.Fixture,Flags=32,FontBBox=[0,-200,500,800],ItalicAngle=0,Ascent=800,Descent=-200,CapHeight=700,StemV=80,FontFile2=stream))
    return pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font,Subtype=pikepdf.Name.TrueType,BaseFont=pikepdf.Name.Fixture,FirstChar=32,LastChar=255,Widths=[500]*224,Encoding=pikepdf.Name.WinAnsiEncoding,FontDescriptor=descriptor))


def layer(name,body=''):
    return f'%AI5_BeginLayer\n1 1 1 1 0 0 1 16 0 0 136 0 50 0 Lb\n({name}) Ln\n{body}\nLB\n%AI5_EndLayer--\n'


def bat(path, mismatch=False, footer=None):
    pdf=pikepdf.Pdf.new();pg=pdf.add_blank_page(page_size=(300,500));disc=pdf.make_stream(b'0.9 0.7 0 0 k -5 -5 10 10 re f')
    disc.Type=pikepdf.Name.XObject;disc.Subtype=pikepdf.Name.Form;disc.BBox=[-5,-5,5,5];disc.Resources=pikepdf.Dictionary()
    props=pikepdf.Dictionary()
    for key,name in [('A','Relevé'),('P','Pictos')]:props['/'+key]=pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.OCG,Name=name))
    if footer:props['/D']=pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.OCG,Name='Date et N° de conception'))
    pg.Resources=pikepdf.Dictionary(Properties=props,Font=pikepdf.Dictionary(F0=font(pdf)),XObject=pikepdf.Dictionary(Disc=disc))
    pdf.Root.OCProperties=pikepdf.Dictionary(OCGs=list(props.values()),D=pikepdf.Dictionary(BaseState=pikepdf.Name.ON))
    ops=['/OC /A BDC 0 G 2 w 40 90 200 360 re S EMC /OC /P BDC'];native=[]
    for i,y in enumerate([410,280,150]):
        ops.append(f'q 1 0 0 -1 80 {y} cm /Disc Do Q')
        ops.append(f'0.9 0.7 0.01 0 K 1 w 80 {y} m 130 {y} l 110 {y} l S')
        ops.append(f'0.9 0.7 0.01 0 k 105 {y} m 115 {y-3} l 115 {y+3} l h f')
        ops.append(f'BT /F0 8 Tf 1 0 0 1 70 {y-24} Tm ({"PIV" if i==2 else "PEV"}) Tj ET')
        native.append(f'/SymbolInstance :\n(Nouveau symbole VEI) /SymbolRef ,\n1 0 0 -1 80 {y-500} /RTransformMatrix\n;\n')
    ops.append('EMC')
    if footer:ops.append(f'/OC /D BDC BT /F0 5 Tf 1 0 0 1 10 20 Tm ({footer}) Tj ET EMC')
    pg.Contents=pdf.make_stream('\n'.join(ops).encode('cp1252'))
    size=6 if mismatch else 5
    definition=f'%AI14_BeginSymbol\n(Nouveau symbole VEI)\n-{size} -5 m\n5 -5 L\n5 5 L\n-5 5 L\n-{size} -5 L\nf\n%AI10_EndSymbol\n'
    data=('%!PS-Adobe-3.0\n%AI3_Cropmarks: 0 -500 300 0\n'+definition+layer('Relevé')+layer('Pictos',''.join(native))+(layer('Date et N° de conception') if footer else '')).encode()
    pg.obj.PieceInfo=pikepdf.Dictionary(Illustrator=pikepdf.Dictionary(Private=pikepdf.Dictionary(AIPrivateData1=pdf.make_stream(PREFIX+zstandard.ZstdCompressor().compress(data)))))
    pdf.save(path)


def template(path):
    pdf=pikepdf.Pdf.new();pg=pdf.add_blank_page(page_size=(841.89,1190.55))
    oc=pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.OCG,Name='Date et N° de conception'))
    pg.Resources=pikepdf.Dictionary(Properties=pikepdf.Dictionary(Zone=oc))
    pg.Contents=pdf.make_stream(b'/OC /Zone BDC 0 0 0 0 K 1 w 40 250 760 700 re S EMC')
    pdf.save(path)


@pytest.fixture
def project(tmp_path,monkeypatch):
    source=tmp_path/'BAT.ai';bat(source)
    directory=tmp_path/'templates'/'doemo';directory.mkdir(parents=True)
    template(directory/'PE-A3-V.pdf');template(directory/'PI-A3-V.pdf')
    monkeypatch.setenv('DOEMO_TEMPLATES_ROOT',str(directory.parent))
    return source,directory


def calls(container, matrix=(1,0,0,1,0,0)):
    """Walk actual Do calls, not unused resources, to count visible VEI forms."""
    stack=[];ctm=matrix
    resources=container.Resources if isinstance(container,pikepdf.Stream) else container.obj.Resources
    for ins in pikepdf.parse_content_stream(container):
        op=str(ins.operator)
        if op=='q':stack.append(ctm)
        elif op=='Q':ctm=stack.pop()
        elif op=='cm':ctm=multiply(ctm,tuple(map(float,ins.operands)))
        elif op=='Do':
            obj=resources.XObject[ins.operands[0]]
            if obj.get('/Subtype')==pikepdf.Name.Form:
                current=multiply(ctm,tuple(map(float,obj.get('/Matrix',(1,0,0,1,0,0)))))
                yield obj.read_bytes(),current
                yield from calls(obj,current)


def test_native_bindings_and_missing_metadata_are_explicit(project):
    source,_=project
    with pikepdf.open(source) as pdf:
        symbols,markers,_=bind(pdf.pages[0],Scene(pdf.pages[0]))
        assert len(symbols)==len(markers)==3
        assert [m.kind for m in markers]==['PE','PE','PI']
        assert [m.id for m in markers]==['p001-vei001','p001-vei002','p001-vei003']
        del pdf.pages[0].obj.PieceInfo
        with pytest.raises(ValueError,match='absentes'):bind(pdf.pages[0],Scene(pdf.pages[0]))


def test_three_pdfs_one_actual_vei_call_each_and_complete_zip(project,tmp_path):
    source,_=project;original=source.read_bytes();destination=tmp_path/'batch'
    info=inspect_generation(source);assert info['generation_available'] and info['marker_count']==3
    assert all('path' not in template for template in info['templates'])
    report=generate_batch(source,destination)
    assert report['count']==3 and source.read_bytes()==original
    with pikepdf.open(source) as pdf:disc=pdf.pages[0].Resources.XObject.Disc.read_bytes()
    for row in report['results']:
        with pikepdf.open(destination/row['file']) as pdf:
            drawn=list(calls(pdf.pages[0]));discs=[m for stream,m in drawn if stream==disc]
            assert len(discs)==1  # Inactive disc resources may exist but must never be painted.
            assert discs[0][1]==pytest.approx(0,abs=1e-8)
            assert discs[0][2]==pytest.approx(0,abs=1e-8)  # Counterrotation keeps the disc upright.
            assert not any(b'(PEV)' in stream or b'(PIV)' in stream for stream,_ in drawn)
            assert len(pdf.pages)==1
        assert row['direction_after'][0]==pytest.approx(0,abs=1e-8)
        assert row['direction_after'][1]>0
    with zipfile.ZipFile(destination/'plans.zip') as archive:
        assert archive.testzip() is None
        assert set(archive.namelist())=={'rapport.json',*(x['file'] for x in report['results'])}
        for row in report['results']:assert hashlib.sha256(archive.read(row['file'])).hexdigest()==row['sha256']


def test_failure_never_publishes_partial_zip(project,tmp_path):
    source,templates=project;(templates/'PI-A3-V.pdf').unlink()
    with pytest.raises(ValueError,match='absente'):generate_batch(source,tmp_path/'failed')
    assert not (tmp_path/'failed').exists()
    assert not list(tmp_path.glob('.lot-*'))


def test_no_overwrite(project,tmp_path):
    source,_=project;destination=tmp_path/'existing';destination.mkdir();sentinel=destination/'mine';sentinel.write_text('keep')
    with pytest.raises(ValueError,match='écraser'):generate_batch(source,destination)
    assert sentinel.read_text()=='keep'


def test_changed_symbol_geometry_is_refused(project,tmp_path):
    source,_=project;bat(source,mismatch=True)
    with pytest.raises(ValueError,match='différente'):generate_batch(source,tmp_path/'bad')
    assert not (tmp_path/'bad').exists()


def test_different_client_never_falls_back(project,tmp_path):
    source,_=project
    with pytest.raises(ValueError):generate_batch(source,tmp_path/'bad',client='autre')
    assert not (tmp_path/'bad').exists()


def test_bounds_respect_image_clip_and_retain_original_stream():
    pdf=pikepdf.Pdf.new();pg=pdf.add_blank_page(page_size=(200,200));image=pdf.make_stream(b'\xff\x00\x00');image.Type=pikepdf.Name.XObject;image.Subtype=pikepdf.Name.Image;image.Width=1;image.Height=1;image.BitsPerComponent=8;image.ColorSpace=pikepdf.Name.DeviceRGB
    pg.Resources=pikepdf.Dictionary(XObject=pikepdf.Dictionary(Logo=image));pg.Contents=pdf.make_stream(b'q 20 30 40 50 re W n 100 0 0 100 0 0 cm /Logo Do Q')
    scene=Scene(pg);assert scene.items[0].bounds==(20,30,60,80)
    assert b'20 30 40 50 re' in scene.items[0].stream and b'/Logo Do' in scene.items[0].stream


def test_geometry_matching_is_not_a_bounding_box_test():
    square=[('m',0,0),('l',10,0),('l',10,10),('l',0,10),('h',)]
    triangle=[('m',0,0),('l',10,0),('l',0,10),('h',)]
    assert outlines_match(square,square)
    assert not outlines_match(square,triangle)


def test_optional_levels_clip_pe_but_never_pi(project,tmp_path):
    from doemo_pdf.levels import new_document
    source,_=project;doc=new_document(source)
    doc['markers']=[{'id':f'p001-vei{i:03d}','page':1,'point':[80,y]} for i,y in enumerate([410,280,150],1)]
    doc['levels']=[{'id':'rdc','name':'RDC','page':1,'color':'#ff0000','vei_ids':['p001-vei001','p001-vei002'],
                    'contours':[{'id':'l','role':'include','fill_rule':'nonzero','nodes':[{'x':x,'y':y} for x,y in [(30,240),(180,240),(180,350),(260,350),(260,460),(30,460)]]}]}]
    doc['review_acknowledged']=True
    report=generate_batch(source,tmp_path/'clipped',levels=doc)
    for row in report['results']:
        with pikepdf.open(tmp_path/'clipped'/row['file']) as pdf:
            clips=[stream for stream,_ in calls(pdf.pages[0]) if b'W\nn' in stream]
            assert bool(clips)==(row['type']=='PE')
            assert row['level']==('rdc' if row['type']=='PE' else None)
    # Saved contours do not take effect unless the caller explicitly supplies them.
    full=generate_batch(source,tmp_path/'whole')
    assert all(row['level'] is None for row in full['results'])


def test_fragment_hashes_are_stable_across_processes(project):
    import os,subprocess,sys
    source,_=project
    code="import sys,pikepdf,hashlib; from doemo_pdf.scene import Scene; p=pikepdf.open(sys.argv[1]); print(hashlib.sha256(b''.join(x.stream for x in Scene(p.pages[0]).items)).hexdigest())"
    hashes=[subprocess.check_output([sys.executable,'-c',code,str(source)],env={**os.environ,'PYTHONHASHSEED':seed}) for seed in ['1','2']]
    assert hashes[0]==hashes[1]


def test_clip_cannot_silently_hide_active_vei(project,tmp_path):
    from doemo_pdf.levels import new_document
    source,_=project;doc=new_document(source)
    doc['markers']=[{'id':'p001-vei001','page':1,'point':[80,410]}]
    doc['levels']=[{'id':'rdc','name':'RDC','page':1,'color':'#ff0000','vei_ids':['p001-vei001'],
                    'contours':[{'id':'small','role':'include','fill_rule':'nonzero','nodes':[{'x':x,'y':y} for x,y in [(20,20),(30,20),(30,30),(20,30)]]}]}]
    with pytest.raises(ValueError,match='zone occupée par le VEI'):generate_batch(source,tmp_path/'bad-clip',levels=doc)
    assert not (tmp_path/'bad-clip').exists()


def test_legend_frames_and_bottom_footer_date_and_sequence(project,tmp_path,monkeypatch):
    source,_=project
    bat(source,footer='Mise à jour n° 1 - Date et n° du plan : 27-10-2026 - CO26100364-1')
    # Date must be captured once per lot, not individually for each PDF.
    dates=iter([date(2026,10,28)])
    monkeypatch.setattr('doemo_pdf.generate.batch_date',lambda:next(dates))
    destination=tmp_path/'dated';report=generate_batch(source,destination)
    assert report['generation_date']=='2026-10-28'
    for n,row in enumerate(report['results'],1):
        expected=f'Mise à jour n° 1 - Date et n° du plan : 28-10-2026 - CO26100364-{n}'
        assert row['footer_text']==expected and row['plan_reference']==f'CO26100364-{n}'
        text=PdfReader(destination/row['file']).pages[0].extract_text()
        assert text.count(expected)==1 and '27-10-2026' not in text
        assert 0<row['layout']['footer_bounds'][1]<row['layout']['footer_bounds'][3]<16
        with pikepdf.open(destination/row['file']) as pdf:
            ops=pikepdf.parse_content_stream(pdf.pages[0])
            # Check actual page operators: one closed, stroked coloured frame.
            colours=[tuple(map(float,ins.operands)) for ins in ops if str(ins.operator)=='K']
            assert colours==[(1.,0.,1.,0.) if row['type']=='PE' else (0.,.99,.97,0.)]
            rects=[tuple(map(float,ins.operands)) for ins in ops if str(ins.operator)=='re']
            x0,y0,x1,y1=row['layout']['legend_frame']
            assert rects==[pytest.approx((x0,y0,x1-x0,y1-y0))]
            assert y0>row['layout']['zone'][1]


def test_footer_keeps_revision_and_handles_double_digit_plan_numbers():
    from types import SimpleNamespace
    from doemo_pdf.generate import footer_label
    scene=SimpleNamespace(items=[SimpleNamespace(kind='text',text='Mise à jour n° 4 - Date et n° du plan : 31-12-2025 - CLIENT-A-9',bounds=(0,0,10,10))])
    text,reference=footer_label(scene,[0],12,date(2027,1,1))
    assert text=='Mise à jour n° 4 - Date et n° du plan : 01-01-2027 - CLIENT-A-12'
    assert reference=='CLIENT-A-12'


def test_unique_vei_stem_may_start_off_center_inside_disc(project,tmp_path):
    source,_=project
    modified=tmp_path/'off-centre.ai'
    with pikepdf.open(source) as pdf:
        data=pdf.pages[0].Contents.read_bytes().replace(b'80 410 m',b'80.5 410 m')
        pdf.pages[0].Contents=pdf.make_stream(data);pdf.save(modified)
    with pikepdf.open(modified) as pdf:
        _,markers,_=bind(pdf.pages[0],Scene(pdf.pages[0]));assert len(markers)==3
        pdf.pages[0].Contents=pdf.make_stream(data+b'\n/OC /P BDC .9 .7 .01 0 K 80 410 m 100 410 l S EMC')
        with pytest.raises(ValueError,match='Tige VEI absente ou ambiguë'):bind(pdf.pages[0],Scene(pdf.pages[0]))


def test_pdf_without_native_data_gives_actionable_ai_import_message(tmp_path):
    source=tmp_path/'export.pdf'
    with pikepdf.Pdf.new() as pdf:
        pg=pdf.add_blank_page();pg.Contents=pdf.make_stream(b'/Layer /MC0 BDC EMC');pdf.save(source)
    with pytest.raises(ValueError,match='Importez le fichier .ai original'):inspect_generation(source)


def test_template_retains_its_blending_space_when_bat_has_cmyk_icc(project,tmp_path):
    source,templates=project;modified=tmp_path/'icc.ai'
    with pikepdf.open(source) as pdf:
        profile=pdf.make_stream(b'ICC fixture');profile.N=4
        pdf.pages[0].obj.Group=pikepdf.Dictionary(S=pikepdf.Name.Transparency,CS=pikepdf.Array([pikepdf.Name.ICCBased,profile]))
        pdf.save(modified)
    for template_path in templates.glob('*.pdf'):
        with pikepdf.open(template_path,allow_overwriting_input=True) as pdf:
            pdf.pages[0].obj.Group=pikepdf.Dictionary(S=pikepdf.Name.Transparency,CS=pikepdf.Name.DeviceCMYK)
            pdf.save(template_path)
    report=generate_batch(modified,tmp_path/'icc-batch')
    for row in report['results']:
        with pikepdf.open(tmp_path/'icc-batch'/row['file']) as pdf:
            assert pdf.pages[0].obj.Group.CS[1].read_bytes()==b'ICC fixture'
            groups=[obj.Group for obj in pdf.pages[0].Resources.XObject.values() if '/Group' in obj]
            assert len(groups)==1 and groups[0].CS==pikepdf.Name.DeviceCMYK and groups[0].I
