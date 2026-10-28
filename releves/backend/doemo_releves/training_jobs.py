"""OVH training queue. Provider credentials never leave the CPU backend.

A single nonblocking file lock serializes reconciliation, not web requests.
Remote submission is idempotent; uncertain responses are reconciled by job ID.
All nonterminal training jobs participate in the lifecycle stop guard.
"""
import contextlib
import fcntl
import hashlib
import io
import json
import math
import os
import re
import time
import uuid
from pathlib import Path
import httpx
from . import gpu
from .store import Conflict

ACTIVE=('queued','waiting_gpu','dispatching','running','checkpointing','paused','cancel_requested','interrupted')
TERMINAL=('completed','failed','cancelled')
HEX=re.compile(r'^[a-f0-9]{64}$')


def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(encoded(value).encode()).hexdigest()


def profile():
    """Operator-installed acceptance record, never supplied by a browser."""
    path=os.environ.get('DOEMO_TRAINING_PROFILE','')
    if not path:return None
    try:
        p=Path(path)
        if p.stat().st_size>64*1024:return None
        value=json.loads(p.read_text())
        keys=('driver_sha256','runtime_sha256','config_sha256','weights_sha256')
        if value.get('engine')!='rtmdet' or any(not HEX.fullmatch(value.get(k,'')) for k in keys):return None
        evidence=value.get('acceptance',{})
        if any(evidence.get(k) is not True for k in ('training_completed','resume_verified','inference_preemption_verified','cancel_verified')):return None
        if not HEX.fullmatch(evidence.get('report_sha256','')):return None
        clean={k:value[k] for k in keys};clean.update(engine='rtmdet',driver='rtmdet.training/1',acceptance={k:evidence[k] for k in ('training_completed','resume_verified','inference_preemption_verified','cancel_verified','report_sha256')})
        clean['id']=digest(clean)
        return clean
    except (OSError,ValueError,TypeError,AttributeError):return None


def capability(engine):
    p=profile()
    enabled=p is not None and engine=='rtmdet' and gpu.configured()
    return {'training':enabled,'register_weights':engine=='rtmdet','driver_status':'accepted_profile' if enabled else 'async_adapter_acceptance_required' if engine=='rtmdet' else 'not_implemented',
            'reason':('' if enabled else 'Entraînement non disponible : profil RTMDet recetté et orchestration OVH requis.' if engine=='rtmdet' else 'Entraînement non disponible : pilote compatible non raccordé.'),
            'profile_id':p['id'] if enabled else None,'batch_size_max':4,'learning_rate_max':.001}


def decode(row):
    value=dict(row)
    for key in ('parameters','result','profile'):
        value[key]=json.loads(value[key]) if value.get(key) else None
    return value


def record(c,ident):
    row=c.execute('SELECT * FROM training_runs WHERE id=?',(ident,)).fetchone()
    if not row:raise LookupError()
    return decode(row)


def event(c,actor,action,ident,detail=None):
    c.execute('INSERT INTO training_audit(actor,action,entity,detail) VALUES(?,?,?,?)',(actor,action,ident,encoded(detail or {})))


def launch(store,actor,data):
    from .training import row_dataset
    params={'epochs':data.epochs,'batch_size':data.batch_size,'learning_rate':data.learning_rate}
    if not data.confirmed:raise ValueError('Autorisation explicite du coût GPU requise')
    if not data.request_key:raise ValueError('Identifiant de demande requis')
    fingerprint=digest(dict(engine=data.engine,dataset_id=data.dataset_id,parameters=params))
    with gpu.lifecycle_lock(store),store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM training_runs WHERE author=? AND request_key=?',(actor,data.request_key)).fetchone()
        if old:
            if old['request_sha256']!=fingerprint:raise Conflict('Identifiant déjà utilisé pour une autre demande')
            return decode(old)
        dataset=row_dataset(c,data.dataset_id)
        if dataset['engine']!=data.engine:raise ValueError('Dataset incompatible')
        cap=capability(data.engine)
        if not cap['training']:
            from fastapi import HTTPException
            raise HTTPException(503,cap['reason'])
        if data.batch_size>4 or data.learning_rate>.001:raise ValueError('Paramètres hors limites du pilote RTMDet')
        examples=dataset['snapshot']['examples']
        if any(not any(e['split']==split for e in examples) for split in ('train','validation','test')):raise ValueError('Lots indépendants train, validation et test requis')
        train={a['category'] for e in examples if e['split']=='train' for a in e['data']['labels']}
        if train!={a['category'] for e in examples for a in e['data']['labels']}:raise ValueError('Chaque classe doit être représentée en entraînement')
        p=profile();ident=uuid.uuid4().hex
        c.execute("INSERT INTO training_runs(id,engine,dataset_id,parameters,status,author,request_key,request_sha256,profile,pod_id,updated) VALUES(?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                  (ident,data.engine,data.dataset_id,encoded(params),'queued',actor,data.request_key,fingerprint,encoded(p),os.environ['DOEMO_RUNPOD_POD_ID']))
        c.execute('UPDATE gpu_control SET last_activity=?,next_poll=0 WHERE id=1',(time.time(),))
        event(c,actor,'training.queued',ident,{'dataset_sha256':dataset['sha256'],'profile_id':p['id']})
        return record(c,ident)


def cancel(store,actor,ident):
    with gpu.lifecycle_lock(store),store.connect() as c:
        c.execute('BEGIN IMMEDIATE');job=record(c,ident)
        if job['status'] in TERMINAL:raise Conflict('Tâche déjà terminée')
        # Once a network submission was attempted, a missing reply is not proof
        # that nothing runs. Remote acknowledgement is mandatory in that case.
        status='cancel_requested' if job['dispatched'] else 'cancelled'
        c.execute('UPDATE training_runs SET status=?,cancel_requested=1,retry_at=0,updated=CURRENT_TIMESTAMP WHERE id=?',(status,ident))
        event(c,actor,'training.cancel_requested',ident);return record(c,ident)


def retry(store,actor,ident,confirmed):
    if not confirmed:raise ValueError('Confirmer la reprise GPU')
    with gpu.lifecycle_lock(store),store.connect() as c:
        c.execute('BEGIN IMMEDIATE');job=record(c,ident)
        if job['status']!='interrupted':raise Conflict('Seules les tâches interrompues peuvent reprendre depuis leur checkpoint')
        if job['pod_id']!=os.environ.get('DOEMO_RUNPOD_POD_ID'):raise Conflict('Le Pod configuré a changé : reprise à contrôler')
        from .training import row_dataset
        row_dataset(c,job['dataset_id'])
        if job['profile']!=profile():raise Conflict('Profil d’entraînement modifié')
        c.execute("UPDATE training_runs SET resume_requested=1,cancel_requested=0,retry_at=0,updated=CURRENT_TIMESTAMP WHERE id=?",(ident,))
        event(c,actor,'training.resume_requested',ident);return record(c,ident)


class Transport:
    def __init__(self,url):self.url=url
    def call(self,path,body=None):
        r=httpx.request('GET' if body is None else 'POST',self.url+path,json=body,
            headers={'Authorization':'Bearer '+os.environ['DOEMO_RUNPOD_TOKEN']},timeout=30,follow_redirects=False)
        if r.status_code==404:return None
        r.raise_for_status()
        if len(r.content)>2*1024**2:raise ValueError('Réponse excessive')
        return r.json()
    def status(self,ident):return self.call('/training/jobs/'+ident)
    def control(self,ident,action):return self.call('/training/jobs/'+ident+'/'+action,{})
    def submit(self,job,snapshot,bundle):
        spec={'id':job['id'],'engine':job['engine'],'profile_id':job['profile']['id'],'parameters':job['parameters'],
              'dataset_id':job['dataset_id'],'dataset_sha256':digest(snapshot),'archive_sha256':hashlib.sha256(bundle).hexdigest()}
        r=httpx.post(self.url+'/training/jobs/'+job['id'],headers={'Authorization':'Bearer '+os.environ['DOEMO_RUNPOD_TOKEN']},
            data={'spec':encoded(spec)},files={'file':('dataset.zip',io.BytesIO(bundle),'application/zip')},timeout=180,follow_redirects=False)
        r.raise_for_status()
        if len(r.content)>2*1024**2:raise ValueError('Réponse excessive')
        return r.json()


def valid_result(job,dataset,response):
    manifest=response.get('result')
    if not isinstance(manifest,dict) or manifest.get('schema')!='doemo.artifacts/1':raise ValueError('Manifeste final absent')
    meta=manifest.get('metadata',{});files=manifest.get('files',[])
    if not isinstance(meta,dict):raise ValueError('Métadonnées invalides')
    if meta.get('id')!=job['id'] or meta.get('engine')!=job['engine'] or meta.get('dataset_sha256')!=dataset['sha256'] or meta.get('profile_id')!=job['profile']['id'] or meta.get('parameters')!=job['parameters']:raise ValueError('Résultat incompatible avec la demande')
    if response.get('artifacts_verified') is not True or not isinstance(meta.get('metrics'),dict) or not meta['metrics'] or meta.get('status')!='completed':raise ValueError('Artefacts ou métriques non vérifiés')
    expected={'weights.pth','model_config.py','classes.json','metrics.json'}
    if not isinstance(files,list) or any(not isinstance(f,dict) for f in files) or {f.get('name') for f in files}!=expected or len(files)!=len(expected):raise ValueError('Artefacts manquants')
    for f in files:
        if not HEX.fullmatch(f.get('sha256','')) or type(f.get('bytes')) is not int or f['bytes']<=0:raise ValueError('Empreinte ou taille invalide')
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in meta['metrics'].values()):raise ValueError('Métriques non finies')
    return manifest


def tick(store,transport_factory=Transport):
    # POSIX OVH only. A worker crash releases this lock immediately.
    with (store.root/'training-worker.lock').open('a') as handle:
        try:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return False
        return _tick(store,transport_factory)


def _tick(store,transport_factory):
    from .training import row_dataset,dataset_bundle
    now=time.time()
    with store.connect() as c:
        row=c.execute("SELECT * FROM training_runs WHERE status NOT IN ('completed','failed','cancelled') AND retry_at<=? ORDER BY dispatched DESC,created,id LIMIT 1",(now,)).fetchone()
        if not row:return False
        job=decode(row)
    def update(status,**fields):
        with gpu.lifecycle_lock(store),store.connect() as c:
            current=record(c,job['id'])
            # A cancellation made during an HTTP call must not be overwritten.
            if current['cancel_requested'] and status not in TERMINAL:status='cancel_requested'
            values={'status':status,**fields,'updated':time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime())}
            c.execute('UPDATE training_runs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),job['id']))
            if status!=current['status']:event(c,'worker','training.'+status,job['id'])
    if job['pod_id']!=os.environ.get('DOEMO_RUNPOD_POD_ID'):
        update('interrupted',error='Le Pod a changé ; contrôler la tâche sur le Pod précédent.',retry_at=now+60);return True
    control=gpu.state(store)
    if control['pod_id']!=job['pod_id'] or control['phase'] not in ('ready','busy') or not control['observed_at'] or now-control['observed_at']>60 or control['pending_action']=='stop':
        update('waiting_gpu' if not job['dispatched'] else job['status'],retry_at=now+10);return True
    transport=transport_factory(gpu.gateway_url(job['pod_id']))
    def bundle_for(dataset):
        folder=store.root/'training-outbox';folder.mkdir(exist_ok=True)
        path=folder/(job['id']+'.zip')
        if path.exists():
            bundle=path.read_bytes()
            with store.connect() as c:expected=record(c,job['id'])['archive_sha256']
            if expected and hashlib.sha256(bundle).hexdigest()!=expected:raise ValueError('Archive locale corrompue')
        else:
            bundle=dataset_bundle(dataset['snapshot'],job['engine'],lambda e:store.root/'documents'/e['document_id']/f"page-{e['page']}.png")
            temporary=folder/(uuid.uuid4().hex+'.tmp');temporary.write_bytes(bundle);temporary.replace(path)
        with store.connect() as c:c.execute('UPDATE training_runs SET archive_sha256=? WHERE id=?',(hashlib.sha256(bundle).hexdigest(),job['id']))
        return bundle
    try:
        with store.connect() as c:
            try:dataset=row_dataset(c,job['dataset_id'])
            except ValueError:
                dataset=None
            inference=bool(c.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running','waiting_gpu','retry_gpu','interrupted') AND json_extract(payload,'$.engine') IN ('qwen','paddleocr','rtmdet') LIMIT 1").fetchone())
            current=record(c,job['id'])
        if dataset is None and not current['cancel_requested']:
            cancel(store,'worker-consent-revoked',job['id']);return True
        if not job['dispatched']:
            if current['cancel_requested'] or current['status']=='cancelled':return True
            if inference:update('queued',retry_at=now+5);return True
            if job['profile']!=profile():update('failed',error='Profil modifié avant démarrage.');return True
            bundle=bundle_for(dataset)
            # Intent must be durable before the first byte leaves OVH.
            with gpu.lifecycle_lock(store),store.connect() as c:
                c.execute('BEGIN IMMEDIATE');current=record(c,job['id'])
                if current['cancel_requested']:return True
                c.execute("UPDATE training_runs SET dispatched=1,status='dispatching' WHERE id=?",(job['id'],))
            response=transport.submit(job,dataset['snapshot'],bundle)
        else:
            response=transport.status(job['id'])
            if current['cancel_requested']:
                # Cancel is an idempotent tombstone even if the remote job is absent.
                response=transport.control(job['id'],'cancel')
            elif response is None:
                if inference:update(job['status'],retry_at=now+5);return True
                if job['profile']!=profile():raise ValueError('Profil modifié')
                # Same ID, same archive and same request. A late original upload
                # is deduplicated by the gateway; cancellation creates a tombstone.
                response=transport.submit(job,dataset['snapshot'],bundle_for(dataset))
            elif inference and response['status'] in ('queued','running','checkpointing'):
                response=transport.control(job['id'],'pause')
            elif not inference and ((response['status']=='paused' and response.get('pause_reason')=='inference') or (response['status']=='interrupted' and current['resume_requested'])):
                if dataset is None:raise ValueError('Consentement révoqué')
                response=transport.control(job['id'],'resume')
                with store.connect() as c:c.execute('UPDATE training_runs SET resume_requested=0 WHERE id=?',(job['id'],))
        if not isinstance(response,dict) or response.get('id')!=job['id'] or response.get('status') not in (*ACTIVE,*TERMINAL):raise ValueError('État distant invalide')
        status=response['status'];progress=response.get('progress')
        if progress is not None and (type(progress) not in (int,float) or not math.isfinite(progress) or not 0<=progress<=1):raise ValueError('Progression invalide')
        revision=response.get('revision',0)
        if type(revision) is not int or revision<job['remote_revision']:raise ValueError('Réponse distante périmée')
        result=valid_result(job,dataset,response) if status=='completed' and dataset else None
        if status=='completed' and dataset is None:status='cancelled'
        update(status,progress=progress,result=encoded(result) if result else None,remote_revision=revision,
               error=response.get('error') if status in ('failed','interrupted') else None,retry_at=now+5)
        if revision>job['remote_revision']:
            with store.connect() as c:event(c,'worker','training.observed',job['id'],{k:response.get(k) for k in ('status','revision','iteration','total_iterations','epoch','loss','progress')})
    except (httpx.HTTPError,OSError):
        update(job['status'],error='Connexion GPU interrompue ; vérification différée avec le même identifiant.',retry_at=now+15)
    except (ValueError,KeyError,TypeError):
        update('interrupted',error='État ou artefacts distants à contrôler. Aucun résultat enregistré.',retry_at=now+60)
    return True


def main():
    from .store import Store
    store=Store(os.environ.get('DOEMO_RELEVES_DATA','/var/lib/doemo-studio/releves'))
    while True:
        tick(store);time.sleep(2)

if __name__=='__main__':main()
