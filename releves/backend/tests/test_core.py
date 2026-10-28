import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from doemo_releves.library import import_library, safe_path
from doemo_releves.registration import project, solve
from doemo_releves.recognition import local_proposals, ocr
from doemo_releves.models import ProjectState, Annotation, Box, Point, Floor, Registration, Review, Mapping
from doemo_releves.exchange import export_placements, validate_state


def minimal_pdf():
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Resources << >> /Contents 4 0 R >>',
               b'<< /Length 0 >>\nstream\n\nendstream']
    out = b'%PDF-1.4\n'; offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out)); out += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    at = len(out); out += b'xref\n0 5\n0000000000 65535 f \n'
    out += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets)
    return out + f'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{at}\n%%EOF\n'.encode()


def library_fixture(tmp_path, extra=None, bad_hash=False, mismatched_component=False):
    content = minimal_pdf()
    checksum = hashlib.sha256(content).hexdigest()
    manifest = {'children': [{'id':'asset1','name':'Déclencheur', 'type':'application/vnd.adobe.element.image+dcx',
        'path':'asset1','components':[{'path':'test.ai','type':'application/illustrator','length':len(content),'library#sha256':checksum}]}]}
    data = {'source_library_name':'test', 'source_library_id':'test', 'total_items':1, 'counts_by_type':{'image':1},
        'assets':[{'id':'asset1','name':'Déclencheur','type':'application/vnd.adobe.element.image+dcx', 'groups':['Incendie'],
        'components':[{'type':'application/illustrator','role':'primary','archive_path':'asset1/test.ai',
                       'size_bytes':len(content),'sha256':'0'*64 if bad_hash else checksum}]}]}
    if mismatched_component:
        manifest['children'][0]['components'][0]['path'] = 'different.ai'
    inventory = tmp_path/'inventory.json'; inventory.write_text(json.dumps(data))
    archive = tmp_path/'sai.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('manifest',json.dumps(manifest));z.writestr('asset1/test.ai',content)
        if extra: z.writestr(*extra)
    return inventory, archive


@pytest.mark.parametrize('path',['../escape.ai','/root.ai','a/../b','a\\b','C:/x','a//b','a/./b'])
def test_archive_paths(path):
    with pytest.raises(ValueError): safe_path(path)


def test_real_import_contract_and_provisional_catalog(tmp_path):
    inventory, archive = library_fixture(tmp_path)
    provisional = import_library(inventory,tmp_path/'provisional')
    assert not provisional['archive_verified'] and not provisional['assets'][0]['verified']
    native = import_library(inventory,tmp_path/'native',archive)
    assert native['archive_verified'] and native['assets'][0]['preview']
    assert (tmp_path/'native/asset1/test.ai').read_bytes()==minimal_pdf()
    assert not native['assets'][0]['approved']


@pytest.mark.parametrize('option',[{'extra':('../escape',b'x')},{'bad_hash':True},{'mismatched_component':True}])
def test_invalid_archive_is_atomic(tmp_path,option):
    inventory,archive=library_fixture(tmp_path,**option)
    with pytest.raises(ValueError): import_library(inventory,tmp_path/'bad',archive)
    assert not (tmp_path/'bad').exists()
    assert not list(tmp_path.glob('.sai-*'))


def test_symbolic_link_archive_refused(tmp_path):
    inventory, archive = library_fixture(tmp_path)
    with zipfile.ZipFile(archive,'a') as z:
        entry=zipfile.ZipInfo('link');entry.create_system=3;entry.external_attr=0o120777<<16;z.writestr(entry,'/etc/passwd')
    with pytest.raises(ValueError,match='Liens'):import_library(inventory,tmp_path/'bad',archive)


def test_registration_measures_independent_error():
    source=[[.1,.1],[.8,.1],[.1,.8],[.8,.8]]
    target=[[.15,.2],[.85,.2],[.15,.9],[.85,.9]]
    result=solve(source,target,'affine',1000,1000,[[.4,.4]],[[.45,.5]])
    assert result['check_error_px']<1e-8
    bad=solve(source,target,'affine',1000,1000,[[.4,.4]],[[.6,.5]])
    assert bad['check_error_px']==pytest.approx(150)
    with pytest.raises(ValueError,match='indépendant'):solve(source,target,'affine',1000,1000,[source[0]],[target[0]])
    with pytest.raises(ValueError):solve([[0,0],[.5,.5],[1,1]],[[0,0],[.5,.5],[1,1]],'affine',100,100,[[.3,.4]],[[.3,.4]])


def test_perspective_and_singularity():
    matrix=np.array([[.7,.03,.1],[.02,.8,.1],[.2,.1,1]])
    source=[[0,0],[1,0],[1,1],[0,1],[.2,.4]]
    target=project(matrix,source).tolist()
    result=solve(source,target,'homography',2000,1500,[[.7,.5]],project(matrix,[[.7,.5]]).tolist())
    assert result['check_error_px']<.001
    with pytest.raises(ValueError): project([[1,0,0],[0,1,0],[0,0,0]],[[.3,.2]])


def project_fixture():
    points=[Point(x=.1,y=.1),Point(x=.9,y=.1),Point(x=.1,y=.9)]
    reg=Registration(source_document_id='survey',source_page=1,floor_id='rdc',model='affine',matrix=[[1,0,0],[0,1,0],[0,0,1]],source_points=points,target_points=points,check_source_points=[Point(x=.6,y=.6)],check_target_points=[Point(x=.6,y=.6)],fit_error_px=0,check_error_px=0,max_error_px=5,confirmed=True,architecture_confirmed=True)
    state=ProjectState(revision=4,library_id='sai',floors=[Floor(id='rdc',name='RDC',target_page=1,artboard_index=0,confirmed=True)],registrations=[reg],
        mappings=[Mapping(annotation='DM',equipment_type='DM',asset_id='asset',confirmed=True)],annotations=[Annotation(id='mark1',source_document_id='survey',source_page=1,bbox=Box(x=.2,y=.2,w=.02,h=.02),anchor=Point(x=.21,y=.21),anchor_kind='manual',text='DM',equipment_type='DM',asset_id='asset',floor_id='rdc',status='confirmed',review=Review(**{key:True for key in Review.model_fields}))])
    documents=[{'id':'survey','role':'survey','pages':[{'width':1000,'height':1000}]},{'id':'target','role':'target','sha256':'a'*64,'name':'bat.ai','pages':[{'width':1000,'height':1000,'pdf_size_pt':[500,500]}]}]
    library={'id':'sai','archive_verified':True,'assets':[{'id':'asset','verified':True,'approved':True,'pictogram_candidate':True,'name':'DM','components':[{'archive_path':'asset/file.ai','sha256':'b'*64,'role':'primary'}]}]}
    return {'id':'test','state':state.model_dump(),'documents':documents},library


def test_export_exact_illustrator_frame_and_no_unknowns():
    p,library=project_fixture()
    result=export_placements(p,library)
    assert result['placements'][0]['x']==pytest.approx(105)
    assert result['placements'][0]['y']==pytest.approx(105)
    assert result['report']['placed_in_illustrator'] is None
    assert result['coordinate_system']['y_axis']=='down'


@pytest.mark.parametrize('case',['provisional','unapproved','position','floor','mapping','architecture','uncertain','spoofed_registration'])
def test_export_gates(case):
    p,library=project_fixture();s=p['state']
    if case=='provisional':library['archive_verified']=False
    if case=='unapproved':library['assets'][0]['approved']=False
    if case=='position':s['annotations'][0]['review']['position']=False
    if case=='floor':s['floors'][0]['confirmed']=False
    if case=='mapping':s['mappings'][0]['confirmed']=False
    if case=='architecture':s['registrations'][0]['architecture_confirmed']=False
    if case=='uncertain':s['annotations'][0]['status']='uncertain_position'
    if case=='spoofed_registration':s['registrations'][0]['check_target_points'][0]['x']=.9
    with pytest.raises(ValueError):export_placements(p,library)


def test_client_matrix_is_recomputed():
    p,_=project_fixture();s=ProjectState.model_validate(p['state']);s.registrations[0].matrix=[[8,0,0],[0,8,0],[0,0,1]]
    validate_state(s,p['documents']);assert s.registrations[0].matrix[0][0]==pytest.approx(1)


def test_colors_produce_evidence_never_equipment(monkeypatch):
    import doemo_releves.recognition as module
    monkeypatch.setattr(module,'ocr',lambda _: ([] ,None))
    image=np.full((400,400,3),255,dtype=np.uint8)
    import cv2
    cv2.circle(image,(180,210),5,(255,0,0),-1)
    annotations,info=local_proposals(image,'doc',1)
    assert len(annotations)==1 and annotations[0].color=='red'
    assert not annotations[0].equipment_type and annotations[0].status!='confirmed'
    assert not any(annotations[0].review.model_dump().values())
    assert annotations[0].bbox.x<.45<annotations[0].bbox.x+annotations[0].bbox.w


def test_ocr_quotes_do_not_swallow_subsequent_lines(monkeypatch):
    import doemo_releves.recognition as module
    class Result:
        stdout=b'level\tleft\ttop\twidth\theight\tconf\ttext\n5\t2\t3\t4\t5\t90\t"\n5\t8\t3\t4\t5\t90\tDM\n'
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:Result())
    rows,_=ocr(np.zeros((20,20,3),dtype=np.uint8))
    assert len(rows)==2 and rows[1]['text']=='DM'
