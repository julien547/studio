"""CPU fixtures only: no Paddle import, trained weights or GPU acceptance claimed."""
import asyncio
import copy
import json
import sys
import tempfile
import time
import zipfile
from argparse import Namespace
from pathlib import Path
import pytest
from PIL import Image
from test_training import api,source,label,example,validate,dataset,PREFIX
from doemo_releves import gpu,training_jobs

@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/'services/runpod'))
    import paddle_training,paddle_pipeline,training_service
    return paddle_training,paddle_pipeline,training_service

@pytest.fixture
def ocr_data(tmp_path):
    root=tmp_path/'data';root.mkdir();rows=[]
    for split,color in zip(('train','validation','test'),('red','green','blue')):
        Image.new('RGB',(100,32),color).save(root/(split+'.png'))
        rows.append({'image':split+'.png','split':split,'text':'H₂O'})
    (root/'ocr.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows))
    (root/'examples.json').write_text(json.dumps({'engine':'paddleocr'}))
    dictionary=tmp_path/'dictionary.txt';dictionary.write_text('H\n₂\nO\n')
    return root,dictionary,rows


def config():
    return {'Architecture':{'model_type':'rec','algorithm':'CRNN','Head':{'name':'CTCHead'}},'Loss':{'name':'CTCLoss'},
            'PostProcess':{'name':'CTCLabelDecode'},'Global':{'max_text_length':25,'use_space_char':False},
            'Train':{'dataset':{'name':'SimpleDataSet','transforms':[{'DecodeImage':{}}]}},
            'Eval':{'dataset':{'name':'SimpleDataSet','transforms':[{'DecodeImage':{}}]}}}


def test_labels_are_exact_and_detector_or_unknown_characters_are_refused(modules,ocr_data,tmp_path):
    data,_,_=modules;root,dictionary,rows=ocr_data
    value,splits,_=data.configuration(config(),root,tmp_path,dictionary,2,1,.0001)
    assert 'H₂O' in Path(splits['train']).read_text() and not value['Global']['lower']
    wrong=config();wrong['Architecture']['model_type']='det'
    with pytest.raises(ValueError,match='reconnaissance'):data.configuration(wrong,root,tmp_path,dictionary,2,1,.0001)
    dictionary.write_text('H\n2\nO\n')
    with pytest.raises(ValueError,match='caractère absent'):data.configuration(config(),root,tmp_path,dictionary,2,1,.0001)
    dictionary.write_text('H\n₂\nO\n')
    (root/'test.png').write_bytes((root/'train.png').read_bytes())
    with pytest.raises(ValueError,match='plusieurs lots'):data.configuration(config(),root,tmp_path,dictionary,2,1,.0001)


def test_metrics_and_training_reader_reject_normalized_or_missing_labels(modules):
    data,_,_=modules
    metric=data.ExactMetric(['H₂O','PCF'])
    metric.add(([('H2O',.8),('PCF',1)],[('H₂O',1),('PCF',1)]))
    values=metric.finish();assert values['cer']==pytest.approx(1/6) and values['wer']==.5
    assert values['exact_match']==.5 and values['samples']==2
    with pytest.raises(ValueError):data.ExactMetric(['H₂O']).add(([('H2O',.8)],[('H2O',1)]))
    with pytest.raises(ValueError):data.ExactMetric(['PCF']).finish()
    assert list(data.CheckedLoader([['PCF'],['H₂O']],['H₂O','PCF'],lambda x:x))==[['PCF'],['H₂O']]
    with pytest.raises(ValueError):list(data.CheckedLoader([['H2O']],['H₂O'],lambda x:x))
    with pytest.raises(ValueError):list(data.CheckedLoader([['PCF']],['PCF','H₂O'],lambda x:x))


class CpuSession:
    """Numerical fixture, deliberately not a Paddle model or real weights."""
    def __init__(self):self.weight=0;self.optimizer=0
    def loader(self,mode,seed):return [1,1]
    def step(self,batch):self.optimizer+=1;self.weight+=self.optimizer;return 1/self.optimizer
    def save(self,folder):
        (folder/'weights.pdparams').write_text(json.dumps(self.weight));(folder/'optimizer.pdopt').write_text(json.dumps(self.optimizer))
    def restore(self,folder):
        self.weight=json.loads((folder/'weights.pdparams').read_text());self.optimizer=json.loads((folder/'optimizer.pdopt').read_text())


def test_epoch_checkpoint_resume_restores_optimizer_and_matches_uninterrupted_fixture(modules,tmp_path):
    _,driver,service=modules
    root=tmp_path/'volume';job=root/'training/jobs'/('a'*32);job.mkdir(parents=True)
    work=tmp_path/'work';work.mkdir()
    for name in ('training_config.yaml','dictionary.txt'):(work/name).write_text('fixture')
    control=work/'control';control.write_text('pause')
    args=Namespace(epochs=2,control=str(control));events=[]
    record={'id':job.name,'engine':'paddleocr','dataset_sha256':'b'*64,'profile_id':'c'*64,'parameters':{'epochs':2,'batch_size':1,'learning_rate':.0001}}
    emit=lambda event,**kw:events.append(dict(event=event,**kw))
    with pytest.raises(driver.Paused):driver.train_epochs(CpuSession(),args,record,job,root,work,emit)
    checkpoint=root/next(e['manifest'] for e in events if e['event']=='checkpoint')
    assert service.verify(checkpoint)['metadata']['epoch']==1
    control.write_text('run');resumed=CpuSession()
    final=driver.train_epochs(resumed,args,record,job,root,work,emit,checkpoint)
    assert resumed.weight==10 and resumed.optimizer==4 and service.verify(final)['metadata']['epoch']==2
    uninterrupted=CpuSession();driver.train_epochs(uninterrupted,args,record,job,root,work,emit)
    assert (resumed.weight,resumed.optimizer)==(uninterrupted.weight,uninterrupted.optimizer)
    (checkpoint.parent/'optimizer.pdopt').write_text('corrupted')
    with pytest.raises(ValueError):driver.train_epochs(CpuSession(),args,record,job,root,work,emit,checkpoint)
    control.write_text('cancel');cancelled=CpuSession()
    with pytest.raises(driver.Cancelled):driver.train_epochs(cancelled,args,record,job,root,work,emit)
    assert cancelled.optimizer==0
    control.write_text('pause')
    with pytest.raises(driver.Paused):driver.evaluation_control(args)
    control.write_text('run');driver.evaluation_control(args)


def test_gateway_routes_paddle_to_fixed_driver_and_shared_lock(modules,ocr_data,tmp_path,monkeypatch):
    _,_,service=modules;root,_,_=ocr_data
    archive=tmp_path/'data.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for path in root.iterdir():
            if path.is_file():z.write(path,path.name)
    profile={'public':{'id':'f'*64,'engine':'paddleocr'},'config':'fixture.yaml','weights':'fixture.pdparams','repository':'fixture-repo','dictionary':'fixture-dict'}
    store=service.JobStore(tmp_path/'volume')
    spec={'id':'a'*32,'engine':'paddleocr','profile_id':'f'*64,'dataset_id':'b'*32,'dataset_sha256':service.digest({'engine':'paddleocr'}),'archive_sha256':service.sha256(archive),'parameters':{'epochs':2,'batch_size':1,'learning_rate':.0001}}
    store.admit(spec['id'],spec,archive,profile)
    driver=tmp_path/'cpu-paddle-fixture.py';driver.write_text("import sys,json\nassert '--repository' in sys.argv and '--dictionary' in sys.argv\nprint('DOEMO_EVENT='+json.dumps({'event':'cancelled'}),flush=True)\n")
    monkeypatch.setattr(service,'PADDLE_DRIVER',driver);monkeypatch.setattr(service,'PADDLE_PYTHON',sys.executable)
    async def run():
        lock=asyncio.Lock();manager=service.Manager(store.root,lock,lambda:True,lambda:False,lambda:None,lambda:{},lambda:None,lambda:profile)
        await manager.initialize();assert manager.profile_for('paddleocr')==profile and manager.profile_for('rtmdet') is None
        await manager.run(spec['id']);assert not lock.locked() and manager.proc.returncode==0
    asyncio.run(run());assert store.state(spec['id'])['status']=='cancelled'


def test_operator_profile_binds_repository_dictionary_and_backend_id(modules,monkeypatch):
    helper,_,service=modules
    # Local fixture under the required prefix, never a real mount or server.
    root=Path('/workspace/doemo-studio');root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cpu-profile-test-',dir=root) as directory:
        folder=Path(directory);repo=folder/'repository';arch=repo/'ppocr/modeling/architectures';arch.mkdir(parents=True)
        (arch/'__init__.py').write_text('# CPU fixture only\n')
        for name in ('config.yaml','weights.pdparams','dictionary.txt'):(folder/name).write_text('CPU fixture only')
        value={'engine':'paddleocr','driver_sha256':service.sha256(service.PADDLE_DRIVER),'runtime_sha256':service.runtime_hash(),
               'config':str(folder/'config.yaml'),'weights':str(folder/'weights.pdparams'),'dictionary':str(folder/'dictionary.txt'),'repository':str(repo),
               'source_sha256':helper.source_hash(repo),'acceptance':dict(training_completed=True,resume_verified=True,inference_preemption_verified=True,cancel_verified=True,report_sha256='e'*64)}
        for key in ('config','weights','dictionary'):value[key+'_sha256']=service.sha256(value[key])
        path=folder/'fixture-profile.json';path.write_text(json.dumps(value))
        monkeypatch.setenv('DOEMO_PADDLE_TRAINING_PROFILE',str(path));monkeypatch.setattr(service.os.path,'ismount',lambda x:True)
        loaded=service.load_paddle_profile();assert loaded['public']==training_jobs.profile('paddleocr')
        (folder/'dictionary.txt').write_text('modified')
        assert service.load_paddle_profile() is None


def test_paddle_api_admission_and_artifacts_are_separate_from_rtmdet(api,tmp_path,monkeypatch):
    value={'engine':'paddleocr',**{k:'a'*64 for k in ('driver_sha256','runtime_sha256','config_sha256','weights_sha256','source_sha256','dictionary_sha256')},
           'acceptance':dict(training_completed=True,resume_verified=True,inference_preemption_verified=True,cancel_verified=True,report_sha256='b'*64)}
    path=tmp_path/'profile.json';path.write_text(json.dumps(value))
    for key,value in {'DOEMO_PADDLE_TRAINING_PROFILE':str(path),'DOEMO_RUNPOD_MANAGED':'1','RUNPOD_API_KEY':'fixture-only','DOEMO_RUNPOD_TOKEN':'t'*32,'DOEMO_RUNPOD_POD_ID':'fixture-pod'}.items():monkeypatch.setenv(key,value)
    examples=[]
    for color in ('red','green','blue'):
        p=source(api,color);_,e=example(api,'paddleocr',p,[dict(label(),text='H₂O')]);examples.append(validate(api,p,e))
    d=dataset(api,'paddleocr',examples)
    data=dict(engine='paddleocr',dataset_id=d['id'],epochs=2,batch_size=1,learning_rate=.0001,confirmed=True,request_key='paddle-request-001')
    response=api.post(PREFIX+'/runs',json=data);assert response.status_code==200,response.text
    job=response.json();assert api.post(PREFIX+'/runs',json=data).json()['id']==job['id']
    assert job['profile']['driver']=='paddleocr.recognition/1' and gpu.pending(api.app.state.store)==1
    cap=api.get(PREFIX+'/capabilities').json()['engines'];assert cap['paddleocr']['training'] and not cap['qwen']['training']
    assert training_jobs.profile('rtmdet') is None
    manifest={'schema':'doemo.artifacts/1','metadata':{'id':job['id'],'engine':'paddleocr','dataset_sha256':d['sha256'],'profile_id':job['profile']['id'],'parameters':job['parameters'],'status':'completed','metrics':{'cer':.1,'wer':.2}},
              'files':[{'name':name,'bytes':10,'sha256':'c'*64} for name in ('weights.pdparams','training_config.yaml','dictionary.txt','metrics.json','predictions.json')]}
    reply={'result':manifest,'artifacts_verified':True}
    assert training_jobs.valid_result(job,d,reply)==manifest
    manifest['files'][0]['name']='weights.pth'
    with pytest.raises(ValueError):training_jobs.valid_result(job,d,reply)
    assert api.post(PREFIX+'/runs/'+job['id']+'/cancel').json()['status']=='cancelled'
