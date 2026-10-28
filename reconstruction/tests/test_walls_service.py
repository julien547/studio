import base64
import io
import importlib.util
import json
from pathlib import Path
import tarfile
import threading
import time
import xml.etree.ElementTree as ET

import httpx
import numpy as np
import pytest
from PIL import Image
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from doemo_reconstruction.geometry import wall,edit,solid_intervals,axis_points,validate
from doemo_reconstruction.export import export_svg,connector_payload
from doemo_reconstruction.wall_module import reconstruct_mask,CLASSES
from doemo_reconstruction.ai_service.auth import issue,verify
from doemo_reconstruction.ai_service.jobs import JobStore
from doemo_reconstruction.ai_service.runpod import RunPod,IdleController
from doemo_reconstruction.ai_service.worker import Worker,create_worker
from doemo_reconstruction.ai_service.service import Orchestrator,create_app
from test_reconstruction import document


def keys():
    key=Ed25519PrivateKey.generate()
    return (key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()),
            key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))


def request():
    import hashlib
    image=Image.new('RGB',(16,16),'white');data=io.BytesIO();image.save(data,format='PNG');binary=data.getvalue()
    return {'project_id':'test-project','page':1,'source_sha256':'a'*64,'image_sha256':hashlib.sha256(binary).hexdigest(),
            'image_base64':base64.b64encode(binary).decode(),'width':16,'height':16,'regions':[],
            'engines':['qwen'],'model_versions':{'qwen':'test'},'parameters':{}}


def test_centerline_black_open_and_independent_of_measured_width():
    d=document();l=d['levels'][0];w=l['walls'][0];w['status']='approved';l['stroke_width']=1.25
    w['openings']=[{'kind':'door','start':.25,'end':.5,'status':'approved'}]
    before=export_svg(l);w['thickness']=20;assert export_svg(l)==before
    svg=ET.fromstring(before);paths=svg.findall('.//{http://www.w3.org/2000/svg}path')
    assert len(paths)==2 and not svg.findall('.//{http://www.w3.org/2000/svg}polygon')
    for p in paths:
        assert p.attrib['stroke']=='#000000' and p.attrib['fill']=='none'
        assert p.attrib['stroke-width']=='1.25' and p.attrib['stroke-linecap']=='butt'
        assert 'Z' not in p.attrib['d'] and 'stroke-dasharray' not in p.attrib
    l['floor_validated']=True;payload=connector_payload(d)
    assert payload['schema'].endswith('/2') and 'polygons' not in payload['levels'][0]['walls'][0]
    assert payload['levels'][0]['walls'][0]['paths'][0]==[[10,20],[32.5,20]]


def test_unknown_physical_thickness_does_not_invent_scale():
    d=document();l=d['levels'][0];l['walls'][0]['thickness']=None
    validate(d);assert '<path' in export_svg(l,False);assert l['scale'] is None


def test_split_preserves_opening_position_and_revokes_approval():
    d=document();w=d['levels'][0]['walls'][0];w['status']='approved'
    w['openings']=[{'kind':'door','start':.3,'end':.7,'status':'approved'}]
    out=edit(d,'L',{'op':'split','id':w['id'],'fraction':.5},'Alice')
    parts=out['levels'][0]['walls'];assert len(parts)==2
    endpoints=[axis_points(p,lo,hi) for p in parts for lo,hi in solid_intervals(p)]
    assert endpoints==[[[10,20],[37,20]],[[73,20],[100,20]]]
    assert all(p['status']=='pending' for p in parts)


def test_opening_correction_is_transactional():
    d=document();w=d['levels'][0]['walls'][0];w['openings']=[{'kind':'door','start':.2,'end':.4,'status':'pending'}]
    out=edit(d,'L',{'op':'update_opening','id':w['id'],'index':0,'start':.3,'end':.5,'kind':'passage','status':'approved'},'Alice')
    assert out['levels'][0]['walls'][0]['openings'][0]['start']==.3
    with pytest.raises(ValueError):edit(out,'L',{'op':'update_opening','id':w['id'],'index':0,'start':.8,'end':.2,'kind':'door','status':'approved'},'Alice')
    assert d['levels'][0]['walls'][0]['openings'][0]['start']==.2


def segment(labels):
    return reconstruct_mask(labels,classes=CLASSES,source_sha256='a'*64,model_sha256='b'*64,
                            document_size=[128,128],image_to_document=[2,0,0,2,0,0])


def test_specialized_mask_module_preserves_door_gap():
    labels=np.zeros((64,64),np.uint8);labels[28:35,5:59]=1;labels[28:35,28:36]=3
    result=segment(labels);assert result['walls']
    for w in result['walls']:
        assert not min(w['a'][0],w['b'][0])<64<max(w['a'][0],w['b'][0])
        assert w['status']=='pending' and w['thickness']>0
    assert result['scale'] is None


def test_specialized_mask_module_keeps_diagonal_orientation():
    import cv2
    labels=np.zeros((64,64),np.uint8);cv2.line(labels,(10,12),(50,52),1,7)
    result=segment(labels);assert any(abs(w['b'][0]-w['a'][0])>20 and abs(w['b'][1]-w['a'][1])>20 for w in result['walls'])
    for w in result['walls']:assert abs((w['b'][1]-w['a'][1])-(w['b'][0]-w['a'][0]))<3


def test_generic_detection_boxes_cannot_be_used_as_wall_masks():
    with pytest.raises(ValueError):segment({'boxes':[[1,2,3,4]]})


def test_short_lived_signed_tokens_reject_expiry_scope_and_tamper():
    private,public=keys();token=issue(private,'worker','jobs',now=100,ttl=60)
    verify(public,token,'worker','jobs',now=110)
    for t,a,s,n in [(token,'worker','jobs',160),(token,'other','jobs',110),(token,'worker','control',110),(token+'x','worker','jobs',110)]:
        with pytest.raises(ValueError):verify(public,t,a,s,now=n)


def test_queue_retry_durable_result_and_idempotency(tmp_path):
    store=JobStore(tmp_path/'jobs.sqlite');req=request();job_id=store.submit('analyze',req,'key')
    assert store.submit('analyze',req,'key')==job_id
    with pytest.raises(ValueError):store.submit('analyze',{**req,'page':2},'key')
    job=store.claim();assert job['attempt']==1
    store.fail(job_id,'test failure');assert store.submit('analyze',req,'key')==job_id
    assert store.claim()['attempt']==2
    store.stage(job_id,'saving',90);store.finish(job_id,{'status':'pending'})
    reopened=JobStore(tmp_path/'jobs.sqlite');assert reopened.get(job_id)['result']=={'status':'pending'}
    assert reopened.submit('analyze',req,'key')==job_id;assert reopened.claim() is None
    assert [a['stage'] for a in reopened.get(job_id)['attempts']]==['running','failed','running','saving','completed']
    with pytest.raises(ValueError):store.finish(job_id,{'replacement':True})


def test_restart_does_not_retry_unknown_remote_job_or_allow_stop(tmp_path):
    store=JobStore(tmp_path/'jobs.sqlite');job_id=store.submit('analyze',request(),'key');store.claim();store.recover()
    assert store.get(job_id)['status']=='interrupted' and store.claim() is None
    assert not store.idle(time.time()+4000)
    with pytest.raises(ValueError):store.reconcile(job_id,False)
    store.reconcile(job_id,True);assert store.claim()['attempt']==2


def test_runpod_migration_discovery_and_official_start_route():
    calls=[];pods=[{'id':'new-id','name':'migrated-name','env':{'DOEMO_SERVICE_ID':'DOEMO-STUDIO-IA'},'networkVolumeId':'volume','desiredStatus':'EXITED'}]
    def transport(r):
        calls.append((r.method,r.url.path));return httpx.Response(200,json=pods if r.method=='GET' else {})
    pod=RunPod('unused','volume',client=httpx.Client(base_url='https://rest.runpod.io/v1',transport=httpx.MockTransport(transport)))
    assert pod.ensure_started()['id']=='new-id';assert calls==[('GET','/v1/pods'),('POST','/v1/pods/new-id/start')]
    pods.append({**pods[0],'id':'other-id'})
    with pytest.raises(RuntimeError):pod.discover()
    assert not hasattr(pod,'delete')


def test_idle_stop_waits_thirty_minutes_and_respects_unsaved_and_admission(tmp_path):
    store=JobStore(tmp_path/'jobs.sqlite');job_id=store.submit('analyze',request(),'key');store.claim();store.stage(job_id,'saving',90)
    class Pod:
        stopped=False
        def discover(self):return {'id':'current','desiredStatus':'RUNNING'}
        def stop(self,expected):self.stopped=True
    class Remote:
        unsaved=0;drained=False
        def health(self,pod):return {'ready':True,'active':0,'queued':0,'unsaved':self.unsaved,'stop_safe':True,'pod_id':'current'}
        def drain(self,pod):self.drained=True;return True
    pod=Pod();remote=Remote();guard=IdleController(store,pod,remote,threading.RLock());now=time.time()
    assert not guard.tick(now+4000) # saving blocks even after a long wait
    store.finish(job_id,{'status':'pending'});guard.last_busy=now
    assert not guard.tick(now+1799)
    remote.unsaved=1;assert not guard.tick(now+1801) and not pod.stopped
    remote.unsaved=0;assert not guard.tick(now+2000)
    assert guard.tick(now+3602) and pod.stopped and remote.drained


def test_private_api_auth_and_specialized_model_unavailable(tmp_path):
    private,public=keys();orch=Orchestrator(JobStore(tmp_path/'jobs.sqlite'),None,None)
    client=TestClient(create_app(orch,public,start_worker=False))
    assert client.get('/health').status_code==401
    headers={'Authorization':'Bearer '+issue(private,'doemo-orchestrator','jobs'),'Idempotency-Key':'one'}
    assert client.get('/health',headers=headers).status_code==200
    assert client.post('/jobs/detect-walls',headers=headers).json()['detail']['code']=='architectural_segmentation_not_qualified'
    response=client.post('/jobs/analyze-floorplan',headers=headers,json=request());assert response.status_code==202
    assert client.get('/jobs/'+response.json()['id']+'/results',headers=headers).status_code==409
    assert client.post('/jobs/analyze-floorplan',headers=headers,json=request()).json()['id']==response.json()['id']


def test_worker_commits_results_once_without_rerunning_inference(tmp_path):
    class Engines:
        config={'qwen':{'version':'test'}};calls=0
        def run(self,name,request):self.calls+=1;return {'zones':[],'model_version':'test'}
    engines=Engines();worker=Worker(engines,tmp_path/'exports');worker.ready=True
    job_id='aa862ad6-5f6b-47df-b82b-b3d9b203ebee'
    first=worker.infer(job_id,request());assert worker.infer(job_id,request())==first;assert engines.calls==1
    assert worker.health()['unsaved']==0
    with pytest.raises(ValueError):worker.infer(job_id,{**request(),'page':2})


def test_restore_rejects_traversal_and_escaping_symlink(tmp_path):
    spec=importlib.util.spec_from_file_location('doemo_restore',Path(__file__).parents[1]/'runpod/restore.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    for name,link in [('env/../../escape',''),('env/bin/python','../../../../etc/passwd')]:
        archive=tmp_path/'bad.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:
            m=tarfile.TarInfo(name)
            if link:m.type=tarfile.SYMTYPE;m.linkname=link
            else:m.size=1
            tar.addfile(m,io.BytesIO(b'x') if not link else None)
        with pytest.raises(ValueError):mod.inspect(archive,'env')


def test_restore_dry_run_does_not_touch_existing_component(tmp_path):
    spec=importlib.util.spec_from_file_location('doemo_restore',Path(__file__).parents[1]/'runpod/restore.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    existing=tmp_path/'existing';existing.mkdir();(existing/'keep').write_text('original')
    assert mod.restore({'archive':'missing.tar.gz','component':'env','target':str(existing)},tmp_path,apply=True)['status']=='present_unchanged'
    assert (existing/'keep').read_text()=='original'


def test_parallel_contours_become_one_axis_without_spanning_door_gap():
    from doemo_reconstruction.wall_module import consolidate_parallel_evidence
    candidates=[wall(a,b,1,method='scan') for a,b in [([5,10],[35,10]),([5,14],[35,14]),([50,10],[90,10]),([50,14],[90,14])]]
    result=consolidate_parallel_evidence(candidates)
    assert len(result['walls'])==2 and not result['unresolved']
    for w in result['walls']:
        assert w['a'][1]==w['b'][1]==12
        assert not min(w['a'][0],w['b'][0])<42<max(w['a'][0],w['b'][0])
    candidates[0]['status']='approved'
    with pytest.raises(ValueError):consolidate_parallel_evidence(candidates)


def test_ai_evidence_never_overwrites_corrected_walls_or_calibrates(tmp_path):
    from doemo_reconstruction.ai_service.evidence import attach_evidence
    d=document();d['source']['sha256']='a'*64;w=d['levels'][0]['walls'][0];w['status']='approved'
    evidence={'schema':'doemo.ai.evidence/1','source_sha256':'a'*64,'page':1,'job_id':'job',
              'image_sha256':'b'*64,'width':400,'height':200,'coordinate_space':'input_image_pixels',
              'model_versions':{'paddleocr':'test'},'engines':{'paddleocr':{'texts':[{
              'polygon':[[10,10],[30,10],[30,20],[10,20]],'text':'1200','confidence':.9}]}}}
    request={'image_sha256':'b'*64,'width':400,'height':200,'regions':[]}
    result=attach_evidence(d,'L',evidence,request)
    assert result['levels'][0]['walls']==d['levels'][0]['walls']
    assert result['levels'][0]['scale'] is None
    assert result['levels'][0]['ai_evidence']['job']['texts'][0]['bbox']==[5,5,15,10]
    assert attach_evidence(result,'L',evidence,request)==result


def test_incomplete_persistent_save_blocks_worker_after_restart(tmp_path):
    (tmp_path/'unfinished-job').mkdir();(tmp_path/'unfinished-job'/'partial.json').write_text('{}')
    worker=Worker(None,tmp_path);worker.ready=True
    assert worker.health()['unsaved']==1
    with pytest.raises(RuntimeError):worker.infer('aa862ad6-5f6b-47df-b82b-b3d9b203ebee',request())


def test_private_api_rejects_oversized_streamed_body_before_json(tmp_path):
    private,public=keys();orch=Orchestrator(JobStore(tmp_path/'jobs.sqlite'),None,None)
    client=TestClient(create_app(orch,public,start_worker=False))
    headers={'Authorization':'Bearer '+issue(private,'doemo-orchestrator','jobs'),'Content-Type':'application/json','Idempotency-Key':'big'}
    assert client.post('/jobs/analyze-floorplan',headers=headers,content=b'x'*(13*1024**2+1)).status_code==413
