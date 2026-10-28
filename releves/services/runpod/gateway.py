"""Authenticated, persistent GPU service; launch exactly one uvicorn worker.

Provider RUNPOD_API_KEY is never needed here. The separate gateway token only
permits inference, accepted training jobs, readiness and quiescence, never provider administration.
"""
import asyncio
import contextlib
import hashlib
import hmac
import json
import os
import re
import shutil
import signal
import tempfile
import time
import uuid
from pathlib import Path
from fastapi import FastAPI,Header,HTTPException,UploadFile,Depends,Form
from PIL import Image
from compute import exclusive
from training_service import Manager
import qwen_prompt

lock=asyncio.Lock()
ENGINES={'qwen':'/opt/doemo-qwen-venv/bin/python','paddleocr':'/opt/doemo-ocr-venv/bin/python','rtmdet':'/opt/doemo-rtmdet-venv/bin/python'}
ADAPTER=Path(__file__).with_name('infer.py')
PROBE=Path(__file__).with_name('readiness.py')
BOOT_ID=uuid.uuid4().hex
status={'ready':False,'restoring':True,'engines':{e:False for e in ENGINES},'public_error':None}
draining=False
last_activity=time.monotonic()
training=None
training_admissions=0


def persistent_root():return Path(os.environ.get('DOEMO_PERSISTENT_ROOT','/workspace/doemo-studio'))


def write_json(path,data):
    # No chmod or atomic rename on FUSE. Completion metadata is written LAST.
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False))


def engine_env():
    env={k:v for k,v in os.environ.items() if k!='RUNPOD_API_KEY'}
    return dict(env,UV_CACHE_DIR='/tmp/doemo-uv-cache',PIP_CACHE_DIR='/tmp/doemo-pip-cache',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')


async def execute(python,script,args,log,timeout):
    with exclusive(), log.open('wb') as output:
        proc=await asyncio.create_subprocess_exec(python,str(script),*map(str,args),stdout=output,stderr=output,env=engine_env(),start_new_session=True)
        try:await asyncio.wait_for(proc.wait(),timeout=timeout)
        except (asyncio.TimeoutError,asyncio.CancelledError):
            with contextlib.suppress(ProcessLookupError):os.killpg(proc.pid,signal.SIGKILL)
            await proc.wait();raise
    return proc.returncode


async def warm_models():
    global last_activity
    async with lock:
        root=persistent_root();logs=root/'logs'/BOOT_ID;logs.mkdir(parents=True,exist_ok=True)
        # A process from a previous container cannot still be running in this boot.
        for record in (root/'jobs').glob('*/metadata.json'):
            try:
                data=json.loads(record.read_text())
                if data.get('status')=='running':data['status']='interrupted';write_json(record,data)
            except (ValueError,OSError):pass
        try:
            for engine,python in ENGINES.items():
                if not Path(python).is_file():raise ValueError('Environment absent')
                code=await execute(python,PROBE,[engine],logs/(engine+'-readiness.log'),480)
                status['engines'][engine]=code==0
                if code:raise ValueError('Model probe failed')
            status['ready']=True
        except Exception:
            status['public_error']='Restauration ou chargement des moteurs incomplet. Consulter les journaux persistants du Pod.'
        finally:
            status['restoring']=False;last_activity=time.monotonic()
            write_json(root/'runtime'/'readiness.json',dict(status,boot_id=BOOT_ID))


@contextlib.asynccontextmanager
async def lifespan(app):
    global training
    # fcntl is only used in /tmp, never on geesefs. Reject multiple gateway processes.
    import fcntl
    handle=open(os.environ.get('DOEMO_GATEWAY_LOCK','/tmp/doemo-gateway.lock'),'a')
    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    def activity():
        global last_activity
        last_activity=time.monotonic()
    training=Manager(persistent_root(),lock,lambda:status['ready'],lambda:draining,activity,engine_env)
    await training.initialize()
    task=asyncio.create_task(warm_models())
    trainer=asyncio.create_task(training.loop())
    try:yield
    finally:
        task.cancel()
        trainer.cancel()
        with contextlib.suppress(asyncio.CancelledError):await trainer
        with contextlib.suppress(asyncio.CancelledError):await task
        handle.close()


app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)


def authorize(authorization:str=Header(default='')):
    token=os.environ.get('DOEMO_RUNPOD_TOKEN','')
    if len(token)<32 or not hmac.compare_digest(authorization,'Bearer '+token):raise HTTPException(401,'Authentification requise')


@app.get('/health',dependencies=[Depends(authorize)])
async def health():
    return dict(status,boot_id=BOOT_ID,busy=lock.locked() or bool(training_admissions),active_jobs=int(lock.locked())+training_admissions,draining=draining,
                training_pending=training.store.pending() if training else 0,
                idle_seconds=max(0,time.monotonic()-last_activity),model_inference_verified=status['ready'],automatic_start=False)


@app.post('/quiesce',dependencies=[Depends(authorize)])
async def quiesce():
    global draining
    # No await between testing the lock and setting the admission flag.
    if lock.locked() or training_admissions or status['restoring'] or (training and training.store.pending()):return {'quiesced':False,'boot_id':BOOT_ID}
    draining=True
    return {'quiesced':True,'boot_id':BOOT_ID}


@app.post('/resume',dependencies=[Depends(authorize)])
async def resume():
    global draining
    draining=False
    return {'accepting':True,'boot_id':BOOT_ID}


@app.get('/jobs/{job_id}',dependencies=[Depends(authorize)])
async def job_status(job_id:str):
    if not re.fullmatch('[a-f0-9]{32}',job_id):raise HTTPException(422,'Identifiant invalide')
    path=persistent_root()/'jobs'/job_id/'metadata.json'
    if not path.exists():raise HTTPException(404,'Travail absent')
    return json.loads(path.read_text())


@app.post('/infer/{engine}',dependencies=[Depends(authorize)])
async def infer(engine:str,file:UploadFile,x_doemo_job:str=Header(default=''),context:str=Form(default='')):
    global last_activity
    if engine not in ENGINES:raise HTTPException(404,'Moteur inconnu')
    reference=None
    if context:
        if engine!='qwen':raise HTTPException(422,'Contexte réservé à Qwen')
        try:reference=qwen_prompt.parse(context)
        except (ValueError,TypeError):raise HTTPException(422,'Contexte de référentiel invalide')
    if not status['ready']:raise HTTPException(503,'Les trois moteurs ne sont pas prêts')
    if training:
        await training.infer_priority()
        if training.active:raise HTTPException(409,{'code':'training_preempting','message':'Checkpoint en cours avant priorité à l’inférence'})
    if draining or lock.locked():raise HTTPException(409,'GPU occupé ou en arrêt contrôlé')
    job_id=x_doemo_job or uuid.uuid4().hex
    if not re.fullmatch('[a-f0-9]{32}',job_id):raise HTTPException(422,'Identifiant invalide')
    async with lock:
        last_activity=time.monotonic()
        job=persistent_root()/'jobs'/job_id;job.mkdir(parents=True,exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix='doemo-infer-',dir='/tmp') as tmp:
                source=Path(tmp)/'source.png';count=0;digest=hashlib.sha256()
                with source.open('wb') as out:
                    while chunk:=await file.read(1024**2):
                        count+=len(chunk)
                        if count>64*1024**2:raise HTTPException(413,'Image trop volumineuse')
                        digest.update(chunk);out.write(chunk)
                try:
                    with Image.open(source) as im:
                        if im.format!='PNG' or im.width*im.height>40_000_000:raise ValueError()
                        width,height=im.size;im.verify()
                except Exception:raise HTTPException(422,'PNG invalide')
                metadata={'id':job_id,'engine':engine,'input_sha256':digest.hexdigest(),'status':'running','boot_id':BOOT_ID}
                metadata['context_sha256']=qwen_prompt.digest(reference) if reference is not None else None
                if (job/'metadata.json').exists():
                    try:prior=json.loads((job/'metadata.json').read_text())
                    except ValueError:raise HTTPException(409,'Métadonnées persistantes à contrôler')
                    if prior.get('input_sha256')!=metadata['input_sha256'] or prior.get('engine')!=engine:
                        raise HTTPException(409,'Cet identifiant appartient à une autre analyse')
                    if prior.get('context_sha256')!=metadata['context_sha256']:
                        raise HTTPException(409,'Cet identifiant appartient à un autre contexte Qwen')
                    if prior.get('status')=='completed':return json.loads((job/'response.json').read_text())
                shutil.copyfile(source,job/'input.png');write_json(job/'metadata.json',metadata)
                result=Path(tmp)/'result.json'
                arguments=[engine,source,result]
                if reference is not None:
                    context_path=Path(tmp)/'reference.json';context_path.write_text(qwen_prompt.encoded(reference))
                    shutil.copyfile(context_path,job/'reference.json')
                    arguments.append(context_path)
                try:
                    code=await execute(ENGINES[engine],ADAPTER,arguments,job/'engine.log',480)
                    if code or not result.exists() or result.stat().st_size>8*1024**2:raise ValueError('Invalid output')
                    response={'width':width,'height':height,'engine':engine,'data':json.loads(result.read_text())}
                    if reference is not None:response.update(reference_context=qwen_prompt.proof(reference),input_sha256=metadata['input_sha256'])
                    shutil.copyfile(result,job/'result.json');write_json(job/'response.json',response)
                    metadata['status']='completed';write_json(job/'metadata.json',metadata)
                    return response
                except BaseException as exc:
                    metadata['status']='interrupted' if isinstance(exc,asyncio.CancelledError) else 'failed'
                    write_json(job/'metadata.json',metadata)
                    if isinstance(exc,asyncio.CancelledError):raise
                    raise HTTPException(502,'Moteur interrompu ; journaux conservés sur le volume persistant')
        finally:last_activity=time.monotonic()


@app.get('/training/capabilities',dependencies=[Depends(authorize)])
async def training_capabilities():
    engines={engine:{'training':bool(training and training.profile_for(engine)),
                     'profile_id':training.profile_for(engine)['public']['id'] if training and training.profile_for(engine) else None} for engine in ('rtmdet','paddleocr')}
    return {'engine':'rtmdet',**engines['rtmdet'],'engines':engines}


@app.post('/training/jobs/{ident}',dependencies=[Depends(authorize)])
async def training_submit(ident:str,file:UploadFile,spec:str=Form(...)):
    global training_admissions,last_activity
    if not training or not status['ready'] or draining:raise HTTPException(503,'Admission entraînement indisponible')
    if len(spec)>16384:raise HTTPException(413,'Demande excessive')
    try:
        request=json.loads(spec);profile=training.profile_for(request['engine'])
        if not profile:raise ValueError()
    except (ValueError,KeyError,TypeError):raise HTTPException(422,'Profil du moteur indisponible')
    training_admissions+=1
    last_activity=time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='doemo-training-upload-',dir='/tmp') as tmp:
            archive=Path(tmp)/'dataset.zip';count=0
            with archive.open('wb') as output:
                while chunk:=await file.read(1024**2):
                    count+=len(chunk)
                    if count>256*1024**2:raise HTTPException(413,'Dataset excessif')
                    output.write(chunk)
            # The admission counter prevents quiescence during the verified copy;
            # accepting another queued job must not wait for a long GPU epoch.
            if draining:raise HTTPException(409,'Arrêt contrôlé en cours')
            return await asyncio.to_thread(training.store.admit,ident,request,archive,profile)
    except (ValueError,KeyError,TypeError,OSError):raise HTTPException(422,'Demande, dataset ou profil incompatible')
    finally:
        training_admissions-=1
        last_activity=time.monotonic()


@app.get('/training/jobs/{ident}',dependencies=[Depends(authorize)])
async def training_status(ident:str):
    if not training:raise HTTPException(503,'Service en préparation')
    try:value=await asyncio.to_thread(training.store.public,ident)
    except (ValueError,OSError,KeyError):raise HTTPException(409,'État persistant à contrôler')
    if value is None:raise HTTPException(404,'Tâche absente')
    return value


@app.post('/training/jobs/{ident}/{action}',dependencies=[Depends(authorize)])
async def training_control(ident:str,action:str):
    if not training:raise HTTPException(503,'Service en préparation')
    if action not in ('pause','resume','cancel'):raise HTTPException(404,'Action inconnue')
    try:return await training.control(ident,action)
    except LookupError:raise HTTPException(404,'Tâche absente')
    except (ValueError,OSError,KeyError):raise HTTPException(409,'Transition refusée ; contrôler le checkpoint et la disponibilité')
