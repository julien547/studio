"""Private RunPod service. One process, one inference at a time on the A6000.

Persistent results use content hashes + a verified commit record. SQLite is NOT
used on the network volume. No service secret: only OVH's public verification key.
"""
import base64
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import uuid
from fastapi import FastAPI,Depends,Header,HTTPException
from .auth import verify
from .contracts import validate_request
from .jobs import canonical


class Worker:
    def __init__(self,engines,root):
        self.engines=engines;self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.Lock();self.active=0;self.unsaved=0;self.draining=False;self.ready=False
        self.warmup_error=None
        self.pod_id=os.environ.get('RUNPOD_POD_ID')
        self.instance_id=str(uuid.uuid4())
        for directory in self.root.iterdir():
            if not directory.is_dir():continue
            try:
                manifest=json.loads((directory/'commit.json').read_text())
                content=(directory/(manifest['result_sha256']+'.json')).read_bytes()
                if hashlib.sha256(content).hexdigest()!=manifest['result_sha256']:raise ValueError()
            except Exception:self.unsaved+=1

    def warmup(self):
        from PIL import Image,ImageDraw
        try:
            import subprocess
            subprocess.run(['nvidia-smi','--query-gpu=name,memory.total','--format=csv,noheader'],check=True,capture_output=True,timeout=20)
            with tempfile.TemporaryDirectory(prefix='doemo-probe-',dir='/tmp') as tmp:
                image=Image.new('RGB',(640,360),'white');draw=ImageDraw.Draw(image)
                draw.rectangle((50,70,590,300),outline='black',width=4);draw.text((220,150),'DOEMO 321',fill='black')
                path=Path(tmp)/'probe.png';image.save(path)
                request={'image_path':str(path),'regions':[{'id':'test','bbox':[0,0,640,360]}]}
                for name in ('paddleocr','qwen','rtmdet'):self.engines.run(name,request)
            self.ready=True
        except Exception as error:
            self.warmup_error=type(error).__name__

    def health(self):
        stop_safe=False
        if os.environ.get('DOEMO_WORKER_EXCLUSIVE')=='1':
            try:
                import subprocess
                result=subprocess.run(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],
                                      capture_output=True,text=True,timeout=10,check=True)
                stop_safe=not result.stdout.strip()
            except Exception:pass
        with self.lock:return {'ready':self.ready,'active':self.active,'queued':0,'unsaved':self.unsaved,
                               'pod_id':self.pod_id,'worker_instance_id':self.instance_id,
                               'stop_safe':stop_safe,
                               'draining':self.draining,'warmup_error':self.warmup_error}

    def infer(self,job_id,request):
        if str(uuid.UUID(job_id))!=job_id:raise ValueError('Job ID invalide')
        request,data=validate_request(request);digest=hashlib.sha256(canonical(request).encode()).hexdigest()
        with self.lock:
            if not self.ready or self.draining or self.active or self.unsaved:raise RuntimeError('worker_unavailable')
            self.active=1
        try:
            directory=self.root/job_id
            commit=directory/'commit.json'
            if commit.exists():
                manifest=json.loads(commit.read_text())
                if manifest['request_sha256']!=digest:raise ValueError('Identifiant réutilisé pour une autre requête')
                result_bytes=(directory/(manifest['result_sha256']+'.json')).read_bytes()
                if hashlib.sha256(result_bytes).hexdigest()!=manifest['result_sha256']:raise ValueError('Résultat persistant corrompu')
                return json.loads(result_bytes)
            result={'schema':'doemo.ai.evidence/1','job_id':job_id,'source_sha256':request['source_sha256'],
                    'executed_on':{'pod_id':self.pod_id,'worker_instance_id':self.instance_id},
                    'image_sha256':request['image_sha256'],'page':request['page'],'status':'pending',
                    'coordinate_space':'input_image_pixels','width':request['width'],'height':request['height'],
                    'model_versions':request['model_versions'],'engines':{}}
            with tempfile.TemporaryDirectory(prefix='doemo-inference-',dir='/tmp') as tmp:
                image_path=Path(tmp)/'input.png';image_path.write_bytes(data)
                for name in request['engines']:
                    if self.engines.config[name]['version']!=request['model_versions'][name]:raise ValueError('Version du modèle différente de la requête')
                    output=self.engines.run(name,{'image_path':str(image_path),'regions':request['regions']})
                    result['engines'][name]=output
            with self.lock:self.unsaved=1
            directory.mkdir(exist_ok=True)
            encoded=canonical(result).encode();result_sha=hashlib.sha256(encoded).hexdigest()
            target=directory/(result_sha+'.json')
            # Closing and re-reading are deliberate: network-volume rename/fsync semantics vary.
            target.write_bytes(encoded)
            if hashlib.sha256(target.read_bytes()).hexdigest()!=result_sha:raise OSError('Persistent result verification failed')
            manifest={'request_sha256':digest,'result_sha256':result_sha}
            commit.write_text(canonical(manifest))
            if json.loads(commit.read_text())!=manifest:raise OSError('Persistent commit verification failed')
            with self.lock:self.unsaved=0
            return result
        finally:
            with self.lock:self.active=0
            # A save failure leaves unsaved=1. Automatic stop stays forbidden until reconciliation.


def create_worker(worker,public_key,*,warmup=True):
    @asynccontextmanager
    async def lifespan(app):
        if warmup:threading.Thread(target=worker.warmup,daemon=True).start()
        yield
    app=FastAPI(title='DOEMO private RunPod worker',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    from .limits import BodyLimit
    app.add_middleware(BodyLimit)
    def authenticated(authorization:str=Header(default='')):
        try:verify(public_key,authorization.removeprefix('Bearer '),'doemo-runpod','worker')
        except ValueError:raise HTTPException(401,'Unauthorized')
    @app.get('/health',dependencies=[Depends(authenticated)])
    def health():return worker.health()
    @app.get('/models',dependencies=[Depends(authenticated)])
    def models():return worker.engines.models()
    @app.post('/drain',dependencies=[Depends(authenticated)])
    def drain():
        with worker.lock:
            if worker.active or worker.unsaved:return {'drained':False}
            worker.draining=True;return {'drained':True}
    @app.post('/infer/{job_id}',dependencies=[Depends(authenticated)])
    def infer(job_id:str,request:dict):
        try:return worker.infer(job_id,request)
        except ValueError:raise HTTPException(422,'Invalid request or model configuration')
        except RuntimeError as error:
            if str(error)=='worker_unavailable':raise HTTPException(503,'Worker busy or not ready')
            raise HTTPException(500,'Inference failed; inspect local logs')
        except Exception:raise HTTPException(500,'Inference or persistence failed; inspect local logs')
    return app


def app_factory():
    from .engines import Engines
    engines=Engines(os.environ['DOEMO_MODELS_CONFIG'],os.environ['DOEMO_ENGINE_RUNNER'])
    worker=Worker(engines,os.environ.get('DOEMO_RUNPOD_RESULTS','/workspace/doemo-studio/exports/ai-jobs'))
    return create_worker(worker,Path(os.environ['DOEMO_OVH_PUBLIC_KEY']).read_bytes())
