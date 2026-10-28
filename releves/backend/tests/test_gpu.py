import asyncio
import hashlib
import importlib.util
import io
import json
import os
import platform
import tarfile
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from doemo_releves import gpu
from doemo_releves.runpod import RunPod,ProviderError
from doemo_releves.store import Store
from doemo_releves.api import create_app
from doemo_releves.queue import claim,process_one


@pytest.fixture
def managed(tmp_path,monkeypatch):
    monkeypatch.setenv('DOEMO_RUNPOD_MANAGED','1');monkeypatch.setenv('RUNPOD_API_KEY','backend-only-test-secret')
    monkeypatch.setenv('DOEMO_RUNPOD_POD_ID','41m7oy6qjaj2ji');monkeypatch.setenv('DOEMO_RUNPOD_TOKEN','g'*40)
    monkeypatch.delenv('DOEMO_RUNPOD_ENDPOINT',raising=False)
    monkeypatch.setenv('DOEMO_RUNPOD_AUTOSTART','1');monkeypatch.setenv('DOEMO_RUNPOD_AUTOSTOP','1')
    return Store(tmp_path/'data')


class Provider:
    def __init__(self,status='EXITED'):self.status=status;self.actions=[];self.fail=None
    def get(self,pod_id):
        return {'id':pod_id,'name':'DOEMO-STUDIO-IA','status':self.status,'actions':['start'] if self.status in ('EXITED','ERROR') else ['stop'],'mounts':{'persistent':{'path':'/workspace'}}}
    def action(self,pod_id,action):
        self.actions.append(action)
        if self.fail:raise self.fail
        return {'id':pod_id,'status':self.status}


class Gateway:
    def __init__(self):self.calls=[];self.ready=True;self.busy=False;self.idle=1801;self.quiet=True;self.error=False
    def health(self):
        if self.error:raise httpx.ConnectError('secret URL must not be logged')
        return {'ready':self.ready,'engines':{e:self.ready for e in gpu.ENGINES},'boot_id':'boot-A','busy':self.busy,'active_jobs':int(self.busy),'idle_seconds':self.idle,'restoring':False}
    def quiesce(self):self.calls.append('quiesce');return {'quiesced':self.quiet,'boot_id':'boot-A'}
    def resume(self):self.calls.append('resume');return {'accepting':True}


def job(store,status='queued',engine='qwen'):
    ident=store.create('designer','test')
    with store.connect() as c:c.execute('INSERT INTO jobs(id,project_id,actor,status,stage,payload) VALUES(?,?,?,?,?,?)',(ident,ident,'designer',status,'test',json.dumps({'engine':engine})))
    return ident


def controller(store,provider=None,gateway=None,now=10000):
    p=provider or Provider();g=gateway or Gateway();clock=[now]
    return gpu.Controller(store,p,lambda url:g,lambda:clock[0]),p,g,clock


def ready_state(store,now=10000,last=8000):gpu.update(store,pod_id=os.environ['DOEMO_RUNPOD_POD_ID'],phase='ready',boot_id='boot-A',last_activity=last,observed_at=now)


def test_v2_contract_and_key_never_returned():
    calls=[]
    def handle(r):
        calls.append(r)
        assert r.headers['authorization']=='Bearer backend-key'
        return httpx.Response(200,json={'id':'pod-id','name':'DOEMO-STUDIO-IA','status':'EXITED','env':{'secret':'DO NOT RETURN'},'actions':['start','terminate']})
    p=RunPod('backend-key',httpx.Client(transport=httpx.MockTransport(handle)))
    assert 'env' not in p.get('pod-id')
    p.action('pod-id','start');p.action('pod-id','stop')
    assert [str(r.url) for r in calls]==['https://api.runpod.io/v2/pods/pod-id','https://api.runpod.io/v2/pods/pod-id/action','https://api.runpod.io/v2/pods/pod-id/action']
    assert json.loads(calls[1].content)=={'action':'start'}
    assert json.loads(calls[2].content)=={'action':'stop'}
    for action in ('terminate','restart','reset','delete'):
        with pytest.raises(ValueError):p.action('pod-id',action)
    with pytest.raises(ValueError):p.get('../other')
    assert len(calls)==3


def test_rate_limit_does_not_log_provider_body():
    p=RunPod('backend-key',httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(429,headers={'Retry-After':'120'},json={'detail':'secret password'}))))
    with pytest.raises(ProviderError) as e:p.get('pod-id')
    assert e.value.retry_after==120 and 'secret' not in str(e.value)


def test_job_starts_pod_once_waits_all_three_models_and_survives_controller_restart(managed):
    job(managed);c,p,g,clock=controller(managed)
    c.tick();assert p.actions==['start']
    clock[0]+=16;c.tick();assert p.actions==['start']
    # New reconciler sees the durable outstanding action, not a fresh command.
    c=gpu.Controller(managed,p,lambda url:g,lambda:clock[0]);clock[0]+=16;c.tick();assert p.actions==['start']
    p.status='RUNNING';g.ready=False;clock[0]+=16;c.tick();assert gpu.state(managed)['phase']=='warming'
    g.ready=True;clock[0]+=16;c.tick();assert gpu.state(managed)['phase']=='busy'
    assert p.actions==['start'] and gpu.state(managed)['pending_action'] is None


def test_two_controllers_do_not_send_duplicate_start(managed):
    job(managed);c,p,g,clock=controller(managed)
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda _:c.tick(),range(4)))
    assert p.actions==['start']


def test_stop_holds_admission_lock_until_provider_action_returns(managed):
    ready_state(managed)
    c,p,g,_=controller(managed,Provider('RUNNING'))
    action_started=threading.Event();release=threading.Event();admitted=threading.Event();attempting=threading.Event()
    def action(ident,operation):
        p.actions.append(operation);action_started.set();assert release.wait(3)
    p.action=action
    def enqueue():
        attempting.set()
        with gpu.lifecycle_lock(managed):
            job(managed);admitted.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        stopped=pool.submit(c.tick);assert action_started.wait(3)
        added=pool.submit(enqueue);assert attempting.wait(3)
        try:assert not admitted.wait(.05)
        finally:release.set()
        stopped.result();added.result()
    assert p.actions==['stop'] and g.calls==['quiesce'] and gpu.pending(managed)==1
    assert claim(managed) is None


def test_unknown_start_outcome_reconciled_before_retry(managed):
    job(managed);c,p,g,clock=controller(managed);p.fail=ProviderError('network')
    c.tick();assert gpu.state(managed)['pending_action']=='start'
    clock[0]+=61;c.tick();assert p.actions==['start']
    p.status='RUNNING';g.ready=True;clock[0]+=16;c.tick();assert p.actions==['start']
    events=gpu.public_status(managed);assert 'backend-only-test-secret' not in json.dumps(events)


def test_exact_idle_threshold_and_no_health_poll_activity(managed):
    c,p,g,clock=controller(managed,Provider('RUNNING'));ready_state(managed,last=8201)
    c.tick();assert not p.actions
    first=gpu.state(managed)['last_activity'];gpu.public_status(managed);assert gpu.state(managed)['last_activity']==first
    clock[0]+=16;c.tick();assert p.actions==['stop'] and g.calls==['quiesce']
    p.status='EXITED';clock[0]+=16;c.tick();assert gpu.state(managed)['phase']=='stopped'


@pytest.mark.parametrize('status',['queued','running','waiting_gpu','retry_gpu','interrupted'])
def test_no_manual_or_idle_stop_with_any_pending_task(managed,status):
    job(managed,status,engine='local');ready_state(managed)
    c,p,g,_=controller(managed,Provider('RUNNING'));c.tick();assert p.actions==[]
    with pytest.raises(ValueError):gpu.request_action(managed,'stop','admin')
    assert g.calls==[]


def test_idle_requires_fresh_remote_health_real_idle_and_quiescence(managed):
    ready_state(managed);c,p,g,clock=controller(managed,Provider('RUNNING'))
    g.idle=10;c.tick();assert not p.actions
    clock[0]+=16;g.idle=2000;g.error=True;c.tick();assert not p.actions
    clock[0]+=31;g.error=False;g.quiet=False;c.tick();assert not p.actions
    clock[0]+=16;g.quiet=True;g.busy=True;c.tick();assert not p.actions


def test_admin_requests_and_manual_stop_without_thirty_minute_wait(managed):
    ready_state(managed,last=9999);c,p,g,clock=controller(managed,Provider('RUNNING'));g.idle=1
    gpu.request_action(managed,'stop','admin');c.tick();assert p.actions==['stop']
    with managed.connect() as db:rows=[dict(r) for r in db.execute('SELECT * FROM gpu_events')]
    assert any(r['actor']=='admin' and r['action']=='stop' for r in rows)
    p.status='EXITED';clock[0]+=16;c.tick();assert gpu.state(managed)['request'] is None
    gpu.request_action(managed,'start','admin');c.tick();assert p.actions==['stop','start']


def test_wrong_pod_name_cannot_be_controlled(managed):
    job(managed);c,p,g,_=controller(managed);p.get=lambda ident:{'id':ident,'name':'OTHER','status':'EXITED'}
    c.tick();assert not p.actions and gpu.state(managed)['phase']=='configuration_error'


def test_changed_pod_never_reuses_old_readiness_or_stop_intent(managed):
    gpu.update(managed,pod_id='previous-pod',phase='ready',boot_id='boot-A',observed_at=time.time(),
               engines=json.dumps({e:True for e in gpu.ENGINES}),request='stop',pending_action='stop',
               next_poll=99999999999,action_at=9900,last_activity=1)
    status=gpu.public_status(managed)
    assert status['pod_id']=='41m7oy6qjaj2ji' and status['engines']=={} and status['stale']
    ident=job(managed)
    assert claim(managed) is None
    c,p,g,_=controller(managed,Provider('RUNNING'));g.ready=False
    c.tick()
    assert not p.actions and gpu.state(managed)['request'] is None
    assert gpu.state(managed)['pending_action'] is None and gpu.state(managed)['phase']=='warming'
    with managed.connect() as db:
        assert db.execute('SELECT status FROM jobs WHERE id=?',(ident,)).fetchone()[0]=='waiting_gpu'


def test_transient_inference_retries_are_bounded(managed,monkeypatch):
    ident=job(managed)
    image=managed.root/'documents'/'source'/'page-1.png';image.parent.mkdir(parents=True)
    Image.new('RGB',(16,16)).save(image)
    with managed.connect() as db:
        db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps({'engine':'qwen','document_id':'source','page':1}),ident))
    def fail(*args,**kwargs):raise httpx.ConnectError('private URL')
    monkeypatch.setattr(httpx,'post',fail)
    for attempt in range(5):
        ready_state(managed,now=time.time());gpu.update(managed,gateway_url='https://test.example')
        with managed.connect() as db:db.execute('UPDATE jobs SET retry_at=0 WHERE id=?',(ident,))
        assert process_one(managed)
        with managed.connect() as db:row=dict(db.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone())
        assert row['attempts']==attempt+1
        assert row['status']==('failed' if attempt==4 else 'retry_gpu')
        assert 'private URL' not in row['error']
    assert gpu.pending(managed)==0


def test_private_configuration_separates_provider_key_and_gateway_token(tmp_path):
    path=Path(__file__).parents[2]/'scripts/configure-runpod.py'
    spec=importlib.util.spec_from_file_location('configure_runpod',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    paths=module.write_configuration(tmp_path/'private','41m7oy6qjaj2ji','provider-secret','g'*40)
    assert 'provider-secret' in paths[0].read_text()
    assert 'provider-secret' not in paths[1].read_text() and 'RUNPOD_API_KEY' not in paths[1].read_text()
    assert all(p.stat().st_mode & 0o777==0o600 for p in paths)
    with pytest.raises(ValueError):module.write_configuration(tmp_path/'private','new-id','replacement','g'*40)
    assert 'provider-secret' in paths[0].read_text()


def test_api_roles_cached_dashboard_and_destructive_actions_forbidden(managed):
    app=create_app(managed.root);c=TestClient(app,headers={'X-Doemo-User':'u','X-Doemo-Role':'dessinateur'})
    assert c.get('/projects/gpu').status_code==200
    assert c.post('/projects/gpu/action',json={'action':'start'}).status_code==403
    assert c.get('/projects/gpu/events').status_code==403
    assert c.post('/projects/gpu/action',headers={'X-Doemo-Role':'admin'},json={'action':'terminate'}).status_code==422
    assert c.post('/projects/gpu/action',headers={'X-Doemo-Role':'admin'},json={'action':'start'}).status_code==200
    assert 'backend-only-test-secret' not in c.get('/projects/gpu').text


def test_worker_does_not_claim_gpu_job_before_readiness_and_cpu_still_claims(managed):
    gpu_job=job(managed);assert claim(managed) is None
    with managed.connect() as c:assert c.execute('SELECT status FROM jobs WHERE id=?',(gpu_job,)).fetchone()[0]=='waiting_gpu'
    cpu_job=job(managed,engine='local');assert claim(managed)['id']==cpu_job
    gpu.update(managed,pod_id=os.environ['DOEMO_RUNPOD_POD_ID'],phase='ready',observed_at=time.time(),gateway_url='https://test.example')
    assert claim(managed)['id']==gpu_job


def load_module(name):
    path=Path(__file__).parents[2]/'services/runpod'/f'{name}.py'
    spec=importlib.util.spec_from_file_location('gpu_test_'+name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_persistent_results_retry_and_quiescence(tmp_path,monkeypatch):
    gateway=load_module('gateway');monkeypatch.setenv('DOEMO_RUNPOD_TOKEN','g'*40);monkeypatch.setenv('DOEMO_PERSISTENT_ROOT',str(tmp_path/'volume'))
    gateway.status.update(ready=True,restoring=False,engines={e:True for e in gateway.ENGINES})
    count=[]
    async def execute(python,script,args,log,timeout):
        count.append(1);Path(args[-1]).write_text(json.dumps({'rec_texts':[],'rec_scores':[],'rec_polys':[]}));return 0
    monkeypatch.setattr(gateway,'execute',execute)
    c=TestClient(gateway.app,headers={'Authorization':'Bearer '+'g'*40,'X-Doemo-Job':'a'*32})
    b=io.BytesIO();Image.new('RGB',(16,16),'white').save(b,'PNG');data=b.getvalue()
    r=c.post('/infer/paddleocr',files={'file':('x.png',data)});assert r.status_code==200,r.text
    assert (tmp_path/'volume/jobs'/('a'*32)/'input.png').read_bytes()==data
    assert c.post('/infer/paddleocr',files={'file':('x.png',data)}).json()==r.json() and len(count)==1
    assert c.post('/quiesce').json()['quiesced'] is True
    assert c.post('/infer/qwen',files={'file':('x.png',data)}).status_code==409
    assert c.post('/resume').status_code==200
    assert c.get('/jobs/'+('a'*32)).json()['status']=='completed'
    assert 'RUNPOD_API_KEY' not in gateway.engine_env()


def test_gateway_refuses_quiescence_during_real_inference_handler(tmp_path,monkeypatch):
    gateway=load_module('gateway');monkeypatch.setenv('DOEMO_RUNPOD_TOKEN','g'*40)
    monkeypatch.setenv('DOEMO_PERSISTENT_ROOT',str(tmp_path/'volume'))
    gateway.status.update(ready=True,restoring=False,engines={e:True for e in gateway.ENGINES})
    async def scenario():
        started=asyncio.Event();release=asyncio.Event()
        async def execute(python,script,args,log,timeout):
            started.set();await release.wait();Path(args[-1]).write_text('{}');return 0
        monkeypatch.setattr(gateway,'execute',execute)
        image=io.BytesIO();Image.new('RGB',(16,16)).save(image,'PNG')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway.app),base_url='http://test',headers={'Authorization':'Bearer '+'g'*40}) as client:
            task=asyncio.create_task(client.post('/infer/qwen',files={'file':('x.png',image.getvalue())}))
            await asyncio.wait_for(started.wait(),2)
            try:
                assert (await client.get('/health')).json()['busy'] is True
                assert (await client.post('/quiesce')).json()['quiesced'] is False
            finally:release.set()
            assert (await task).status_code==200
            assert (await client.post('/quiesce')).json()['quiesced'] is True
    asyncio.run(scenario())


def make_manifest(tmp_path,bad=False):
    root=tmp_path/'snapshots';root.mkdir();archive=root/'env.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        info=tarfile.TarInfo('../escape' if bad else 'doemo-test-venv/bin/python');body=b'preserved interpreter';info.size=len(body);info.mode=0o755;tar.addfile(info,io.BytesIO(body))
    manifest={'version':1,'machine':platform.machine(),'environments':{'test':{'root':'doemo-test-venv','roots':['doemo-test-venv'],'archive':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}}}
    path=root/'manifest.json';path.write_text(json.dumps(manifest));return path


def test_restore_absent_environment_and_preserve_existing(tmp_path):
    module=load_module('environments');manifest=make_manifest(tmp_path);opt=tmp_path/'opt';opt.mkdir()
    assert module.restore(manifest,opt)=={'test':'restored'}
    python=opt/'doemo-test-venv/bin/python';assert python.read_bytes()==b'preserved interpreter'
    python.write_bytes(b'locally validated environment')
    assert module.restore(manifest,opt)=={'test':'preserved'} and python.read_bytes()==b'locally validated environment'


def test_restore_refuses_corruption_and_path_escape(tmp_path):
    module=load_module('environments');manifest=make_manifest(tmp_path,bad=True);opt=tmp_path/'opt';opt.mkdir()
    with pytest.raises(ValueError):module.restore(manifest,opt)
    assert not (tmp_path/'escape').exists()
    (manifest.parent/'env.tar.gz').write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='Empreinte'):module.restore(manifest,opt)
