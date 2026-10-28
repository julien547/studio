"""Durable SQLite work queue on the CPU host. No paid GPU lifecycle calls.

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
        return remote_health()

    @app.post('/projects/{ident}/jobs')
    def submit(ident: str, data: AnalysisJob, who=Depends(actor)):
        get(ident,who);source,_=doc(ident,data.document_id,who,data.page)
        if source['role']!='survey': raise ValueError('Choisir un relevé')
        job=uuid.uuid4().hex
        with store.connect() as c:
            c.execute('INSERT INTO jobs(id,project_id,actor,status,stage,payload) VALUES(?,?,?,?,?,?)',
                (job,ident,who.login,'queued','En attente',data.model_dump_json()))
        return {'id':job,'status':'queued'}

    @app.post('/projects/{ident}/jobs/{job_id}/retry')
    def retry(ident: str,job_id: str,who=Depends(actor)):
        get(ident,who)
        with store.connect() as c:
            result=c.execute("UPDATE jobs SET status='queued',stage='Nouvelle tentative',error=NULL,updated=CURRENT_TIMESTAMP WHERE id=? AND project_id=? AND status IN ('failed','waiting_gpu','interrupted')",(job_id,ident))
            if not result.rowcount: raise ValueError('Ce traitement ne peut pas être relancé')
        return {'status':'queued'}


def claim(store):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("UPDATE jobs SET status='interrupted',stage='Interrompu',error='Le worker a été interrompu ; relancer explicitement.' WHERE status='running' AND lease_until<?",(time.time(),))
        row=c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created,id LIMIT 1").fetchone()
        if not row:return None
        c.execute("UPDATE jobs SET status='running',stage='Préparation',attempts=attempts+1,lease_until=?,updated=CURRENT_TIMESTAMP WHERE id=?",(time.time()+650,row['id']))
        return dict(row)


def process_one(store):
    job=claim(store)
    if not job:return False
    payload=json.loads(job['payload']);engine=payload['engine']
    def update(status,stage,result=None,error=None):
        with store.connect() as c:
            c.execute('UPDATE jobs SET status=?,stage=?,result=?,error=?,updated=CURRENT_TIMESTAMP WHERE id=?',
                (status,stage,json.dumps(result) if result is not None else None,error,job['id']))
    try:
        path=store.root/'documents'/payload['document_id']/f"page-{payload['page']}.png"
        if engine=='local':
            from .worker import run_job
            update('running','Reconnaissance OCR locale')
            result=run_job('recognition',{'image_path':str(path),'document_id':payload['document_id'],'page':payload['page'],'mode':'local','legend_box':None})
            result.update(observations=[],warnings=result['report'].get('warnings',[]))
        else:
            if remote_health()['status']!='available':
                update('waiting_gpu','GPU indisponible',error='Vérifier la configuration ou démarrer le Pod manuellement, puis relancer.')
                return True
            from PIL import Image
            with Image.open(path) as im: width,height=im.size
            update('running','Analyse '+engine)
            with path.open('rb') as f:
                r=httpx.post(endpoint()+'/infer/'+engine,headers={'Authorization':'Bearer '+os.environ['DOEMO_RUNPOD_TOKEN']},
                    files={'file':('page.png',f,'image/png')},timeout=540,follow_redirects=False)
            r.raise_for_status()
            if len(r.content)>8*1024**2:raise ValueError('Réponse IA excessive')
            response=r.json()
            if response.get('width')!=width or response.get('height')!=height:
                raise ValueError('Le moteur doit retourner les coordonnées dans l’image transmise')
            result=normalise(engine,response['data'],payload['document_id'],payload['page'],width,height)
            result['raw']=response
        update('completed','Résultat prêt à vérifier',result)
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
