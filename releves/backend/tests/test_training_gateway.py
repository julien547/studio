"""Persistent gateway protocol tested with CPU fixture subprocesses only."""
import asyncio
import json
import os
import sys
import zipfile
from pathlib import Path
import pytest
from test_training_artifacts import fixture

@pytest.fixture
def service(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/'services/runpod'))
    import training_service
    return training_service

@pytest.fixture
def admitted(tmp_path,service):
    data=tmp_path/'data';fixture(data);snapshot={'engine':'rtmdet'}
    (data/'examples.json').write_text(json.dumps(snapshot))
    archive=tmp_path/'dataset.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for p in data.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(data))
    spec={'id':'a'*32,'engine':'rtmdet','profile_id':'b'*64,'parameters':{'epochs':2,'batch_size':1,'learning_rate':.0001},
          'dataset_id':'c'*32,'dataset_sha256':service.digest(snapshot),'archive_sha256':service.sha256(archive)}
    profile={'public':{'id':spec['profile_id']},'config':'fixture.py','weights':'fixture.pth'}
    store=service.JobStore(tmp_path/'volume');store.admit(spec['id'],spec,archive,profile)
    return store,spec,archive,profile


def test_admission_survives_restart_deduplicates_and_cancel_tombstone_wins(admitted,service):
    store,spec,archive,profile=admitted;ident=spec['id']
    assert service.JobStore(store.root).state(ident)['status']=='queued'
    assert store.admit(ident,spec,archive,profile)['revision']==1
    with pytest.raises(ValueError,match='autre demande'):store.admit(ident,dict(spec,parameters={**spec['parameters'],'epochs':3}),archive,profile)
    manager=service.Manager(store.root,asyncio.Lock(),lambda:True,lambda:False,lambda:None,lambda:{},lambda:profile)
    asyncio.run(manager.control(ident,'cancel'))
    assert store.admit(ident,spec,archive,profile)['status']=='cancelled'
    missing='d'*32;asyncio.run(manager.control(missing,'cancel'))
    assert store.admit(missing,dict(spec,id=missing),archive,profile)['status']=='cancelled'
    assert store.pending()==0


def test_restart_marks_running_interrupted_and_partial_last_write_fails_closed(admitted):
    store,spec,_,_=admitted;ident=spec['id']
    store.append(ident,status='running',checkpoint='last-checkpoint')
    store.recover();assert store.state(ident)['status']=='interrupted' and store.state(ident)['pause_reason']=='restart'
    file=store.directory(ident)/'event-000000000099-bad.json';file.write_text('{')
    assert store.state(ident)['status']=='interrupted' and store.pending()==1
    store.append(ident,status='cancelled');assert store.state(ident)['revision']==100 and store.pending()==0


def test_completed_artifact_is_verified_again_before_returning(admitted,service,tmp_path):
    from artifacts import preserve
    store,spec,_,_=admitted;ident=spec['id'];source=tmp_path/'fixture.pth';source.write_bytes(b'CPU fixture, not GPU-trained weights')
    manifest=preserve({'weights.pth':source},store.root/'training/jobs'/ident/'results',spec)
    store.append(ident,status='completed',result_manifest=str(manifest.relative_to(store.root)))
    assert store.public(ident)['artifacts_verified'] is True
    (manifest.parent/'weights.pth').write_bytes(b'broken')
    with pytest.raises(ValueError):store.public(ident)
    with pytest.raises(ValueError):store.artifact(ident,'../../escape/manifest.json')


def test_resume_requires_checkpoint_after_interruption_and_never_accepts_arbitrary_commands(admitted,service):
    store,spec,archive,profile=admitted;ident=spec['id']
    manager=service.Manager(store.root,asyncio.Lock(),lambda:True,lambda:False,lambda:None,lambda:{},lambda:profile)
    store.append(ident,status='interrupted')
    with pytest.raises(ValueError,match='checkpoint'):asyncio.run(manager.control(ident,'resume'))
    with pytest.raises(ValueError):service.spec_valid(dict(spec,command='rm -rf /'),ident)
    with pytest.raises(ValueError):service.spec_valid(dict(spec,parameters={**spec['parameters'],'batch_size':100}),ident)


def test_preparation_can_be_cancelled_or_paused_before_child_process_exists(admitted,service):
    store,spec,_,profile=admitted;manager=service.Manager(store.root,asyncio.Lock(),lambda:True,lambda:False,lambda:None,lambda:{},lambda:profile)
    manager.active=spec['id'];manager.control_file=None
    assert asyncio.run(manager.control(spec['id'],'pause'))['status']=='paused'
    assert asyncio.run(manager.control(spec['id'],'cancel'))['status']=='cancelled'


def fixture_driver(tmp_path,service,monkeypatch,fail=False):
    path=tmp_path/'fixture-driver.py'
    path.write_text('''import argparse,json,time
from pathlib import Path
import sys
sys.path.insert(0,'''+repr(str(Path(service.__file__).parent))+''')
from artifacts import preserve
p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--managed-job');p.add_argument('--control');args,_=p.parse_known_args()
root=Path(args.output);ident=args.managed_job;spec=json.loads((root/'training/queue'/ident/'request.json').read_text())
print('DOEMO_EVENT='+json.dumps({'event':'progress','iteration':1,'total_iterations':2,'epoch':1,'loss':.3}),flush=True)
files={}
for name in ('weights.pth','model_config.py','classes.json','metrics.json'):
 path=Path(args.control).parent/name;path.write_text('CPU fixture only');files[name]=path
manifest=preserve(files,root/'training/jobs'/ident/'results',dict(spec,status='completed',metrics={'fixture_score':1}))
print('DOEMO_EVENT='+json.dumps({'event':'completed','manifest':str(manifest.relative_to(root))}),flush=True)
'''+('raise SystemExit(1)\n' if fail else ''))
    monkeypatch.setattr(service,'DRIVER',path);monkeypatch.setattr(service,'PYTHON',sys.executable)

@pytest.mark.parametrize('fail',[False,True])
def test_completion_requires_verified_files_and_successful_process_exit(admitted,service,tmp_path,monkeypatch,fail):
    store,spec,_,profile=admitted;fixture_driver(tmp_path,service,monkeypatch,fail)
    async def scenario():
        lock=asyncio.Lock();manager=service.Manager(store.root,lock,lambda:True,lambda:False,lambda:None,lambda:{},lambda:profile)
        await manager.initialize();await manager.run(spec['id'])
        assert manager.proc.returncode==(1 if fail else 0) and not lock.locked()
    asyncio.run(scenario())
    state=store.state(spec['id']);assert state['status']==('failed' if fail else 'completed')
    assert state['progress']==.5 # Comes from the actual fixture event, not a timer.
    if not fail:assert store.public(spec['id'])['artifacts_verified']


def test_gateway_auth_status_and_quiesce_include_training_without_starting_gpu(admitted,service,monkeypatch):
    from fastapi.testclient import TestClient
    import gateway
    store,spec,_,profile=admitted
    manager=service.Manager(store.root,asyncio.Lock(),lambda:True,lambda:False,lambda:None,lambda:{},lambda:profile)
    monkeypatch.setattr(gateway,'training',manager);monkeypatch.setattr(gateway,'draining',False)
    monkeypatch.setenv('DOEMO_RUNPOD_TOKEN','t'*32)
    gateway.status.update(ready=True,restoring=False)
    c=TestClient(gateway.app)
    assert c.get('/training/jobs/'+spec['id']).status_code==401
    c.headers['Authorization']='Bearer '+'t'*32
    assert c.get('/training/jobs/'+spec['id']).json()['status']=='queued'
    assert c.post('/quiesce').json()['quiesced'] is False
    assert c.get('/health').json()['training_pending']==1
    assert c.post('/training/jobs/'+spec['id']+'/cancel').json()['status']=='cancelled'
    assert c.post('/quiesce').json()['quiesced'] is True


def test_shutdown_reaps_child_before_releasing_gpu_and_keeps_interruption(admitted,service,tmp_path,monkeypatch):
    store,spec,_,profile=admitted
    driver=tmp_path/'slow-driver.py'
    driver.write_text('import time\ntime.sleep(120)\n')
    monkeypatch.setattr(service,'DRIVER',driver);monkeypatch.setattr(service,'PYTHON',sys.executable)
    async def scenario():
        lock=asyncio.Lock();manager=service.Manager(store.root,lock,lambda:True,lambda:False,lambda:None,lambda:{},lambda:profile)
        task=asyncio.create_task(manager.run(spec['id']))
        for _ in range(200):
            if manager.proc:break
            await asyncio.sleep(.01)
        assert manager.proc and lock.locked()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert manager.proc.returncode is not None and not lock.locked() and manager.active is None
    asyncio.run(scenario())
    assert store.state(spec['id'])['status']=='interrupted'


def test_checkpoint_binding_and_epoch_are_verified(admitted,service,tmp_path):
    from artifacts import preserve
    store,spec,_,profile=admitted;ident=spec['id'];source=tmp_path/'epoch.pth';source.write_bytes(b'fixture')
    manager=service.Manager(store.root,asyncio.Lock(),lambda:True,lambda:False,lambda:None,lambda:{},lambda:profile)
    manifest=preserve({'epoch_1.pth':source},store.root/'training/jobs'/ident/'checkpoints',dict(spec,epoch=1,resume_file='epoch_1.pth'))
    asyncio.run(manager.receive(ident,{'event':'checkpoint','manifest':str(manifest.relative_to(store.root))}))
    assert store.state(ident)['epoch']==1
    wrong=preserve({'epoch_1.pth':source},store.root/'training/jobs'/ident/'checkpoints',dict(spec,epoch=1,profile_id='f'*64))
    with pytest.raises(ValueError):asyncio.run(manager.receive(ident,{'event':'checkpoint','manifest':str(wrong.relative_to(store.root))}))
    with pytest.raises(ValueError):asyncio.run(manager.receive(ident,{'event':'progress','iteration':1,'total_iterations':2,'loss':float('nan')}))


def test_acceptance_requires_explicit_authorization_before_gpu_checks(service):
    from argparse import Namespace
    from accept_training import acceptance
    with pytest.raises(ValueError,match='Autorisation'):
        asyncio.run(acceptance(Namespace(authorize_gpu_training=False,maintenance_confirmed=False)))
