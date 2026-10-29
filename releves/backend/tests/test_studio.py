import io
import json
import time
import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from doemo_releves.api import create_app
from doemo_releves.auth import standalone,password_hash
from doemo_releves.store import Store
from doemo_releves.coordinates import frames,apply,inverse
from doemo_releves.ai_contracts import normalise
from doemo_releves.queue import process_one,claim


def client(tmp_path):
    return TestClient(create_app(tmp_path/'private'),headers={'X-Doemo-User':'designer','X-Doemo-Role':'dessinateur'})


def project_with_page(c):
    p=c.post('/projects',json={'name':'Animalis test','reference':'test','client':'client'}).json()
    b=io.BytesIO();Image.new('RGB',(600,400),'white').save(b,'PNG')
    r=c.post(f"/projects/{p['id']}/documents",data={'role':'survey'},files={'file':('plan.png',b.getvalue())})
    assert r.status_code==200,r.text
    return r.json()


def annotation(did):
    return {'id':'pcf1','source_document_id':did,'source_page':1,'bbox':{'x':.1,'y':.2,'w':.02,'h':.03},'text':'PCF','equipment_type':'PCF','anchor':{'x':.15,'y':.25},'review':{'equipment':True,'position':True},'training_accepted':False}


def test_authentication_origin_spoof_logout_and_throttle(tmp_path):
    app=standalone(tmp_path/'auth',origin='http://localhost:8082')
    with app.state.store.connect() as db:
        db.execute('INSERT INTO users(login,password_hash,role) VALUES(?,?,?)',('designer',password_hash('a-long-test-password'),'dessinateur'))
    c=TestClient(app,base_url='http://localhost:8082')
    assert c.get('/api/projects',headers={'X-Doemo-User':'admin','X-Doemo-Role':'admin'}).status_code==401
    assert c.post('/session',json={'login':'designer','password':'a-long-test-password'}).status_code==403
    headers={'Origin':'http://localhost:8082'}
    r=c.post('/session',headers=headers,json={'login':'designer','password':'a-long-test-password'})
    assert r.status_code==200 and 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']
    assert c.get('/session').json()['role']=='dessinateur'
    assert c.put('/api/projects/catalogue/PCF',headers={**headers,'X-Doemo-Role':'admin'},json={'code':'PCF','name':'spoof'}).status_code==403
    assert c.post('/api/projects',headers={'Origin':'https://evil.example'},json={'name':'bad'}).status_code==403
    assert c.post('/session/logout',headers=headers).status_code==200
    assert c.get('/api/projects').status_code==401
    for _ in range(8):assert c.post('/session',headers=headers,json={'login':'designer','password':'bad'}).status_code==401
    assert c.post('/session',headers=headers,json={'login':'designer','password':'bad'}).status_code==429
    assert c.get('/session',headers={'Host':'evil.example'}).status_code==400


def test_source_only_floors_export_revision_and_ownership(tmp_path):
    c=client(tmp_path);p=project_with_page(c);ident=p['id'];did=p['documents'][0]['id'];s=p['state']
    s['floors']=[{'id':'r1','name':'R-1','target_page':1,'artboard_index':0,'source_document_id':did,'source_page':1,'source_region':{'x':.05,'y':.05,'w':.4,'h':.45},'rotation_deg':90}]
    s['annotations']=[dict(annotation(did),floor_id='r1')]
    r=c.put(f'/projects/{ident}/state',json=s);assert r.status_code==200,r.text
    assert r.json()['state']['annotations'][0]['anchor'] != r.json()['state']['annotations'][0]['bbox']
    export=c.get(f'/projects/{ident}/structured-export').json()
    assert export['native_ai_created'] is False and len(export['transformations'])==2
    assert c.get(f'/projects/{ident}/history').json()[0]['revision']==1
    assert c.get(f'/projects/{ident}/history/0').json()['annotations']==[]
    assert c.get(f'/projects/{ident}/history',headers={'X-Doemo-User':'other'}).status_code==404
    assert c.put(f'/projects/{ident}/state',json=s).status_code==409
    Store(c.app.state.store.root)  # idempotent migration; state preserved
    assert c.get(f'/projects/{ident}').json()['state']['revision']==1


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_coordinate_round_trip_resolution_crop_rotation_pdf(rotation):
    page={'width':2381,'height':1683,'pdf_size_pt':[1190.4,841.44]}
    f=frames(page,{'x':.12,'y':.08,'w':.32,'h':.47},rotation)
    original=[[.2,.3],[.13,.09],[.4,.5]]
    for _ in range(100):
        original=apply(f['view_to_page'],apply(f['page_to_view'],original))
    assert np.max(np.abs(np.array(original)-[[.2,.3],[.13,.09],[.4,.5]]))<1e-12
    pixels=apply(f['page_normalized_to_raster'],original)
    assert abs(pixels[0][0]-.2*2381)<1e-9
    for key in ['page_normalized_to_pdf','page_normalized_to_illustrator_top_left']:
        assert np.allclose(apply(inverse(f[key]),apply(f[key],original)),original,atol=1e-12)


def test_imports_paddle_res_qwen_no_coordinates_rtmdet_no_equipment():
    raw={'res':{'rec_texts':['PCF'],'rec_scores':[.8],'rec_polys':[[[100,200],[130,200],[130,220],[100,220]]]}}
    a=normalise('paddleocr',raw,'d',1,1000,500)['annotations'][0]
    assert a['bbox']=={'x':.1,'y':.4,'w':pytest.approx(.03),'h':pytest.approx(.04)}
    assert a['anchor'] is None and a['status']=='review' and not any(a['review'].values())
    q=normalise('qwen',{'zones':[{'zone':'left','elements':[{'texte':'PE'},{'texte':'PE'}]}]},'d',1,1000,500)
    assert not q['annotations'] and len(q['observations'])==1
    r=normalise('rtmdet',{'labels':[9],'scores':[.9],'bboxes':[[1,1,3,3]]},'d',1,1000,500)
    assert r['annotations']==[] and r['observations'][0]['equipment_created']==0
    assert r['proposals'][0]['source_class']==9
    assert r['proposals'][0]['category'] is None and r['proposals'][0]['anchor'] is None
    assert r['proposals'][0]['bbox']=={'x':.001,'y':.002,'w':.002,'h':.004}
    outside=normalise('rtmdet',{'labels':[9],'scores':[.9],'bboxes':[[1,1,3000,3]]},'d',1,1000,500)
    assert outside['proposals']==[]
    with pytest.raises(ValueError):normalise('rtmdet',{'labels':['FIRE'],'scores':[.9],'bboxes':[[1,1,3,3]]},'d',1,1000,500)
    with pytest.raises(ValueError):normalise('paddleocr',raw,'d',1,0,500)
    with pytest.raises(ValueError):normalise('paddleocr',{'rec_texts':['x'],'rec_scores':[]},'d',1,1000,500)


def test_analysis_idempotence_preserves_human_corrections(tmp_path):
    c=client(tmp_path);p=project_with_page(c);ident=p['id'];did=p['documents'][0]['id']
    data={'engine':'paddleocr','document_id':did,'page':1,'width':600,'height':400,'revision':0,
          'data':{'rec_texts':['PCF'],'rec_scores':[.5],'rec_polys':[[[10,10],[20,10],[20,20],[10,20]]]}}
    r=c.post(f'/projects/{ident}/analysis-imports',json=data);assert r.status_code==200,r.text
    job=r.json()['id'];assert c.post(f'/projects/{ident}/analysis-imports',json=data).json()['id']==job
    p=c.post(f'/projects/{ident}/jobs/{job}/apply',json={'revision':0}).json()
    assert len(p['state']['annotations'])==1
    p['state']['annotations'][0]['text']='corrigé'
    p=c.put(f'/projects/{ident}/state',json=p['state']).json()
    p=c.post(f'/projects/{ident}/jobs/{job}/apply',json={'revision':p['state']['revision']}).json()
    assert len(p['state']['annotations'])==1 and p['state']['annotations'][0]['text']=='corrigé'
    assert c.get(f'/projects/{ident}/jobs',headers={'X-Doemo-User':'other'}).status_code==404


def test_queue_gpu_off_and_crash_recovery(tmp_path,monkeypatch):
    monkeypatch.delenv('DOEMO_RUNPOD_ENDPOINT',raising=False);monkeypatch.delenv('DOEMO_RUNPOD_TOKEN',raising=False)
    c=client(tmp_path);p=project_with_page(c);ident=p['id'];did=p['documents'][0]['id']
    assert c.get('/projects/ai-status').json()['status']=='not_configured'
    job=c.post(f'/projects/{ident}/jobs',json={'engine':'qwen','document_id':did,'page':1}).json()['id']
    assert process_one(c.app.state.store)
    assert c.get(f'/projects/{ident}/jobs').json()[0]['status']=='waiting_gpu'
    assert c.post(f'/projects/{ident}/jobs/{job}/retry').status_code==200
    assert claim(c.app.state.store)['id']==job
    with c.app.state.store.connect() as db:db.execute('UPDATE jobs SET lease_until=?',(time.time()-10,))
    assert claim(c.app.state.store) is None
    assert c.get(f'/projects/{ident}/jobs').json()[0]['status']=='interrupted'


def test_server_invalidates_review_and_gates_training(tmp_path):
    c=client(tmp_path);p=project_with_page(c);ident=p['id'];s=p['state'];s['annotations']=[annotation(p['documents'][0]['id'])]
    p=c.put(f'/projects/{ident}/state',json=s).json();s=p['state'];s['annotations'][0]['text']='H2O';s['annotations'][0]['training_accepted']=True
    p=c.put(f'/projects/{ident}/state',json=s).json()
    assert not p['state']['annotations'][0]['review']['equipment'] and not p['state']['annotations'][0]['training_accepted']
    s=p['state'];s['workflow']='validated';assert c.put(f'/projects/{ident}/state',json=s).status_code==403
    assert c.get(f'/projects/{ident}/dataset').status_code==403
    assert c.get(f'/projects/{ident}/dataset',headers={'X-Doemo-Role':'admin'}).status_code==422


def test_remote_job_contract_and_failure_do_not_modify_project(tmp_path,monkeypatch):
    from doemo_releves import queue
    c=client(tmp_path);p=project_with_page(c);ident=p['id'];did=p['documents'][0]['id']
    monkeypatch.setenv('DOEMO_RUNPOD_TOKEN','fake-test-token')
    monkeypatch.setenv('DOEMO_RUNPOD_ENDPOINT','https://configured.example')
    monkeypatch.setattr(queue,'remote_health',lambda:{'status':'available'})
    class Response:
        content=b'{}'
        def raise_for_status(self):pass
        def json(self):return {'width':600,'height':400,'data':{'rec_texts':[],'rec_scores':[],'rec_polys':[]}}
    monkeypatch.setattr(queue.httpx,'post',lambda *a,**kw:Response())
    c.post(f'/projects/{ident}/jobs',json={'engine':'paddleocr','document_id':did,'page':1})
    assert process_one(c.app.state.store)
    assert c.get(f'/projects/{ident}/jobs').json()[0]['status']=='completed'
    assert c.get(f'/projects/{ident}').json()['state']['annotations']==[]
    class BadResponse(Response):
        def json(self):return {'width':2048,'height':1447,'data':{}}
    monkeypatch.setattr(queue.httpx,'post',lambda *a,**kw:BadResponse())
    j=c.post(f'/projects/{ident}/jobs',json={'engine':'paddleocr','document_id':did,'page':1}).json()['id']
    assert process_one(c.app.state.store)
    assert next(r for r in c.get(f'/projects/{ident}/jobs').json() if r['id']==j)['status']=='failed'
    assert c.get(f'/projects/{ident}').json()['state']['annotations']==[]


def test_training_export_only_explicit_accepted_examples(tmp_path):
    c=client(tmp_path);p=project_with_page(c);ident=p['id'];s=p['state'];a=annotation(p['documents'][0]['id']);a['training_accepted']=True;s['annotations']=[a]
    assert c.put(f'/projects/{ident}/state',json=s).status_code==200
    assert c.put(f'/projects/{ident}/metadata',json={'training_authorized':True}).status_code==403
    assert c.put(f'/projects/{ident}/metadata',headers={'X-Doemo-Role':'admin'},json={'training_authorized':True,'reference':'building-A'}).status_code==200
    export=c.get(f'/projects/{ident}/dataset',headers={'X-Doemo-Role':'admin'}).json()
    assert len(export['annotations'])==1 and export['images'][0]['split_group']=='building-A'
    assert export['annotations'][0]['bbox']==pytest.approx([60,80,12,12])
    assert export['annotations'][0]['equipment_point']==pytest.approx([90,100])
    assert export['info']['training_started'] is False


@pytest.mark.parametrize('rotation,top_left',[(0,[10,220]),(90,[10,20]),(180,[110,20]),(270,[110,220])])
def test_pdf_intrinsic_rotation_and_crop_box(rotation,top_left):
    f=frames({'width':1000,'height':2000,'pdf_size_pt':[100,200],
              'pdf_source_frame':{'rotation_deg':rotation,'crop_box_pt':[10,20,110,220]}})
    assert apply(f['page_normalized_to_pdf'],[[0,0]])[0]==top_left
    assert np.allclose(apply(inverse(f['page_normalized_to_pdf']),apply(f['page_normalized_to_pdf'],[[.3,.7]])),[[.3,.7]])


def test_exif_rotated_image_original_frame(tmp_path):
    from doemo_releves.documents import prepare_document
    im=Image.new('RGB',(120,80),'white');exif=Image.Exif();exif[274]=6
    source=tmp_path/'rotated.jpg';im.save(source,exif=exif)
    directory=tmp_path/'render';directory.mkdir()
    page=prepare_document(source,directory,'rotated.jpg','survey')['pages'][0]
    assert (page['width'],page['height'])==(80,120)
    assert page['original_image_size_px']==[120,80]
    f=frames(page)['page_normalized_to_original_raster']
    assert apply(f,[[0,0],[1,1]])==[[0,80],[120,0]]
    assert np.allclose(apply(inverse(f),apply(f,[[.27,.65]])),[[.27,.65]])


def test_gpu_gateway_requires_token_and_does_not_claim_inference(tmp_path,monkeypatch):
    import importlib.util
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/'services/runpod'))
    spec=importlib.util.spec_from_file_location('test_runpod_gateway',Path(__file__).parents[2]/'services/runpod/gateway.py')
    gateway=importlib.util.module_from_spec(spec);spec.loader.exec_module(gateway)
    monkeypatch.setenv('DOEMO_RUNPOD_TOKEN','t'*40)
    c=TestClient(gateway.app)
    assert c.get('/health').status_code==401
    r=c.get('/health',headers={'Authorization':'Bearer '+'t'*40})
    assert r.status_code==200 and r.json()['model_inference_verified'] is False
    assert r.json()['automatic_start'] is False
    assert c.post('/infer/unknown',headers={'Authorization':'Bearer '+'t'*40},files={'file':('x.png',b'invalid')}).status_code==404


def test_migration_concurrent_startup(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:Store(tmp_path/'shared').create('test','Project'),range(4)))
    assert len(set(results))==4
    with Store(tmp_path/'shared').connect() as c:
        assert c.execute('SELECT count(*) FROM schema_migrations').fetchone()[0]==6
        assert c.execute('SELECT count(*) FROM projects').fetchone()[0]==4
