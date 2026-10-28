"""OVH private asynchronous API + RunPod client. Single worker process required.

Expose to the existing authenticated project backend, not to browsers. The backend
must authorize ownership of each project before signing a service request.
"""
from contextlib import asynccontextmanager
import os
from pathlib import Path
import threading
import time
import httpx
from fastapi import Depends,FastAPI,Header,HTTPException
from .auth import issue,verify
from .contracts import AnalysisRequest,validate_request
from .jobs import JobStore
from .runpod import RunPod,IdleController


class RemoteWorker:
    def __init__(self,private_key,port=8009):self.private_key,self.port=private_key,port
    def call(self,pod,method,path,body=None,timeout=30):
        token=issue(self.private_key,'doemo-runpod','worker')
        with httpx.Client(timeout=timeout,follow_redirects=False) as client:
            response=client.request(method,RunPod.worker_url(pod,self.port)+path,
                headers={'Authorization':'Bearer '+token},json=body)
            response.raise_for_status();return response.json()
    def health(self,pod):return self.call(pod,'GET','/health')
    def drain(self,pod):return self.call(pod,'POST','/drain')['drained']
    def wait_ready(self,pod,stop,timeout=1800):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline and not stop.is_set():
            try:
                state=self.health(pod)
                if state.get('pod_id')!=pod['id']:
                    raise RuntimeError('Le worker ne correspond pas au Pod actif découvert')
                if state.get('ready') and not state.get('draining'):return
                if state.get('warmup_error'):raise RuntimeError('Tests fonctionnels RunPod en échec')
            except httpx.HTTPError:pass
            stop.wait(5)
        raise TimeoutError('GPU ou modèles non prêts')
    def infer(self,pod,job):return self.call(pod,'POST','/infer/'+job['id'],job['request'],timeout=2800)


class Orchestrator:
    def __init__(self,store,runpod,worker,autostop=False):
        self.store,self.runpod,self.worker=store,runpod,worker
        self.gate=threading.RLock();self.stop=threading.Event();self.autostop=autostop
        self.idle=IdleController(store,runpod,worker,self.gate);self.last_control_error=None

    def process_once(self):
        with self.gate:job=self.store.claim()
        if job is None:return False
        try:
            with self.gate:pod=self.runpod.ensure_started()
            self.store.stage(job['id'],'gpu_requested',10)
            self.worker.wait_ready(pod,self.stop)
            self.store.stage(job['id'],'functional_models_ready',25)
            self.store.stage(job['id'],'inference_running',40,{'models':job['request']['model_versions']})
            result=self.worker.infer(pod,job)
            if result.get('job_id')!=job['id'] or result.get('source_sha256')!=job['request']['source_sha256'] or result.get('image_sha256')!=job['request']['image_sha256']:raise ValueError('Résultat pour une autre source')
            self.store.stage(job['id'],'inference_received',80)
            self.store.stage(job['id'],'saving',90)
            self.store.finish(job['id'],result)
        except Exception as error:
            # No raw HTTP payload, credentials or customer content in public errors.
            self.store.fail(job['id'],type(error).__name__+': consulter les journaux backend')
        return True

    def loop(self):
        while not self.stop.is_set():
            if self.process_once():continue
            if self.autostop:
                try:self.idle.tick()
                except Exception as error:self.last_control_error=type(error).__name__
            self.stop.wait(2)


def create_app(orchestrator,public_key,*,start_worker=True):
    @asynccontextmanager
    async def lifespan(app):
        orchestrator.store.recover()
        if start_worker:threading.Thread(target=orchestrator.loop,daemon=True).start()
        yield
        orchestrator.stop.set()
    app=FastAPI(title='DOEMO architectural orchestration',docs_url=None,redoc_url=None,lifespan=lifespan)
    from .limits import BodyLimit
    app.add_middleware(BodyLimit)
    def authenticated(authorization:str=Header(default='')):
        try:verify(public_key,authorization.removeprefix('Bearer '),'doemo-orchestrator','jobs')
        except ValueError:raise HTTPException(401,'Unauthorized')
    @app.get('/health',dependencies=[Depends(authenticated)])
    def health():return {'ready':True,'role':'ovh-orchestration','runpod_inference_verified':False,
                         'control_error':orchestrator.last_control_error}
    @app.get('/models',dependencies=[Depends(authenticated)])
    def models():
        try:return orchestrator.worker.call(orchestrator.runpod.discover(),'GET','/models')
        except Exception:raise HTTPException(503,'RunPod inaccessible ou non configuré')
    @app.post('/jobs/analyze-floorplan',status_code=202,dependencies=[Depends(authenticated)])
    def analyze(request:AnalysisRequest,idempotency_key:str=Header(min_length=1,max_length=128)):
        try:
            checked,_=validate_request(request.model_dump())
            with orchestrator.gate:job_id=orchestrator.store.submit('analyze-floorplan',checked,idempotency_key)
            return {'id':job_id,'status':orchestrator.store.get(job_id)['status']}
        except ValueError as error:raise HTTPException(422,str(error))
    @app.post('/jobs/detect-walls',dependencies=[Depends(authenticated)])
    def detect_walls():
        # Explicit unavailability is safer than redirecting architectural work into generic RTMDet.
        raise HTTPException(503,{'code':'architectural_segmentation_not_qualified',
            'module':'doemo-walls','next_step':'Qualifier un modèle et ses droits commerciaux ; le moteur géométrique reste utilisable localement.'})
    @app.get('/jobs/{job_id}',dependencies=[Depends(authenticated)])
    def job(job_id:str):
        try:result=orchestrator.store.get(job_id);result.pop('result');return result
        except KeyError:raise HTTPException(404,'Job not found')
    @app.get('/jobs/{job_id}/results',dependencies=[Depends(authenticated)])
    def results(job_id:str):
        try:result=orchestrator.store.get(job_id)
        except KeyError:raise HTTPException(404,'Job not found')
        if result['status']!='completed':raise HTTPException(409,'Results not committed')
        return result['result']
    return app


def app_factory():
    store=JobStore(os.environ.get('DOEMO_JOBS_DB','/var/lib/doemo/jobs.sqlite3'))
    runpod=RunPod(os.environ['RUNPOD_API_KEY'],os.environ['RUNPOD_NETWORK_VOLUME_ID'],os.environ.get('DOEMO_SERVICE_ID','DOEMO-STUDIO-IA'))
    remote=RemoteWorker(Path(os.environ['DOEMO_OVH_PRIVATE_KEY']).read_bytes(),int(os.environ.get('DOEMO_WORKER_PORT','8009')))
    orchestrator=Orchestrator(store,runpod,remote,autostop=os.environ.get('DOEMO_AUTOSTOP')=='1')
    return create_app(orchestrator,Path(os.environ['DOEMO_OVH_PUBLIC_KEY']).read_bytes())
