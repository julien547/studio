"""CPU fixtures only; no Torch, PEFT, weights or GPU loaded."""
import asyncio
import io
import json
import sys
import tempfile
import zipfile
from argparse import Namespace
from pathlib import Path
import pytest
from PIL import Image
from test_training import api,source,example,validate,dataset,PREFIX
from doemo_releves import training_jobs,gpu

@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/'services/runpod'))
    import qwen_training_data,qwen_training,training_service
    return qwen_training_data,qwen_training,training_service


def profile_value():
    return dict(engine='qwen',**{k:'a'*64 for k in ('driver_sha256','runtime_sha256','config_sha256','weights_sha256')},
                acceptance=dict(training_completed=True,resume_verified=True,inference_preemption_verified=True,cancel_verified=True,report_sha256='b'*64))


def config():
    return dict(schema='doemo.qwen-lora/1',rank=8,alpha=16,max_tokens=2048,max_pixels=65536,
                runtime_versions=dict(torch='fixture',transformers='fixture',peft='fixture',safetensors='fixture'))


def make_data(root):
    root.mkdir();rows=[]
    for split,color in zip(('train','validation','test'),('red','green','blue')):
        Image.new('RGB',(64,64),color).save(root/(split+'.png'))
        rows.append({'image':split+'.png','split':split,'messages':[{'role':'user','content':'PCF'},{'role':'assistant','content':'Porte coupe-feu'}]})
    (root/'examples.json').write_text(json.dumps({'engine':'qwen'}))
    (root/'qwen.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    return rows


def test_dataset_prompt_and_assistant_mask_are_separate_and_fail_closed(modules,tmp_path):
    helper,_,_=modules;root=tmp_path/'data';rows=make_data(root)
    splits,_=helper.dataset(root);assert all(len(v)==1 for v in splits.values())
    assert helper.assistant_labels([1,2,3,4],[1,2],10)==[-100,-100,3,4]
    for full,prefix,limit in [([1,2,3],[1,4],10),([1,2],[1,2],10),([1,2,3],[1],2)]:
        with pytest.raises(ValueError):helper.assistant_labels(full,prefix,limit)
    prompt=helper.messages(rows[0],None)
    assert len(prompt)==2 and 'Porte coupe-feu' not in str(prompt) and 'PCF' in str(prompt)
    (root/'test.png').write_bytes((root/'train.png').read_bytes())
    with pytest.raises(ValueError,match='plusieurs lots'):helper.dataset(root)
    rows[0]['image']='../external.png';(root/'qwen.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    with pytest.raises(ValueError,match='inaccessible'):helper.dataset(root)


class CpuSession:
    def __init__(self,control=None):self.weight=0;self.optimizer=0;self.control=control
    def step(self,row,seed):
        self.optimizer+=1;self.weight+=self.optimizer
        if self.control:self.control.write_text('pause');self.control=None
        return .5
    def save(self,folder):
        (folder/'adapter_model.safetensors').write_text(str(self.weight));(folder/'adapter_config.json').write_text('{}');(folder/'optimizer.pt').write_text(str(self.optimizer))
    def restore(self,folder):
        self.weight=int((folder/'adapter_model.safetensors').read_text());self.optimizer=int((folder/'optimizer.pt').read_text())


def test_batch_pause_resume_optimizer_matches_uninterrupted_fixture(modules,tmp_path):
    _,driver,service=modules
    with pytest.raises(ValueError,match='Autorisation'):driver.run(Namespace(authorize_gpu_training=False))
    root=tmp_path/'volume';job=root/'training/jobs'/('a'*32);job.mkdir(parents=True)
    tmp=tmp_path/'work';tmp.mkdir();(tmp/'training_config.json').write_text('{}')
    control=tmp/'control';control.write_text('run');args=Namespace(epochs=2,control=str(control),resume_manifest=None)
    record=dict(id=job.name,engine='qwen',dataset_sha256='b'*64,profile_id='c'*64,parameters={'epochs':2,'batch_size':1,'learning_rate':.0001})
    events=[];emit=lambda event,**v:events.append(dict(event=event,**v))
    with pytest.raises(driver.Paused):driver.train(CpuSession(control),args,record,[1,2,3],job,root,tmp,emit)
    path=root/next(e['manifest'] for e in events if e['event']=='checkpoint')
    assert service.verify(path)['metadata']['cursor']==1
    control.write_text('run');args.resume_manifest=str(path);resumed=CpuSession()
    final=driver.train(resumed,args,record,[1,2,3],job,root,tmp,emit)
    assert resumed.optimizer==6 and resumed.weight==21
    args.resume_manifest=None;plain=CpuSession();driver.train(plain,args,record,[1,2,3],job,root,tmp,emit)
    assert plain.weight==resumed.weight
    # Cancel before any optimizer step; checkpoint corruption cannot resume.
    control.write_text('cancel');cancelled=CpuSession()
    with pytest.raises(driver.Cancelled):driver.train(cancelled,args,record,[1],job,root,tmp,emit)
    assert cancelled.optimizer==0
    control.write_text('run');args.resume_manifest=str(path);(path.parent/'optimizer.pt').write_text('corrupted')
    with pytest.raises(ValueError):driver.train(CpuSession(),args,record,[1,2,3],job,root,tmp,emit)


def test_qwen_profile_hashes_base_config_and_runtime(modules,monkeypatch):
    helper,_,service=modules;root=Path('/workspace/doemo-studio');root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='qwen-cpu-profile-',dir=root) as directory:
        folder=Path(directory);base=folder/'base';base.mkdir();(base/'config.json').write_text('{}');(base/'model.safetensors').write_text('CPU fixture only')
        cfg=folder/'training.json';cfg.write_text(json.dumps(config()))
        value=profile_value();value.update(config=str(cfg),weights=str(base),config_sha256=service.sha256(cfg),weights_sha256=helper.model_hash(base),driver_sha256=service.sha256(service.QWEN_DRIVER),runtime_sha256=service.runtime_hash())
        path=folder/'profile.json';path.write_text(json.dumps(value));monkeypatch.setenv('DOEMO_QWEN_TRAINING_PROFILE',str(path));monkeypatch.setattr(service.os.path,'ismount',lambda _:True)
        assert service.load_qwen_profile()['public']==training_jobs.profile('qwen')
        (base/'config.json').write_text('{"changed":true}')
        assert service.load_qwen_profile() is None
        value['acceptance']['resume_verified']=False;path.write_text(json.dumps(value));assert training_jobs.profile('qwen') is None


def test_qwen_gateway_fixed_driver_and_shared_compute_lock(modules,tmp_path,monkeypatch):
    _,_,service=modules;root=tmp_path/'data';make_data(root);archive=tmp_path/'data.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for path in root.iterdir():z.write(path,path.name)
    profile={'public':dict(id='a'*64,engine='qwen'),'config':'fixture','weights':'fixture-base'}
    spec=dict(id='b'*32,engine='qwen',profile_id='a'*64,parameters={'epochs':2,'batch_size':1,'learning_rate':.0001},dataset_id='c'*32,dataset_sha256=service.digest({'engine':'qwen'}),archive_sha256=service.sha256(archive))
    store=service.JobStore(tmp_path/'volume');store.admit(spec['id'],spec,archive,profile)
    driver=tmp_path/'qwen-fixture.py';driver.write_text("import json\nprint('DOEMO_EVENT='+json.dumps({'event':'cancelled'}),flush=True)\n")
    monkeypatch.setattr(service,'QWEN_DRIVER',driver);monkeypatch.setattr(service,'QWEN_PYTHON',sys.executable)
    async def run():
        lock=asyncio.Lock();manager=service.Manager(store.root,lock,lambda:True,lambda:False,lambda:None,lambda:{},lambda:None,lambda:None,lambda:profile)
        await manager.initialize();assert manager.profile_for('qwen')==profile
        await manager.run(spec['id']);assert not lock.locked() and manager.proc.returncode==0
    asyncio.run(run());assert store.state(spec['id'])['status']=='cancelled'
    invalid=dict(spec,parameters=dict(spec['parameters'],batch_size=2))
    with pytest.raises(ValueError):service.spec_valid(invalid,spec['id'])


def test_qwen_api_requires_acceptance_binds_artifacts_and_blocks_promotion(api,tmp_path,monkeypatch):
    examples=[]
    for color in ('red','green','blue'):
        p=source(api,color);_,e=example(api,'qwen',p,[],convention='PCF',interpretation='Porte coupe-feu');examples.append(validate(api,p,e))
    d=dataset(api,'qwen',examples);data=dict(engine='qwen',dataset_id=d['id'],epochs=2,batch_size=1,learning_rate=.0001,confirmed=True,request_key='qwen-request-001')
    assert api.post(PREFIX+'/runs',json=data).status_code==503
    path=tmp_path/'qwen-profile.json';path.write_text(json.dumps(profile_value()))
    for key,value in {'DOEMO_QWEN_TRAINING_PROFILE':str(path),'DOEMO_RUNPOD_MANAGED':'1','RUNPOD_API_KEY':'fixture','DOEMO_RUNPOD_POD_ID':'fixture','DOEMO_RUNPOD_TOKEN':'t'*32}.items():monkeypatch.setenv(key,value)
    caps=api.get(PREFIX+'/capabilities').json()['engines'];assert caps['qwen']['training'] and caps['qwen']['batch_size_max']==1 and not caps['architecture']['training']
    assert not caps['qwen']['deployment'] and not caps['qwen']['evaluation']
    assert api.post(PREFIX+'/runs',json=dict(data,batch_size=2)).status_code==422
    r=api.post(PREFIX+'/runs',json=data);assert r.status_code==200,r.text
    job=r.json();assert api.post(PREFIX+'/runs',json=data).json()['id']==job['id'] and gpu.pending(api.app.state.store)==1
    manifest={'schema':'doemo.artifacts/1','metadata':dict(id=job['id'],engine='qwen',dataset_sha256=d['sha256'],profile_id=job['profile']['id'],parameters=job['parameters'],status='completed',metrics={'test_assistant_loss':.5}),
              'files':[dict(name=n,bytes=10,sha256='c'*64) for n in ('adapter_model.safetensors','adapter_config.json','training_config.json','metrics.json')]}
    assert training_jobs.valid_result(job,d,{'result':manifest,'artifacts_verified':True})==manifest
    manifest['files'][0]['name']='weights.pth'
    with pytest.raises(ValueError):training_jobs.valid_result(job,d,{'result':manifest,'artifacts_verified':True})
    assert api.post(PREFIX+'/runs/'+job['id']+'/cancel').json()['status']=='cancelled'
    # Labelled completion fixture to exercise registry isolation, never GPU output.
    manifest['files'][0]['name']='adapter_model.safetensors'
    with api.app.state.store.connect() as c:
        c.execute("UPDATE training_runs SET status='completed',result=? WHERE id=?",(json.dumps(manifest),job['id']))
    response=api.post(PREFIX+'/models/qwen/versions',json={'name':'Adaptateur fixture','dataset_id':d['id'],'run_id':job['id']})
    assert response.status_code==200 and response.json()['method']=='weights'
    version=response.json()['id']
    assert api.post(PREFIX+'/models/qwen/'+version+'/test').status_code==503
    for action in ('approve','publish','rollback'):
        assert api.post(PREFIX+'/models/qwen/'+version+'/'+action,json={'confirmed':True}).status_code==409

