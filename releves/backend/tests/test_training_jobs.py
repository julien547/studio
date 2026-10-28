"""CPU contract tests. Accepted profiles and remote responses are fixtures,
not evidence that any real GPU training was performed."""
import json
import time
import httpx
import pytest
from test_training import api,source,label,example,validate,dataset,PREFIX
from doemo_releves import gpu,training_jobs as jobs

@pytest.fixture
def accepted(api,monkeypatch,tmp_path):
    value={'engine':'rtmdet','driver_sha256':'a'*64,'runtime_sha256':'e'*64,'config_sha256':'b'*64,'weights_sha256':'c'*64,
           'acceptance':{'training_completed':True,'resume_verified':True,'inference_preemption_verified':True,'cancel_verified':True,'report_sha256':'d'*64}}
    path=tmp_path/'fixture-acceptance.json';path.write_text(json.dumps(value))
    for k,v in {'DOEMO_TRAINING_PROFILE':str(path),'DOEMO_RUNPOD_MANAGED':'1','RUNPOD_API_KEY':'fixture-provider-key','DOEMO_RUNPOD_TOKEN':'t'*32,'DOEMO_RUNPOD_POD_ID':'fixture-pod'}.items():monkeypatch.setenv(k,v)
    store=api.app.state.store
    gpu.update(store,pod_id='fixture-pod',phase='ready',observed_at=time.time(),gateway_url='https://fixture.invalid',engines=json.dumps({e:True for e in gpu.ENGINES}))
    examples=[]
    for color in ('red','green','blue'):
        p=source(api,color);_,e=example(api,'rtmdet',p,[label('FIRE',anchor={'x':.5,'y':.5})]);examples.append(validate(api,p,e))
    d=dataset(api,'rtmdet',examples)
    return store,d


def launch(api,d,key='fixture-request-key-001',**kw):
    response=api.post(PREFIX+'/runs',json=dict(engine='rtmdet',dataset_id=d['id'],epochs=2,batch_size=1,learning_rate=.0001,confirmed=True,request_key=key,**kw))
    assert response.status_code==200,response.text
    return response.json()


def again(store,remote):
    with store.connect() as c:c.execute('UPDATE training_runs SET retry_at=0')
    jobs.tick(store,lambda url:remote)


def read(store,ident):
    with store.connect() as c:return jobs.record(c,ident)


class Remote:
    def __init__(self):self.value=None;self.submissions=[];self.controls=[];self.timeout=False;self.on_submit=None
    def submit(self,job,snapshot,bundle):
        self.submissions.append((job['id'],bundle));self.value={'id':job['id'],'status':'running','revision':1,'progress':.2}
        if self.on_submit:self.on_submit()
        if self.timeout:self.timeout=False;raise httpx.ReadTimeout('fixture')
        return self.value
    def status(self,ident):return self.value
    def control(self,ident,action):
        self.controls.append(action);self.value={'id':ident,'status':{'cancel':'cancelled','pause':'paused','resume':'running'}[action],'revision':(self.value or {}).get('revision',0)+1,'progress':.2,'pause_reason':'inference' if action=='pause' else None};return self.value


def completed(job,d):
    return {'id':job['id'],'status':'completed','revision':20,'progress':1,'artifacts_verified':True,'result':{
        'schema':'doemo.artifacts/1','id':'fixture','files':[{'name':n,'bytes':10,'sha256':'a'*64} for n in ('weights.pth','model_config.py','classes.json','metrics.json')],
        'metadata':{'id':job['id'],'engine':'rtmdet','dataset_sha256':d['sha256'],'profile_id':job['profile']['id'],'parameters':job['parameters'],'status':'completed','metrics':{'coco/bbox_mAP':.5},'production_approved':False}}}


def test_admission_is_explicit_idempotent_and_pending_jobs_block_stop(api,accepted):
    store,d=accepted
    assert api.post(PREFIX+'/runs',json={'engine':'rtmdet','dataset_id':d['id']}).status_code==422
    job=launch(api,d);assert launch(api,d)['id']==job['id']
    changed={**job['parameters'],'epochs':3,'engine':'rtmdet','dataset_id':d['id'],'confirmed':True,'request_key':'fixture-request-key-001'}
    assert api.post(PREFIX+'/runs',json=changed).status_code==409
    assert gpu.pending(store)==1 and gpu.pending(store,True)==1
    with pytest.raises(ValueError,match='en attente'):gpu.request_action(store,'stop','admin')
    assert api.post(PREFIX+'/runs/'+job['id']+'/cancel').json()['status']=='cancelled'
    assert gpu.pending(store)==0
    assert api.post(PREFIX+'/runs/'+job['id']+'/cancel').status_code==409


def test_lost_reply_reconciles_same_job_and_completed_artifacts_become_candidate(api,accepted):
    store,d=accepted;job=launch(api,d);remote=Remote();remote.timeout=True
    again(store,remote);assert read(store,job['id'])['dispatched']==1
    again(store,remote);assert len(remote.submissions)==1 and read(store,job['id'])['status']=='running'
    remote.value=completed(job,d);again(store,remote)
    assert read(store,job['id'])['status']=='completed' and gpu.pending(store)==0
    saved=api.post(PREFIX+'/models/rtmdet/versions',json={'name':'Modèle fixture','dataset_id':d['id'],'run_id':job['id']})
    assert saved.status_code==200,saved.text
    assert saved.json()['status']=='candidate'
    repeated=api.post(PREFIX+'/models/rtmdet/versions',json={'name':'Doublon','dataset_id':d['id'],'run_id':job['id']})
    assert repeated.json()['id']==saved.json()['id']
    assert api.post(PREFIX+'/models/rtmdet/'+saved.json()['id']+'/publish',json={'confirmed':True}).status_code==409
    assert api.get(PREFIX+'/models?engine=rtmdet').json()['deployment']['version_id'] is None


def test_lost_first_upload_reuses_identical_bytes_and_cancel_race_needs_ack(api,accepted):
    store,d=accepted;job=launch(api,d);remote=Remote();remote.timeout=True
    again(store,remote);remote.value=None;again(store,remote)
    assert len(remote.submissions)==2 and remote.submissions[0]==remote.submissions[1]
    jobs.cancel(store,'admin',job['id']);assert read(store,job['id'])['status']=='cancel_requested'
    assert gpu.pending(store)==1
    again(store,remote);assert read(store,job['id'])['status']=='cancelled' and remote.controls==['cancel']


def test_cancellation_during_http_call_cannot_be_overwritten_by_running_reply(api,accepted):
    store,d=accepted;job=launch(api,d);remote=Remote();remote.on_submit=lambda:jobs.cancel(store,'admin',job['id'])
    again(store,remote);assert read(store,job['id'])['status']=='cancel_requested'
    again(store,remote);assert read(store,job['id'])['status']=='cancelled'


def test_inference_priority_pauses_then_resumes_training_without_parallel_dispatch(api,accepted):
    store,d=accepted;job=launch(api,d);remote=Remote();example=d['snapshot']['examples'][0]
    with store.connect() as c:c.execute("INSERT INTO jobs(id,project_id,actor,status,stage,payload) VALUES('inference',?,'admin','queued','fixture',?)",(example['project_id'],json.dumps({'engine':'qwen'})))
    again(store,remote);assert not remote.submissions
    with store.connect() as c:c.execute("UPDATE jobs SET status='completed' WHERE id='inference'")
    again(store,remote)
    with store.connect() as c:c.execute("UPDATE jobs SET status='queued' WHERE id='inference'")
    again(store,remote);assert remote.controls==['pause'] and read(store,job['id'])['status']=='paused'
    with store.connect() as c:c.execute("UPDATE jobs SET status='completed' WHERE id='inference'")
    again(store,remote);assert remote.controls==['pause','resume']


def test_restart_interruption_requires_explicit_resume_and_changed_pod_never_receives_job(api,accepted,monkeypatch):
    store,d=accepted;job=launch(api,d);remote=Remote();again(store,remote)
    remote.value={'id':job['id'],'status':'interrupted','revision':2,'pause_reason':'restart'}
    again(store,remote);again(store,remote);assert not remote.controls
    assert api.post(PREFIX+'/runs/'+job['id']+'/resume',json={'confirmed':False}).status_code==422
    assert api.post(PREFIX+'/runs/'+job['id']+'/resume',json={'confirmed':True}).status_code==200
    again(store,remote);assert remote.controls==['resume']
    monkeypatch.setenv('DOEMO_RUNPOD_POD_ID','different-pod');again(store,remote)
    assert read(store,job['id'])['status']=='interrupted' and len(remote.submissions)==1


def test_revocation_cancels_remote_and_invalid_artifacts_never_register(api,accepted):
    store,d=accepted;job=launch(api,d);remote=Remote();again(store,remote)
    remote.value=completed(job,d);remote.value['result']['metadata']['dataset_sha256']='f'*64
    again(store,remote);assert read(store,job['id'])['status']=='interrupted'
    assert api.post(PREFIX+'/models/rtmdet/versions',json={'name':'Bad','dataset_id':d['id'],'run_id':job['id']}).status_code==422
    pid=d['snapshot']['examples'][0]['project_id'];api.put('/projects/'+pid+'/metadata',json={'training_authorized':False})
    again(store,remote);assert read(store,job['id'])['status']=='cancel_requested'
    again(store,remote);assert read(store,job['id'])['status']=='cancelled'


def test_same_request_remains_idempotent_when_profile_is_disabled(api,accepted,monkeypatch):
    store,d=accepted;job=launch(api,d)
    monkeypatch.delenv('DOEMO_TRAINING_PROFILE')
    assert launch(api,d)['id']==job['id']
    assert gpu.pending(store)==1
    assert api.post(PREFIX+'/runs/'+job['id']+'/cancel').json()['status']=='cancelled'
