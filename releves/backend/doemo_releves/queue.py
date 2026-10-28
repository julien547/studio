"""Durable SQLite work queue on the CPU host; lifecycle is a separate reconciler.

A separate worker claims one job atomically. Expired leases become interrupted and
require explicit retry. Raw engine outputs remain distinct from reviewed state.
"""
import json
import os
import time
import uuid
from pathlib import Path
from typing import Literal
import httpx
from fastapi import Depends
from pydantic import Field
from .models import Model
from .ai_contracts import normalise
from . import gpu


class AnalysisJob(Model):
    document_id: str
    page: int = Field(ge=1)
    engine: Literal['local','paddleocr','qwen','rtmdet']


def configured():
    return bool(os.environ.get('DOEMO_RUNPOD_ENDPOINT') and os.environ.get('DOEMO_RUNPOD_TOKEN'))


def endpoint():
    value=os.environ.get('DOEMO_RUNPOD_ENDPOINT','').rstrip('/')
    from urllib.parse import urlsplit
    p=urlsplit(value)
    if p.scheme!='https' or not p.netloc or p.username or p.query or p.fragment:
        raise ValueError('Endpoint RunPod HTTPS requis')
    return value


def remote_health():
    if not configured(): return {'status':'not_configured','engines':{},'automatic_start':False}
    try:
        r=httpx.get(endpoint()+'/health',headers={'Authorization':'Bearer '+os.environ['DOEMO_RUNPOD_TOKEN']},timeout=3,follow_redirects=False)
        r.raise_for_status();data=r.json()
        return {'status':'available','engines':{e: data.get('engines',{}).get(e,False) is True for e in ('qwen','paddleocr','rtmdet')},'automatic_start':False}
    except (httpx.HTTPError,ValueError,TypeError):
        return {'status':'unavailable','engines':{},'automatic_start':False}


def attach_queue(app,store,actor,get,doc):
    @app.get('/projects/ai-status')
    def ai_status(who=Depends(actor)):
        if gpu.enabled():return gpu.public_status(store)
        return remote_health()

    @app.post('/projects/{ident}/jobs')
    def submit(ident: str, data: AnalysisJob, who=Depends(actor)):
        get(ident,who);source,_=doc(ident,data.document_id,who,data.page)
        if source['role']!='survey': raise ValueError('Choisir un relevé')
        job=uuid.uuid4().hex
        with gpu.lifecycle_lock(store), store.connect() as c:
            c.execute('INSERT INTO jobs(id,project_id,actor,status,stage,payload) VALUES(?,?,?,?,?,?)',
                (job,ident,who.login,'queued','En attente',data.model_dump_json()))
            if data.engine!='local':
                c.execute('UPDATE gpu_control SET last_activity=?,next_poll=0 WHERE id=1',(time.time(),))
        return {'id':job,'status':'queued'}

    @app.post('/projects/{ident}/jobs/{job_id}/retry')
    def retry(ident: str,job_id: str,who=Depends(actor)):
        get(ident,who)
        with gpu.lifecycle_lock(store), store.connect() as c:
            row=c.execute('SELECT payload FROM jobs WHERE id=? AND project_id=?',(job_id,ident)).fetchone()
            if row and json.loads(row['payload']).get('training_preview'):raise ValueError('Relancer la comparaison depuis l’espace d’apprentissage')
            result=c.execute("UPDATE jobs SET status='queued',stage='Nouvelle tentative',error=NULL,retry_at=0,attempts=0,updated=CURRENT_TIMESTAMP WHERE id=? AND project_id=? AND status IN ('failed','waiting_gpu','retry_gpu','interrupted')",(job_id,ident))
            if not result.rowcount: raise ValueError('Ce traitement ne peut pas être relancé')
        return {'status':'queued'}


def claim(store):
    with gpu.lifecycle_lock(store), store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("UPDATE jobs SET status='interrupted',stage='Interrompu',error='Le worker a été interrompu ; relancer explicitement.' WHERE status='running' AND lease_until<?",(time.time(),))
        if gpu.enabled():
            # Recover GPU jobs after a CPU process crash. Reuse the same remote job ID.
            c.execute("UPDATE jobs SET status='retry_gpu',retry_at=? WHERE status='interrupted' AND json_extract(payload,'$.engine') IN ('qwen','paddleocr','rtmdet')",(time.time()+15,))
            control=c.execute('SELECT * FROM gpu_control WHERE id=1').fetchone()
            usable=control['pod_id']==os.environ.get('DOEMO_RUNPOD_POD_ID') and control['phase'] in ('ready','busy') and control['observed_at'] is not None and time.time()-control['observed_at']<60 and control['pending_action']!='stop'
            if usable:
                c.execute("UPDATE jobs SET status='queued' WHERE status IN ('waiting_gpu','retry_gpu') AND retry_at<=?",(time.time(),))
            else:
                c.execute("UPDATE jobs SET status='waiting_gpu',stage='Attente du GPU et des trois moteurs' WHERE status='queued' AND json_extract(payload,'$.engine') IN ('qwen','paddleocr','rtmdet')")
        row=c.execute("SELECT * FROM jobs WHERE status='queued' AND retry_at<=? ORDER BY created,id LIMIT 1",(time.time(),)).fetchone()
        if not row:return None
        c.execute("UPDATE jobs SET status='running',stage='Préparation',attempts=attempts+1,lease_until=?,updated=CURRENT_TIMESTAMP WHERE id=?",(time.time()+650,row['id']))
        return dict(row)


def process_one(store):
    job=claim(store)
    if not job:return False
    payload=json.loads(job['payload']);engine=payload['engine']
    def update(status,stage,result=None,error=None):
        with gpu.lifecycle_lock(store), store.connect() as c:
            c.execute('UPDATE jobs SET status=?,stage=?,result=?,error=?,updated=CURRENT_TIMESTAMP WHERE id=?',
                (status,stage,json.dumps(result) if result is not None else None,error,job['id']))
            if engine!='local':c.execute('UPDATE gpu_control SET last_activity=? WHERE id=1',(time.time(),))
    try:
        path=store.root/'documents'/payload['document_id']/f"page-{payload['page']}.png"
        if engine=='local':
            from .worker import run_job
            update('running','Reconnaissance OCR locale')
            result=run_job('recognition',{'image_path':str(path),'document_id':payload['document_id'],'page':payload['page'],'mode':'local','legend_box':None})
            result.update(observations=[],warnings=result['report'].get('warnings',[]))
        else:
            managed=gpu.enabled()
            control=gpu.state(store) if managed else None
            if not managed and remote_health()['status']!='available':
                update('waiting_gpu','GPU indisponible',error='Vérifier la configuration ou démarrer le Pod manuellement, puis relancer.')
                return True
            from PIL import Image
            with Image.open(path) as im: width,height=im.size
            context_data={}
            if payload.get('training_preview'):
                from .qwen_preview import check_job,encoded,digest,image_hash
                with store.connect() as c:check_job(c,payload)
                if image_hash(path)!=payload['input_sha256']:raise ValueError('Page modifiée depuis l’admission de la comparaison')
                context_data={'data':{'context':encoded(payload['qwen_context'])}}
            update('running','Analyse '+engine)
            url=control['gateway_url'] if managed else endpoint()
            with path.open('rb') as f:
                r=httpx.post(url+'/infer/'+engine,headers={'Authorization':'Bearer '+os.environ['DOEMO_RUNPOD_TOKEN'], 'X-Doemo-Job':job['id']},
                    files={'file':('page.png',f,'image/png')},timeout=540,follow_redirects=False,**context_data)
            r.raise_for_status()
            if len(r.content)>8*1024**2:raise ValueError('Réponse IA excessive')
            response=r.json()
            if payload.get('training_preview'):
                proof=response.get('reference_context',{})
                if not isinstance(proof,dict) or proof.get('sha256')!=digest(payload['qwen_context']) or proof.get('schema')!=payload['qwen_context']['schema'] or response.get('input_sha256')!=payload['input_sha256']:
                    update('failed','Comparaison non vérifiée',error='Le gateway ne confirme pas la page et le référentiel attendus. Faire vérifier sa version par la session de déploiement.')
                    return True
            if response.get('width')!=width or response.get('height')!=height:
                raise ValueError('Le moteur doit retourner les coordonnées dans l’image transmise')
            result=normalise(engine,response['data'],payload['document_id'],payload['page'],width,height)
            result['raw']=response
        update('completed','Résultat prêt à vérifier',result)
    except (httpx.HTTPError,KeyError) as exc:
        if gpu.enabled() and engine!='local':
            # A training checkpoint is not a failed inference attempt. Keep the
            # same request until the compute slot is released, without burning
            # the five transport retries or launching a duplicate GPU inference.
            if isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code==409:
                try:preempting=exc.response.json().get('detail',{}).get('code')=='training_preempting'
                except (ValueError,AttributeError):preempting=False
                if preempting:
                    update('retry_gpu','Attente du checkpoint d’entraînement')
                    with gpu.lifecycle_lock(store),store.connect() as c:
                        c.execute('UPDATE jobs SET attempts=max(0,attempts-1),retry_at=? WHERE id=?',(time.time()+3,job['id']))
                    return True
            if job['attempts']>=4:
                update('failed','Échec après cinq tentatives',error='Le GPU ou le moteur reste indisponible. Vérifier le journal puis relancer manuellement.')
                return True
            update('retry_gpu','GPU temporairement indisponible',error='Reprise automatique avec le même identifiant, sans écraser les résultats.')
            with gpu.lifecycle_lock(store), store.connect() as c:
                c.execute('UPDATE jobs SET retry_at=? WHERE id=?',(time.time()+min(300,15*2**min(job['attempts'],4)),job['id']))
                c.execute('UPDATE gpu_control SET next_poll=0 WHERE id=1')
        else:update('failed','Échec',error='Analyse interrompue ou service indisponible.')
    except Exception:
        # Do not echo remote URLs, headers, model exception details or credentials.
        update('failed','Échec',error='Analyse interrompue ou réponse invalide. Vérifier le service puis relancer.')
    return True


def main():
    import argparse
    from .store import Store
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    store=Store(os.environ.get('DOEMO_RELEVES_DATA','/var/lib/doemo-studio/releves'))
    while True:
        worked=process_one(store)
        if args.once:return
        if not worked:time.sleep(2)

if __name__=='__main__':main()
