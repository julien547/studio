"""Project-owned geometry review, immutable revisions and explicit training drafts."""
import json
import time
import uuid
from pathlib import Path
from typing import Literal
from fastapi import Depends
from fastapi.responses import Response
from pydantic import Field
from shapely.geometry import Point
from .models import Model
from .store import Conflict
from . import circulations as geo
from . import circulation_preparation as prep


class Analyze(Model):
    source:geo.Source
    rules:geo.Rules=Field(default_factory=geo.Rules)
    revision:int=Field(default=-1,ge=-1)
    replace_reviewed:bool=False


class Change(Model):
    revision:int=Field(ge=0)
    operation:Literal['accept','reject','merge','split','hole','replace','add','color','restore']
    ids:list[str]=Field(default_factory=list,max_length=1000)
    geometry:dict|list|None=None
    category:Literal['room','technical','outside','unknown']|None=None
    color:geo.Color|None=None
    restore_revision:int|None=None


class Hint(Model):
    revision:int=Field(ge=0)
    job_id:str


class Learn(Model):
    source_document_id:str
    page:int=Field(ge=1)


def attach(app,store,actor,admin,get,doc):
    prefix='/projects/{ident}/circulations'
    def read(c,ident,cid):
        r=c.execute('SELECT state FROM circulation_documents WHERE project_id=? AND id=?',(ident,cid)).fetchone()
        if not r:raise LookupError('Document de circulations absent')
        return json.loads(r[0])
    def save(c,ident,cid,state,who,action,revision):
        state['revision']=revision+1
        value=json.dumps(state,ensure_ascii=False,allow_nan=False)
        if revision<0:c.execute('INSERT INTO circulation_documents(project_id,id,revision,state) VALUES(?,?,?,?)',(ident,cid,0,value))
        elif c.execute('UPDATE circulation_documents SET revision=?,state=?,updated=CURRENT_TIMESTAMP WHERE project_id=? AND id=? AND revision=?',(revision+1,value,ident,cid,revision)).rowcount!=1:raise Conflict('Recharger la version des circulations')
        c.execute('INSERT INTO circulation_history(project_id,document_id,revision,state,actor,action) VALUES(?,?,?,?,?,?)',(ident,cid,revision+1,value,who.login,action))
        return state

    @app.get(prefix)
    def listing(ident:str,who=Depends(actor)):
        get(ident,who)
        with store.connect() as c:return [dict(r) for r in c.execute('SELECT id,revision,updated FROM circulation_documents WHERE project_id=?',(ident,))]

    @app.post(prefix)
    def analyze(ident:str,data:Analyze,who=Depends(actor)):
        get(ident,who);cid=data.source.document_id
        with store.connect() as c:
            old=c.execute('SELECT state FROM circulation_documents WHERE project_id=? AND id=?',(ident,cid)).fetchone()
            if old:
                previous=json.loads(old[0])
                if geo.digest(data.source.model_dump())==previous['source_version'] and data.rules.model_dump()==previous['rules']:return previous
                if previous['revision']!=data.revision:raise Conflict('Recharger avant régénération')
                if any(r['origin'].startswith('human') for r in previous['regions']) and not data.replace_reviewed:raise Conflict('Confirmer la régénération : corrections humaines conservées dans l’historique')
            elif data.revision!=-1:raise Conflict('Document absent')
        value=geo.reconstruct(data.source,data.rules)
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            return save(c,ident,cid,value,who,'reconstruct',data.revision)

    @app.get(prefix+'/{cid}')
    def fetch(ident:str,cid:str,who=Depends(actor)):
        get(ident,who)
        with store.connect() as c:return read(c,ident,cid)

    @app.get(prefix+'/{cid}/history')
    def history(ident:str,cid:str,who=Depends(actor)):
        get(ident,who)
        with store.connect() as c:return [dict(r) for r in c.execute('SELECT revision,actor,action,created FROM circulation_history WHERE project_id=? AND document_id=? ORDER BY revision DESC',(ident,cid))]

    @app.get(prefix+'/{cid}/preparation')
    def preparation_hints(ident:str,cid:str,who=Depends(actor)):
        get(ident,who)
        with store.connect() as c:state=read(c,ident,cid)
        return prep.suggestions(geo.Source.model_validate(state['source']),geo.Rules.model_validate(state['rules']))

    @app.post(prefix+'/{cid}/preparation')
    def preparation(ident:str,cid:str,data:prep.Preparation,who=Depends(actor)):
        get(ident,who)
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE');state=read(c,ident,cid)
            if data.revision!=state['revision']:raise Conflict('Recharger avant préparation')
            if any(r['origin'].startswith('human') for r in state['regions']) and not data.replace_reviewed:
                raise Conflict('Confirmer le recalcul après préparation : corrections conservées dans l’historique')
            return save(c,ident,cid,prep.prepare(state,data),who,'prepare_'+data.operation,data.revision)

    @app.put(prefix+'/{cid}')
    def change(ident:str,cid:str,data:Change,who=Depends(actor)):
        get(ident,who)
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE');state=read(c,ident,cid)
            if data.revision!=state['revision']:raise Conflict('Recharger avant modification')
            if data.operation=='restore':
                row=c.execute('SELECT state FROM circulation_history WHERE project_id=? AND document_id=? AND revision=?',(ident,cid,data.restore_revision)).fetchone()
                if not row:raise LookupError('Révision absente')
                prior=json.loads(row[0])
                if any(prior['source'][k]!=state['source'][k] for k in ('provider','source_sha256','architecture_sha256','artboards','color_space')):raise ValueError('Restauration d’une autre source interdite ; réimporter cette source explicitement')
                state=prior
            elif data.operation=='color':
                if data.color is None:raise ValueError('Nuance requise')
                if data.color.mode!='SPOT' and data.color.mode!=state['source']['color_space']:raise ValueError('Le mode de la nuance doit correspondre au document')
                state['color']=data.color.model_dump()
            else:geo.edit(state,data.operation,data.ids,data.geometry,data.category)
            return save(c,ident,cid,state,who,data.operation,data.revision)

    @app.get(prefix+'/{cid}/point')
    def select_point(ident:str,cid:str,level:str,x:float,y:float,who=Depends(actor)):
        get(ident,who)
        with store.connect() as c:state=read(c,ident,cid)
        return [r['id'] for r in state['regions'] if r['level']==level and geo.poly(r['shape']).covers(Point(x,y))]

    @app.get(prefix+'/{cid}/export')
    def export(ident:str,cid:str,who=Depends(actor)):
        get(ident,who)
        with store.connect() as c:value=geo.export(read(c,ident,cid))
        return value

    @app.post(prefix+'/{cid}/ai-hints')
    def hints(ident:str,cid:str,data:Hint,who=Depends(actor)):
        # Reuse completed private Qwen/OCR jobs, never COCO and never their polygons.
        get(ident,who)
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE');state=read(c,ident,cid)
            if state['revision']!=data.revision:raise Conflict('Recharger avant import IA')
            row=c.execute('SELECT * FROM jobs WHERE id=? AND project_id=?',(data.job_id,ident)).fetchone()
            if not row or row['status']!='completed':raise ValueError('Analyse terminée requise')
            payload=json.loads(row['payload'])
            if payload['engine'] not in ('qwen','paddleocr'):raise ValueError('Seuls les libellés Qwen/PaddleOCR sont acceptés')
            source,_=doc(ident,payload['document_id'],who,payload['page'])
            if source['sha256']!=state['source']['source_sha256']:raise ValueError('Résultat IA d’un autre fichier source')
            if not 1<=payload['page']<=len(state['source']['artboards']):raise ValueError('Page IA sans plan de travail correspondant')
            rect=state['source']['artboards'][payload['page']-1];l,t,r,b=rect
            labels={v['id']:[] for v in state['regions']}
            for a in json.loads(row['result']).get('annotations',[]):
                box=a.get('bbox');text=a.get('text','').strip()
                if not box or not text:continue
                point=Point(l+(box['x']+box['w']/2)*(r-l),t-(box['y']+box['h']/2)*(t-b))
                matches=[v for v in state['regions'] if v['artboard']==payload['page']-1 and geo.poly(v['shape']).contains(point)]
                if len(matches)==1:labels[matches[0]['id']].append(text)
            for region in state['regions']:
                if region['status']!='proposed' or region['category']!='unknown' or not labels[region['id']]:continue
                cat,score,reason=geo.classify(labels[region['id']],geo.Rules.model_validate(state['rules']))
                region.update(category=cat,confidence=min(score,.8),reason='Proposition '+payload['engine']+' : '+reason,
                              origin=payload['engine']+':'+data.job_id,suggested=False)
            return save(c,ident,cid,state,who,'ai_labels',data.revision)

    @app.post(prefix+'/{cid}/corrections')
    def capture(ident:str,cid:str,who=Depends(actor)):
        p=get(ident,who)
        if not p['metadata'].get('training_authorized'):raise ValueError('Autoriser le projet pour l’apprentissage avant collecte')
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE');state=read(c,ident,cid);ids=[]
            for region in state['regions']:
                if region['status'] not in ('validated','rejected'):continue
                correction=dict(schema='doemo.circulation-correction/1',source_version=state['source_version'],
                    original_category=region['original_category'],corrected_category=region['category'],
                    correction_type='accept' if region['status']=='validated' else 'reject',region=region,
                    source=state['source'],processing_version=geo.VERSION,actor=who.login)
                key=geo.digest([ident,cid,region['id'],state['revision']])
                c.execute('INSERT OR IGNORE INTO circulation_corrections(id,project_id,document_id,region_id,revision,data,actor) VALUES(?,?,?,?,?,?,?)',
                          (key,ident,cid,region['id'],state['revision'],json.dumps(correction),who.login));ids.append(key)
            return {'ids':ids}

    @app.get('/projects/training/circulation-corrections')
    def corrections(who=Depends(admin)):
        with store.connect() as c:
            rows=c.execute('SELECT cc.* FROM circulation_corrections cc JOIN projects p ON p.id=cc.project_id WHERE json_extract(p.metadata,\'$.training_authorized\')=1 ORDER BY cc.created DESC').fetchall()
            return [dict(dict(r),data=json.loads(r['data'])) for r in rows]

    @app.post('/projects/training/circulation-corrections/{key}/example')
    def training_draft(key:str,data:Learn,who=Depends(admin)):
        from .training import authorized,encoded
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM circulation_corrections WHERE id=?',(key,)).fetchone()
            if not row:raise LookupError('Correction absente')
            authorized(c,row['project_id'])
            if row['training_example_id']:return {'id':row['training_example_id']}
            value=json.loads(row['data']);source,_=doc(row['project_id'],data.source_document_id,who,data.page)
            if source['sha256']!=value['source']['source_sha256'] or data.page!=value['region']['artboard']+1 or source['role']!='survey':raise ValueError('Importer le même AI comme relevé source, avec la page correspondante')
            interpretation=encoded({k:value[k] for k in ('original_category','corrected_category','correction_type','region')})
            if len(interpretation)>16000:raise ValueError('Correction trop détaillée ; conserver son export géométrique')
            from .training import Example
            bounds=geo.poly(value['region']['shape']).bounds
            convention='Interpréter la fonction de la région du niveau '+value['region']['level']+' dans la boîte document Illustrator (points, Y vers le haut) '+str([round(v,3) for v in bounds])+'. Ne pas inventer de coordonnées.'
            e=Example(engine='qwen',project_id=row['project_id'],document_id=data.source_document_id,page=data.page,labels=[],
                      convention=convention,interpretation=interpretation,
                      notes='Correction vectorielle '+key+' ; coordonnées document Illustrator en points, y croissant vers le haut.')
            ident=uuid.uuid4().hex
            c.execute('INSERT INTO training_examples(id,engine,project_id,document_id,page,revision,status,data,author) VALUES(?,?,?,?,?,0,?,?,?)',
                      (ident,'qwen',row['project_id'],data.source_document_id,data.page,'draft',e.model_dump_json(),who.login))
            c.execute('UPDATE circulation_corrections SET training_example_id=? WHERE id=?',(ident,key))
            c.execute('INSERT INTO training_revisions(example_id,revision,status,data,actor) VALUES(?,0,?,?,?)',(ident,'draft',e.model_dump_json(),who.login))
            c.execute('INSERT INTO training_audit(actor,action,entity,detail) VALUES(?,?,?,?)',(who.login,'circulation.example',ident,encoded({'correction':key})))
            return {'id':ident}
