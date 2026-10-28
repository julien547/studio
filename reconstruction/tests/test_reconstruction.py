import copy
import json
import math
import pytest
from doemo_reconstruction.geometry import wall, pair_boundaries, solid_intervals, joined_polygon, edit, validate
from doemo_reconstruction.export import export_svg, connector_payload, training_records
from doemo_reconstruction.extract import reconstruct, pdf_transform, transform
from doemo_reconstruction.regions import separate_levels


def document():
    return {'schema':'doemo.architecture/1','revision':0,'history':[], 'source':{'sha256':'fixture'},
            'levels':[{'id':'L','source_page':1,'name':'Test','width':200,'height':100,'unit':'pt',
                       'coordinate':{},'scale':None,'floor_validated':False,'reference':'data:image/png;base64,',
                       'walls':[wall([10,20],[100,20],4)]}]}


def test_pairing_is_angle_independent_and_thickness_measured():
    walls=pair_boundaries([([10,10],[50,50]),([12,8],[52,48])])
    assert len(walls)==1
    assert walls[0]['thickness']==pytest.approx(math.sqrt(8))
    assert walls[0]['status']=='pending'


def test_gap_is_never_bridged():
    lines=[([10,10],[40,10]),([10,14],[40,14]),([60,10],[90,10]),([60,14],[90,14])]
    walls=pair_boundaries(lines)
    assert len(walls)==2
    assert all(not min(w['a'][0],w['b'][0])<50<max(w['a'][0],w['b'][0]) for w in walls)


def test_openings_subtracted_not_painted_over():
    w=wall([0,10],[100,10],4)
    w['openings']=[{'start':.2,'end':.3},{'start':.6,'end':.8}]
    assert solid_intervals(w)==[(0,.2),(.3,.6),(.8,1)]


def test_exact_l_junction_miter_has_shared_edges():
    a=wall([10,20],[50,20],4);b=wall([50,20],[50,70],6)
    pa,pb=joined_polygon(a,[a,b]),joined_polygon(b,[a,b])
    assert pa[1]==pytest.approx(pb[0])
    assert pa[2]==pytest.approx(pb[3])
    assert pa[2]==pytest.approx([53,18])


def test_disconnected_walls_do_not_snap():
    a=wall([10,20],[50,20],4);b=wall([52,20],[52,70],4)
    assert max(p[0] for p in joined_polygon(a,[a,b]))==50


def test_edit_is_transactional_and_requires_reapproval():
    d=document();wid=d['levels'][0]['walls'][0]['id']
    d=edit(d,'L',{'op':'approve','id':wid},'Alice')
    assert len(training_records(d))==1
    changed=edit(d,'L',{'op':'update','id':wid,'thickness':7},'Alice')
    assert changed['levels'][0]['walls'][0]['status']=='pending'
    assert training_records(changed)==[]
    assert d['levels'][0]['walls'][0]['thickness']==4
    with pytest.raises(ValueError):edit(d,'L',{'op':'update','id':wid,'thickness':-1},'Alice')
    assert d['revision']==1


def test_export_draft_and_approved_are_separate():
    d=document();l=d['levels'][0]
    assert '<path' not in export_svg(l)
    assert '<path' in export_svg(l,False)
    assert 'display:none' in export_svg(l)
    d=edit(d,'L',{'op':'approve','id':l['walls'][0]['id']},'Alice')
    assert '<path' in export_svg(d['levels'][0])
    assert d['levels'][0]['scale'] is None
    with pytest.raises(ValueError):connector_payload(d)
    d=edit(d,'L',{'op':'identify_floor','validated':True},'Alice')
    assert connector_payload(d)['levels'][0]['unit']=='pt'


def test_calibration_requires_validated_dimension_and_evidence():
    d=document()
    with pytest.raises(ValueError):edit(d,'L',{'op':'calibrate','a':[0,0],'b':[0,0],'length_mm':10,'evidence':'cote'},'Alice')
    with pytest.raises(ValueError):edit(d,'L',{'op':'calibrate','a':[0,0],'b':[100,0],'length_mm':10,'evidence':''},'Alice')
    d=edit(d,'L',{'op':'calibrate','a':[0,0],'b':[100,0],'length_mm':1000,'evidence':'relevé vérifié'},'Alice')
    assert d['levels'][0]['scale']['mm_per_unit']==10


@pytest.mark.parametrize('rotation,origin',[(0,[0,100]),(90,[0,0]),(180,[200,0]),(270,[100,200])])
def test_pdf_crop_and_rotation(rotation,origin):
    assert transform([10,20],pdf_transform([10,20,210,120],rotation))==origin


def test_invalid_openings_and_nonfinite_coordinates_rejected():
    d=document();w=d['levels'][0]['walls'][0]
    w['openings']=[{'start':.5,'end':.7,'kind':'door','status':'approved'},
                   {'start':.6,'end':.8,'kind':'window','status':'approved'}]
    with pytest.raises(ValueError):validate(d)
    w['openings']=[];w['a'][0]=float('nan')
    with pytest.raises(ValueError):validate(d)


def test_multiple_floors_same_page_keep_coordinates_and_unique_ids():
    d=document();d['levels'][0]['walls'].append(wall([120,20],[180,20],4))
    out=separate_levels(d,[{'id':'left','name':'R-1','source_page':1,'bbox':[0,0,110,100]},
                          {'id':'right','name':'RDC','source_page':1,'bbox':[110,0,200,100]}])
    assert len(out['levels'])==2
    assert out['levels'][1]['walls'][0]['a']==[120,20]
    assert all(l['width']==200 and l['scale'] is None for l in out['levels'])


def test_real_pdf_vector_recovery_precedes_raster(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject,NameObject
    writer=PdfWriter();page=writer.add_blank_page(200,100)
    stream=DecodedStreamObject();stream.set_data(b'0 0 0 RG 10 20 m 100 20 l S 10 24 m 100 24 l S')
    page[NameObject('/Contents')]=writer._add_object(stream)
    path=tmp_path/'vector.pdf'
    with path.open('wb') as f:writer.write(f)
    out=reconstruct(path)
    level=out['levels'][0]
    assert level['method']=='vector'
    assert len(level['raw_vectors'])==2
    # Independent native strokes are no longer guessed to be opposite wall faces.
    assert len(level['walls'])==2
    assert all(w['thickness'] is None for w in level['walls'])
    from doemo_reconstruction.axis_review import review_axes
    report=review_axes(level)
    assert len(report)==1 and not report[0]['resolved']
    assert level['scale'] is None


def test_existing_engine_adapter_preserves_units_and_refuses_overwrite():
    from doemo_reconstruction.studio_adapter import import_analysis
    d=document();d['levels'][0]['walls']=[]
    analysis={'schemaVersion':3,'coordinateSpace':'source','engineVersion':'doemo-local-0.24.0',
              'source':{'page':1,'width':400,'height':200,'rotation':0},
              'walls':[{'id':'old','a':{'x':20,'y':40},'b':{'x':200,'y':40},'thickness':8,
                        'confidence':.7,'warnings':[],'evidence':'parallel_faces'}],
              'openings':[{'type':'Opening','wallId':'old','offset':60,'width':20}]}
    out=import_analysis(d,'L',analysis);w=out['levels'][0]['walls'][0]
    assert w['a']==[10,20] and w['b']==[100,20]
    assert w['thickness']==pytest.approx(4)
    assert w['openings'][0]['start']==pytest.approx(1/3)
    assert w['status']=='pending' and out['levels'][0]['scale'] is None
    with pytest.raises(ValueError):import_analysis(out,'L',analysis)
