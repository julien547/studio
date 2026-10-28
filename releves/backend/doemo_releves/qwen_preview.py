"""Admin-only paired Qwen inference. Reference testing does not train weights.

The ordinary durable inference queue owns execution/lifecycle/retries. Each job
freezes its reference context, and the gateway must acknowledge its exact hash.
Held-out expected answers remain on OVH and are never sent to the model.
"""
import json
import hashlib
import time
import uuid
from typing import Literal
from fastapi import Depends
from pydantic import Field
from .models import Model
from .store import Conflict
from . import gpu
from .training import PREFIX,encoded,digest,row_dataset,audit

REVISION='doemo.qwen-reference/1'


def image_hash(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


class Preview(Model):
    example_id: str
    confirmed: bool=False
    request_key: str=Field(pattern=r'^[a-zA-Z0-9_-]{16,80}$')


class Review(Model):
    verdict: Literal['candidate_better','same','baseline_better','inconclusive']
    notes: str=Field(min_length=1,max_length=2000)


def context(version_id,rules):
    if not isinstance(rules,dict) or len(rules)>100:raise ValueError('Au plus 100 conventions par test Qwen')
    if any(not isinstance(k,str) or not k.strip() or len(k)>400 or not isinstance(v,str) or not v.strip() or len(v)>16000 for k,v in rules.items()):raise ValueError('Conventions invalides')
    value={'schema':REVISION,'version_id':version_id,'rules':rules,'rules_sha256':digest(rules)}
    if len(encoded(value).encode())>32768:raise ValueError('Référentiel trop volumineux pour ce test : limiter à 32 Kio, sans troncature silencieuse')
    return value


def reference(c,ident):
    row=c.execute("SELECT * FROM training_versions WHERE id=? AND engine='qwen' AND method='reference'",(ident,)).fetchone()
    if not row:raise LookupError()
    version=dict(row);version['manifest']=json.loads(row['manifest'])
    dataset=row_dataset(c,version['dataset_id'])
    rules=version['manifest']['rules']
    if digest(rules)!=version['manifest']['artifact_sha256']:raise ValueError('Référentiel altéré')
    return version,dataset


def check_job(c,payload):
    """Recheck consent and immutable binding before each actual network attempt."""
    ident=payload['training_preview']
    row=c.execute('SELECT * FROM qwen_previews WHERE id=?',(ident,)).fetchone()
    if not row:raise ValueError('Comparaison absente')
    version,dataset=reference(c,row['version_id'])
    supplied=payload['qwen_context']
    expected=context(version['id'],version['manifest']['rules']) if supplied.get('version_id') else context(None,{})
    if supplied!=expected:raise ValueError('Contexte figé incompatible')
    e=next((e for e in dataset['snapshot']['examples'] if e['id']==row['example_id'] and e['split']=='test'),None)
    if not e or payload['document_id']!=e['document_id'] or payload['page']!=e['page']:raise ValueError('Document de test incompatible')


def result(c,row):
    value=dict(row)
    _,dataset=reference(c,row['version_id'])
    e=next(e for e in dataset['snapshot']['examples'] if e['id']==row['example_id'])
    value['expected']=e['data']['interpretation']
    value['source']={'project_id':e['project_id'],'document_id':e['document_id'],'name':e['source']['name'],'page':e['page']}
    value['review']=json.loads(value['review']) if value['review'] else None
    for side in ('baseline','candidate'):
        job=c.execute('SELECT id,status,stage,error,result,created,updated,payload FROM jobs WHERE id=?',(row[side+'_job'],)).fetchone()
        entry=dict(job);payload=json.loads(entry.pop('payload'));entry['result']=json.loads(entry['result']) if entry['result'] else None
        entry['context_sha256']=digest(payload['qwen_context']);value[side]=entry
    value['complete']=all(value[k]['status']=='completed' for k in ('baseline','candidate'))
    value.update(scope='qwen_reference_preview',weights_modified=False,publication_eligible=False,base_weights_attested=False)
    return value


def attach(app,store,admin,doc):
    @app.get(PREFIX+'/models/qwen/{ident}/preview-options')
    def options(ident:str,who=Depends(admin)):
        with store.connect() as c:
            version,dataset=reference(c,ident)
            context(ident,version['manifest']['rules'])
            return {'examples':[{'id':e['id'],'name':e['source']['name'],'page':e['page'],'expected':e['data']['interpretation']}
                for e in dataset['snapshot']['examples'] if e['split']=='test']}

    @app.get(PREFIX+'/models/qwen/{ident}/previews')
    def history(ident:str,who=Depends(admin)):
        with store.connect() as c:
            reference(c,ident)
            return [result(c,r) for r in c.execute('SELECT * FROM qwen_previews WHERE version_id=? ORDER BY created DESC,id DESC LIMIT 50',(ident,))]

    @app.post(PREFIX+'/models/qwen/{ident}/previews/{preview_id}/review')
    def review(ident:str,preview_id:str,data:Review,who=Depends(admin)):
        if not data.notes.strip():raise ValueError('Renseigner le motif de comparaison')
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM qwen_previews WHERE id=? AND version_id=?',(preview_id,ident)).fetchone()
            if not row:raise LookupError()
            if not result(c,row)['complete']:raise ValueError('Les deux inférences doivent être terminées avant comparaison')
            c.execute('UPDATE qwen_previews SET review=?,reviewer=?,reviewed=CURRENT_TIMESTAMP WHERE id=?',
                      (data.model_dump_json(),who.login,preview_id))
            audit(c,who.login,'reference.preview.review',preview_id,data.model_dump())
            return result(c,c.execute('SELECT * FROM qwen_previews WHERE id=?',(preview_id,)).fetchone())

    @app.post(PREFIX+'/models/qwen/{ident}/previews')
    def launch(ident:str,data:Preview,who=Depends(admin)):
        if not data.confirmed:raise ValueError('Confirmer les deux inférences et leur coût GPU')
        fingerprint=digest({'version_id':ident,'example_id':data.example_id})
        with gpu.lifecycle_lock(store),store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            prior=c.execute('SELECT * FROM qwen_previews WHERE author=? AND request_key=?',(who.login,data.request_key)).fetchone()
            if prior:
                if prior['request_sha256']!=fingerprint:raise Conflict('Clé déjà associée à une autre comparaison')
                return result(c,prior)
            version,dataset=reference(c,ident)
            example=next((e for e in dataset['snapshot']['examples'] if e['id']==data.example_id and e['split']=='test'),None)
            if not example:raise ValueError('Choisir un exemple du lot test indépendant de cette version')
            # Exact same complete source page in both calls; no expected answer or
            # test label enters the context. Only frozen training conventions do.
            _,directory=doc(example['project_id'],example['document_id'],who,example['page'])
            source_sha256=image_hash(directory/f"page-{example['page']}.png")
            preview=uuid.uuid4().hex;ids=[]
            for version_id,rules in ((None,{}),(ident,version['manifest']['rules'])):
                job=uuid.uuid4().hex;ids.append(job)
                payload={'engine':'qwen','document_id':example['document_id'],'page':example['page'],
                         'training_preview':preview,'qwen_context':context(version_id,rules),'input_sha256':source_sha256}
                c.execute('INSERT INTO jobs(id,project_id,actor,status,stage,payload) VALUES(?,?,?,?,?,?)',
                          (job,example['project_id'],who.login,'queued','Comparaison Qwen en attente',encoded(payload)))
            c.execute('INSERT INTO qwen_previews(id,version_id,example_id,baseline_job,candidate_job,author,request_key,request_sha256) VALUES(?,?,?,?,?,?,?,?)',
                      (preview,ident,example['id'],*ids,who.login,data.request_key,fingerprint))
            c.execute('UPDATE gpu_control SET last_activity=?,next_poll=0 WHERE id=1',(time.time(),))
            audit(c,who.login,'reference.preview.queued',preview,{'version_id':ident,'example_id':example['id']})
            return result(c,c.execute('SELECT * FROM qwen_previews WHERE id=?',(preview,)).fetchone())
