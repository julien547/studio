"""Single-GPU training admission and persistent state, owned by the gateway.

No SQLite, locks, rename or chmod on /workspace. Control files and the exclusive
compute lock live in /tmp. A private, accepted profile chooses fixed local code;
HTTP callers cannot supply Python, command lines or model paths.
"""
import asyncio
import contextlib
import hashlib
import json
import math
import os
import re
import signal
import tempfile
import threading
import time
import uuid
from pathlib import Path
from artifacts import sha256,verify
from training_data import unpack,detection_splits,ocr_splits

ID=re.compile(r'^[a-f0-9]{32}$')
HASH=re.compile(r'^[a-f0-9]{64}$')
TERMINAL=('completed','failed','cancelled')
DRIVER=Path(__file__).with_name('rtmdet_pipeline.py')
PYTHON='/opt/doemo-rtmdet-venv/bin/python'
PADDLE_DRIVER=Path(__file__).with_name('paddle_pipeline.py')
PADDLE_PYTHON='/opt/doemo-ocr-venv/bin/python'


def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(encoded(value).encode()).hexdigest()


def runtime_hash():
    names=('training_service.py','rtmdet_pipeline.py','compute.py','training_data.py','artifacts.py','gateway.py','infer.py','readiness.py','qwen_prompt.py','paddle_pipeline.py','paddle_training.py')
    return digest({name:sha256(Path(__file__).with_name(name)) for name in names})


def load_profile():
    path=os.environ.get('DOEMO_TRAINING_PROFILE','')
    if not path or not os.path.ismount('/workspace'):return None
    try:
        if Path(path).stat().st_size>65536:return None
        value=json.loads(Path(path).read_text());keys=('driver_sha256','runtime_sha256','config_sha256','weights_sha256')
        if value.get('engine')!='rtmdet' or any(not HASH.fullmatch(value.get(k,'')) for k in keys):return None
        evidence=value.get('acceptance',{})
        if any(evidence.get(k) is not True for k in ('training_completed','resume_verified','inference_preemption_verified','cancel_verified')):return None
        if not HASH.fullmatch(evidence.get('report_sha256','')):return None
        if sha256(DRIVER)!=value['driver_sha256'] or runtime_hash()!=value['runtime_sha256']:return None
        for key in ('config','weights'):
            local=Path(value[key]).resolve()
            if not local.is_relative_to('/workspace/doemo-studio') or sha256(local)!=value[key+'_sha256']:return None
        clean={k:value[k] for k in keys};clean.update(engine='rtmdet',driver='rtmdet.training/1',acceptance={k:evidence[k] for k in ('training_completed','resume_verified','inference_preemption_verified','cancel_verified','report_sha256')})
        clean['id']=digest(clean)
        return {'public':clean,'config':value['config'],'weights':value['weights']}
    except (OSError,ValueError,KeyError,TypeError,AttributeError):return None


def load_paddle_profile():
    path=os.environ.get('DOEMO_PADDLE_TRAINING_PROFILE','')
    if not path or not os.path.ismount('/workspace'):return None
    try:
        if Path(path).stat().st_size>65536:return None
        value=json.loads(Path(path).read_text());keys=('driver_sha256','runtime_sha256','config_sha256','weights_sha256','source_sha256','dictionary_sha256')
        if value.get('engine')!='paddleocr' or any(not HASH.fullmatch(value.get(k,'')) for k in keys):return None
        evidence=value.get('acceptance',{})
        if any(evidence.get(k) is not True for k in ('training_completed','resume_verified','inference_preemption_verified','cancel_verified')) or not HASH.fullmatch(evidence.get('report_sha256','')):return None
        if sha256(PADDLE_DRIVER)!=value['driver_sha256'] or runtime_hash()!=value['runtime_sha256']:return None
        from paddle_training import source_hash
        for key in ('config','weights','dictionary','repository'):
            local=Path(value[key]).resolve()
            if not local.is_relative_to('/workspace/doemo-studio'):return None
            if (source_hash(local) if key=='repository' else sha256(local))!=value['source_sha256' if key=='repository' else key+'_sha256']:return None
        clean={k:value[k] for k in keys};clean.update(engine='paddleocr',driver='paddleocr.recognition/1',acceptance={k:evidence[k] for k in ('training_completed','resume_verified','inference_preemption_verified','cancel_verified','report_sha256')})
        clean['id']=digest(clean)
        return {'public':clean,**{k:value[k] for k in ('config','weights','dictionary','repository')}}
    except (OSError,ValueError,KeyError,TypeError,AttributeError):return None


def spec_valid(value,ident):
    if set(value)!={'id','engine','profile_id','parameters','dataset_id','dataset_sha256','archive_sha256'}:raise ValueError('Contrat de demande invalide')
    if value['id']!=ident or not ID.fullmatch(ident) or value['engine'] not in ('rtmdet','paddleocr'):raise ValueError('Moteur ou identifiant invalide')
    if not ID.fullmatch(value['dataset_id']) or any(not HASH.fullmatch(value[k]) for k in ('profile_id','dataset_sha256','archive_sha256')):raise ValueError('Empreintes invalides')
    p=value['parameters']
    if set(p)!={'epochs','batch_size','learning_rate'} or type(p['epochs']) is not int or type(p['batch_size']) is not int:raise ValueError('Paramètres invalides')
    if not 1<=p['epochs']<=100 or not 1<=p['batch_size']<=4 or type(p['learning_rate']) not in (int,float) or not 0<p['learning_rate']<=.001:raise ValueError('Paramètres hors limites')


class JobStore:
    def __init__(self,root):self.root=Path(root);self.queue=self.root/'training/queue';self.mutex=threading.RLock()
    def directory(self,ident):
        if not ID.fullmatch(ident):raise ValueError('Identifiant invalide')
        return self.queue/ident
    def request(self,ident):
        folder=self.directory(ident);value=json.loads((folder/'request.json').read_text())
        accepted=json.loads((folder/'accepted.json').read_text())
        if accepted['sha256']!=digest(value):raise ValueError('Demande persistante incomplète')
        return value
    def state(self,ident):
        with self.mutex:
            folder=self.directory(ident)
            if not folder.exists():return None
            files=sorted(folder.glob('event-*.json'))
            if not files:return {'id':ident,'status':'interrupted','revision':0,'error':'Admission persistante incomplète'}
            revision=int(files[-1].name.split('-')[1])
            try:
                value=json.loads(files[-1].read_text())
                if value['id']!=ident or value['revision']!=revision:raise ValueError()
                return value
            except (OSError,ValueError,KeyError):return {'id':ident,'status':'interrupted','revision':revision,'error':'Écriture persistante incomplète'}
    def append(self,ident,**fields):
        with self.mutex:
            folder=self.directory(ident);folder.mkdir(parents=True,exist_ok=True)
            old=self.state(ident) or {'id':ident,'revision':0}
            value=dict(old,**fields,revision=old['revision']+1,updated=time.time())
            file=folder/f"event-{value['revision']:012d}-{uuid.uuid4().hex}.json"
            with file.open('x') as out:out.write(encoded(value))
            return value
    def admit(self,ident,spec,archive,profile):
        spec_valid(spec,ident)
        with self.mutex:
            prior=self.state(ident)
            if prior:
                # A cancellation tombstone forbids even a late first upload.
                if prior['status']=='cancelled':return prior
                if self.request(ident)!=spec:raise ValueError('Identifiant déjà associé à une autre demande')
                return prior
            if not profile or spec['profile_id']!=profile['public']['id']:raise ValueError('Profil accepté incompatible')
            if profile['public'].get('engine','rtmdet')!=spec['engine']:raise ValueError('Profil d’un autre moteur')
            if sha256(archive)!=spec['archive_sha256']:raise ValueError('Archive corrompue')
            # Validate complete splits on local POSIX disk before admission.
            with tempfile.TemporaryDirectory(prefix='doemo-dataset-check-',dir='/tmp') as tmp:
                extracted=unpack(archive,Path(tmp)/'data')
                snapshot=json.loads((extracted/'examples.json').read_text())
                if digest(snapshot)!=spec['dataset_sha256'] or snapshot.get('engine')!=spec['engine']:raise ValueError('Snapshot incompatible')
                if spec['engine']=='rtmdet':detection_splits(extracted)
                else:ocr_splits(extracted)
            folder=self.directory(ident);folder.mkdir(parents=True,exist_ok=False)
            import shutil
            shutil.copyfile(archive,folder/'dataset.zip')
            if sha256(folder/'dataset.zip')!=spec['archive_sha256']:raise ValueError('Copie persistante incomplète')
            (folder/'request.json').write_text(encoded(spec))
            (folder/'accepted.json').write_text(encoded({'sha256':digest(spec),'created':time.time()}))
            return self.append(ident,status='queued',progress=None,checkpoint=None,pause_reason=None,error=None)
    def all(self):
        return [self.state(p.name) for p in sorted(self.queue.glob('*')) if p.is_dir() and ID.fullmatch(p.name)]
    def pending(self):return sum(s['status'] not in TERMINAL for s in self.all())
    def artifact(self,ident,relative):
        path=(self.root/relative).resolve()
        if not path.is_relative_to((self.root/'training/jobs'/ident).resolve()) or path.name!='manifest.json':raise ValueError('Chemin d’artefact refusé')
        return path
    def public(self,ident):
        value=self.state(ident)
        if value is None:return None
        if value['status']=='completed':
            result=verify(self.artifact(ident,value['result_manifest']))
            spec=self.request(ident);meta=result['metadata']
            if any(meta.get(k)!=spec.get(k) for k in ('id','engine','dataset_sha256','profile_id','parameters')):raise ValueError('Résultat incompatible')
            value=dict(value,result=result,artifacts_verified=True)
        return value
    def recover(self):
        for state in self.all():
            if state['status'] not in (*TERMINAL,'queued','paused','interrupted'):
                self.append(state['id'],status='interrupted',pause_reason='restart',error='Processus interrompu ; reprise explicite depuis le dernier checkpoint requis')


class Manager:
    def __init__(self,root,compute_lock,ready,draining,activity,environment,profile_loader=load_profile,paddle_profile_loader=load_paddle_profile):
        self.store=JobStore(root);self.lock=compute_lock;self.ready=ready;self.draining=draining;self.activity=activity
        self.environment=environment;self.profile_loader=profile_loader;self.profile=None
        self.paddle_profile_loader=paddle_profile_loader;self.paddle_profile=None
        self.active=None;self.control_file=None;self.proc=None;self.priority_until=0
    async def initialize(self):
        self.profile=await asyncio.to_thread(self.profile_loader)
        self.paddle_profile=await asyncio.to_thread(self.paddle_profile_loader)
        await asyncio.to_thread(self.store.recover)
    def profile_for(self,engine):return self.paddle_profile if engine=='paddleocr' else self.profile if engine=='rtmdet' else None
    async def control(self,ident,action):
        state=await asyncio.to_thread(self.store.state,ident)
        if action=='cancel':
            if state and state['status'] in TERMINAL:return state
            if self.active==ident:
                if self.control_file is None:return await asyncio.to_thread(self.store.append,ident,status='cancelled',error=None)
                self.control_file.write_text('cancel')
                return await asyncio.to_thread(self.store.append,ident,status='cancel_requested')
            return await asyncio.to_thread(self.store.append,ident,status='cancelled',error=None)
        if not state:raise LookupError()
        if state['status'] in TERMINAL:return state
        if action=='pause':
            self.priority_until=time.monotonic()+60
            if self.active==ident:
                if state['status']=='cancel_requested':return state
                if self.control_file is None:return await asyncio.to_thread(self.store.append,ident,status='paused',pause_reason='inference')
                self.control_file.write_text('pause')
                return await asyncio.to_thread(self.store.append,ident,status='checkpointing',pause_reason='inference')
            if state['status']=='queued':return await asyncio.to_thread(self.store.append,ident,status='paused',pause_reason='inference')
            return state
        if action!='resume':raise ValueError('Action invalide')
        if state['status'] not in ('paused','interrupted'):return state
        if state['status']=='interrupted' and not state.get('checkpoint'):raise ValueError('Aucun checkpoint reprenable ; créer une nouvelle demande explicitement')
        if self.active or self.lock.locked() or self.draining() or not self.ready():raise ValueError('GPU indisponible pour reprendre')
        if state.get('checkpoint'):await asyncio.to_thread(verify,self.store.artifact(ident,state['checkpoint']))
        self.store.request(ident)
        return await asyncio.to_thread(self.store.append,ident,status='queued',pause_reason=None,error=None)
    async def infer_priority(self):
        self.priority_until=time.monotonic()+60
        if self.active:await self.control(self.active,'pause')
    async def loop(self):
        try:
            while True:
                if (self.profile or self.paddle_profile) and self.ready() and not self.draining() and not self.lock.locked() and time.monotonic()>=self.priority_until:
                    queued=[s for s in await asyncio.to_thread(self.store.all) if s['status']=='queued']
                    if queued:await self.run(queued[0]['id'])
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            if self.proc and self.proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):os.killpg(self.proc.pid,signal.SIGTERM)
                try:await asyncio.wait_for(self.proc.wait(),15)
                except asyncio.TimeoutError:
                    with contextlib.suppress(ProcessLookupError):os.killpg(self.proc.pid,signal.SIGKILL)
                    await self.proc.wait()
            if self.active:await asyncio.to_thread(self.store.append,self.active,status='interrupted',pause_reason='restart',error='Service interrompu')
            raise
    async def run(self,ident):
        async with self.lock:
            # Admission may have been cancelled while filesystem work yielded.
            if self.store.state(ident)['status']!='queued':return
            self.active=ident;self.activity()
            try:
                spec=self.store.request(ident)
                paddle=spec['engine']=='paddleocr'
                current_profile=await asyncio.to_thread(self.paddle_profile_loader if paddle else self.profile_loader)
                if not current_profile or current_profile['public']['id']!=spec['profile_id']:raise ValueError('Profile changed')
                folder=self.store.directory(ident)
                if await asyncio.to_thread(sha256,folder/'dataset.zip')!=spec['archive_sha256']:raise ValueError('Dataset corrupted')
                state=self.store.state(ident)
                if state['status']!='queued':return
                with tempfile.TemporaryDirectory(prefix='doemo-training-control-',dir='/tmp') as tmp:
                    self.control_file=Path(tmp)/'control';self.control_file.write_text('run')
                    args=[PADDLE_PYTHON if paddle else PYTHON,str(PADDLE_DRIVER if paddle else DRIVER),'--dataset',str(folder/'dataset.zip'),'--config',current_profile['config'],'--weights',current_profile['weights'],
                          '--output',str(self.store.root),'--authorize-gpu-training','--managed-job',ident,'--control',str(self.control_file),
                          '--dataset-sha256',spec['dataset_sha256'],'--profile-id',spec['profile_id'],
                          '--epochs',str(spec['parameters']['epochs']),'--batch-size',str(spec['parameters']['batch_size']),'--learning-rate',str(spec['parameters']['learning_rate'])]
                    if paddle:args+=['--repository',current_profile['repository'],'--dictionary',current_profile['dictionary']]
                    if state.get('checkpoint'):args+=['--resume-manifest',str(self.store.artifact(ident,state['checkpoint']))]
                    self.store.append(ident,status='running',error=None,completion_received=False)
                    logs=self.store.root/'training/logs'/ident;logs.mkdir(parents=True,exist_ok=True)
                    with (logs/(uuid.uuid4().hex+'.log')).open('wb') as output:
                        self.proc=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.PIPE,stderr=output,
                            env=dict(self.environment(),DOEMO_TRAINING_CHILD='1'),start_new_session=True,limit=1024*1024)
                        async for line in self.proc.stdout:
                            output.write(line)
                            if line.startswith(b'DOEMO_EVENT='):
                                try:await self.receive(ident,json.loads(line[len(b'DOEMO_EVENT='):]))
                                except (ValueError,KeyError,TypeError):raise ValueError('Invalid driver event')
                        code=await self.proc.wait()
                    state=self.store.state(ident)
                    if code==0 and state.get('completion_received'):
                        self.store.append(ident,status='completed',error=None)
                        state=self.store.state(ident)
                    if code or state['status'] not in (*TERMINAL,'paused'):raise ValueError('Training process failed')
            except asyncio.CancelledError:
                # Reap our child BEFORE releasing the shared compute lock. This
                # also covers operator acceptance timeouts outside loop().
                if self.proc and self.proc.returncode is None:
                    with contextlib.suppress(ProcessLookupError):os.killpg(self.proc.pid,signal.SIGTERM)
                    try:await asyncio.wait_for(self.proc.wait(),15)
                    except asyncio.TimeoutError:
                        with contextlib.suppress(ProcessLookupError):os.killpg(self.proc.pid,signal.SIGKILL)
                        await self.proc.wait()
                self.store.append(ident,status='interrupted',pause_reason='restart',error='Service interrompu ; reprise explicite requise')
                raise
            except Exception:
                if self.proc and self.proc.returncode is None:
                    with contextlib.suppress(ProcessLookupError):os.killpg(self.proc.pid,signal.SIGKILL)
                    await self.proc.wait()
                self.store.append(ident,status='failed',error='Entraînement interrompu ; consulter les journaux persistants')
            finally:
                self.activity()
                if not self.proc or self.proc.returncode is not None:self.active=None;self.control_file=None
    async def receive(self,ident,item):
        event=item.get('event');state=self.store.state(ident)
        if event=='progress':
            iteration=item['iteration'];total=item['total_iterations']
            if type(iteration) is not int or type(total) is not int or not 0<=iteration<=total or total<=0:raise ValueError('Progress invalid')
            loss=item.get('loss')
            if loss is not None and (type(loss) not in (int,float) or not math.isfinite(loss)):raise ValueError('Loss invalid')
            self.store.append(ident,progress=iteration/total,iteration=iteration,total_iterations=total,epoch=item.get('epoch'),loss=item.get('loss'))
        elif event=='checkpoint':
            path=self.store.artifact(ident,item['manifest']);checkpoint=await asyncio.to_thread(verify,path)
            meta=checkpoint['metadata'];spec=self.store.request(ident)
            if not isinstance(meta,dict) or any(meta.get(k)!=spec.get(k) for k in ('id','engine','dataset_sha256','profile_id','parameters')):raise ValueError('Checkpoint binding invalid')
            epoch=meta.get('epoch')
            if type(epoch) is not int or not 1<=epoch<=spec['parameters']['epochs']:raise ValueError('Checkpoint epoch invalid')
            self.store.append(ident,checkpoint=item['manifest'],epoch=epoch)
        elif event in ('paused','cancelled'):
            self.store.append(ident,status=event,pause_reason='inference' if event=='paused' else None)
        elif event=='completed':
            path=self.store.artifact(ident,item['manifest']);manifest=await asyncio.to_thread(verify,path)
            spec=self.store.request(ident)
            if any(manifest['metadata'].get(k)!=spec.get(k) for k in ('id','engine','dataset_sha256','profile_id','parameters')):raise ValueError('Artifact binding invalid')
            self.store.append(ident,status='checkpointing',completion_received=True,result_manifest=item['manifest'],error=None)
        elif event in ('failed','interrupted'):
            self.store.append(ident,status=event,error='Le pilote a interrompu cette tâche')
