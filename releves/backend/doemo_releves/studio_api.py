"""MVP routes added to the existing protected project API."""
import hashlib
import json
import uuid
from pathlib import Path
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import Field
from .models import Model, ProjectState
from .coordinates import frames
from .ai_contracts import normalise


class Metadata(Model):
    reference: str = Field(default='', max_length=100)
    client: str = Field(default='', max_length=200)
    address: str = Field(default='', max_length=500)
    building_type: str = Field(default='', max_length=100)
    responsible: str = Field(default='', max_length=100)
    notes: str = Field(default='', max_length=4000)
    training_authorized: bool = False


class Equipment(Model):
    code: str = Field(pattern=r'^[A-Z][A-Z0-9_]{1,50}$')
    name: str = Field(min_length=1,max_length=200)
    synonyms: list[str] = Field(default_factory=list,max_length=50)
    asset_id: str | None = None
    active: bool = True
    description: str = Field(default='',max_length=2000)


CATALOGUE = [
    Equipment(code='PCF',name='Porte coupe-feu',synonyms=['PCF'],asset_id='02063716-c9a4-4fc3-828b-2dfaa7f44111'),
    Equipment(code='EXT_PORTATIF',name='Extincteur portatif',synonyms=['EXT','H2O','CO2','EP6'],asset_id='6fac994a-56a3-4228-b2f5-ba5bc64c5541',description='Pictogramme unique DOEMO, sans distinction de l’agent extincteur.'),
    Equipment(code='VEI',name='Vous êtes ici',synonyms=['VEI']),
    Equipment(code='PLAN_EVACUATION',name='Plan d’évacuation',synonyms=['PE']),
    Equipment(code='PLAN_INTERVENTION',name='Plan d’intervention',synonyms=['PI']),
    Equipment(code='SANS_ISSUE',name='Signalisation sans issue'),
    Equipment(code='SORTIE',name='Issue de secours'),
    Equipment(code='RIA',name='Robinet d’incendie armé'),
    Equipment(code='DM',name='Déclencheur manuel')]


class ImportedAnalysis(Model):
    engine: Literal['paddleocr','qwen','rtmdet']
    document_id: str
    page: int = Field(ge=1)
    width: int = Field(gt=0,le=50000)
    height: int = Field(gt=0,le=50000)
    revision: int = Field(ge=0)
    data: dict


class AcceptAnalysis(Model):
    revision: int = Field(ge=0)


def attach(app, store, actor, admin, get, doc):
    with store.connect() as c:
        for item in CATALOGUE:
            c.execute('INSERT OR IGNORE INTO equipment_catalogue VALUES(?,?)',(item.code,item.model_dump_json()))

    @app.get('/projects/catalogue')
    def catalogue(who=Depends(actor)):
        with store.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT data FROM equipment_catalogue ORDER BY code')]

    @app.put('/projects/catalogue/{code}')
    def catalogue_put(code: str, item: Equipment, who=Depends(admin)):
        if code!=item.code: raise ValueError('Code métier incompatible')
        if item.asset_id and not any(a['id']==item.asset_id for lib in store.libraries() for a in lib['assets']):
            raise ValueError('Pictogramme absent des bibliothèques importées')
        with store.connect() as c:
            c.execute('INSERT OR REPLACE INTO equipment_catalogue VALUES(?,?)',(code,item.model_dump_json()))
            c.execute('INSERT INTO events(actor,action,data) VALUES(?,?,?)',(who.login,'catalogue',item.model_dump_json()))
        return item

    @app.put('/projects/{ident}/metadata')
    def metadata(ident: str, data: Metadata, who=Depends(actor)):
        previous=get(ident,who)
        if data.training_authorized != previous['metadata'].get('training_authorized',False) and not who.admin:
            raise HTTPException(403,'L’autorisation d’apprentissage est réservée à l’administration')
        with store.connect() as c:
            c.execute('UPDATE projects SET metadata=? WHERE id=?',(data.model_dump_json(),ident))
            c.execute('INSERT INTO events(project_id,actor,action,data) VALUES(?,?,?,?)',(ident,who.login,'metadata',data.model_dump_json()))
        return get(ident,who)

    @app.get('/projects/{ident}/history')
    def history(ident: str, who=Depends(actor)):
        get(ident,who)
        with store.connect() as c:
            return [dict(r) for r in c.execute('SELECT revision,actor,created FROM revisions WHERE project_id=? ORDER BY revision DESC LIMIT 200',(ident,))]

    @app.get('/projects/{ident}/history/{revision}')
    def historical(ident: str, revision: int, who=Depends(actor)):
        get(ident,who)
        with store.connect() as c:
            row=c.execute('SELECT state FROM revisions WHERE project_id=? AND revision=?',(ident,revision)).fetchone()
        if not row: raise LookupError('Révision absente')
        return json.loads(row[0])

    @app.get('/projects/{ident}/structured-export')
    def structured_export(ident: str, who=Depends(actor)):
        p=get(ident,who)
        with store.connect() as c:
            c.execute('INSERT INTO events(project_id,actor,action,data) VALUES(?,?,?,?)',
                      (ident,who.login,'structured-export',json.dumps({'revision':p['state']['revision']})))
        transformations=[]
        for d in p['documents']:
            for page in d['pages']:
                transformations.append({'document_id':d['id'],'page':page['number'],'dimensions':page,
                    'frames':frames(page)})
        for floor in p['state']['floors']:
            if floor.get('source_document_id'):
                d=next(d for d in p['documents'] if d['id']==floor['source_document_id'])
                transformations.append({'floor_id':floor['id'],'document_id':d['id'],'page':floor['source_page'],
                    'frames':frames(d['pages'][floor['source_page']-1],floor['source_region'],floor.get('rotation_deg',0))})
        return {'schema_version':'doemo.studio-export/1','project':p,'transformations':transformations,
                'coordinates':{'unit':'normalized','origin':'upright_source_page_top_left','bbox':'annotation_text_region','anchor':'physical_equipment_on_source','target':'optional_illustrator_target_override'},
                'native_ai_created':False}

    @app.post('/projects/{ident}/analysis-imports')
    def import_analysis(ident: str, data: ImportedAnalysis, who=Depends(actor)):
        p=get(ident,who)
        source,_=doc(ident,data.document_id,who,data.page)
        if source['role']!='survey':
            raise ValueError('Une analyse doit être associée à une page de relevé')
        raw=json.dumps(data.data,ensure_ascii=False)
        if len(raw.encode())>8*1024**2: raise ValueError('JSON limité à 8 Mio')
        if data.revision!=p['state']['revision']: raise ValueError('Recharger la révision courante')
        result=normalise(data.engine,data.data,data.document_id,data.page,data.width,data.height)
        # Content-addressed import; same source/engine/frame cannot be applied twice.
        digest=hashlib.sha256((ident+json.dumps(data.model_dump(exclude={'revision'}),sort_keys=True)).encode()).hexdigest()
        ident_import=digest[:32]
        with store.connect() as c:
            prior=c.execute('SELECT id FROM jobs WHERE id=? AND project_id=?',(ident_import,ident)).fetchone()
            if not prior:
                c.execute('INSERT INTO jobs(id,project_id,actor,status,stage,payload,result) VALUES(?,?,?,?,?,?,?)',
                    (ident_import,ident,who.login,'completed','imported',data.model_dump_json(),json.dumps(result)))
        return {'id':ident_import,'result':result}

    @app.get('/projects/{ident}/jobs')
    def jobs(ident: str, who=Depends(actor)):
        get(ident,who)
        with store.connect() as c:
            rows=c.execute('SELECT id,status,stage,error,attempts,created,updated,payload,result FROM jobs WHERE project_id=? ORDER BY created DESC LIMIT 100',(ident,))
            return [dict(dict(r), payload={k:v for k,v in json.loads(r['payload']).items() if k in ('engine','document_id','page')}, result=json.loads(r['result']) if r['result'] else None) for r in rows]

    @app.post('/projects/{ident}/jobs/{job_id}/apply')
    def apply_analysis(ident: str, job_id: str, data: AcceptAnalysis, who=Depends(actor)):
        p=get(ident,who)
        with store.connect() as c:
            row=c.execute('SELECT * FROM jobs WHERE id=? AND project_id=?',(job_id,ident)).fetchone()
        if not row or row['status']!='completed': raise ValueError('Analyse terminée requise')
        state=ProjectState.model_validate(p['state'])
        if state.revision!=data.revision: raise ValueError('Recharger avant d’intégrer les propositions')
        from .models import Annotation
        known={a.id for a in state.annotations}
        additions=[Annotation.model_validate(a) for a in json.loads(row['result'])['annotations'] if a['id'] not in known]
        if not additions: return p
        # No replacement or implicit confirmation of human corrections.
        for a in additions:
            a.status='review';a.review=type(a.review)();a.training_accepted=False
        state.annotations.extend(additions);state.workflow='review'
        from .exchange import validate_state
        store.save(ident,who.login,validate_state(state,p['documents']),'apply-analysis:'+job_id)
        return get(ident,who)

    @app.get('/projects/{ident}/dataset')
    def dataset(ident: str, who=Depends(admin)):
        p=get(ident,who)
        if not p['metadata'].get('training_authorized'):
            raise ValueError('Autorisation de réutilisation du projet pour apprentissage requise')
        images=[];annotations=[];categories={};ids={}
        accepted_at={};previous={}
        with store.connect() as c:
            for row in c.execute('SELECT revision,actor,created,state FROM revisions WHERE project_id=? ORDER BY revision',(ident,)):
                revision=json.loads(row['state'])
                for example in revision['annotations']:
                    if example.get('training_accepted') and not previous.get(example['id'],False):
                        accepted_at[example['id']]={'actor':row['actor'],'date':row['created'],'revision':row['revision']}
                previous={a['id']:a.get('training_accepted',False) for a in revision['annotations']}
        for a in p['state']['annotations']:
            if not a.get('training_accepted') or not a['review']['equipment'] or not a['review']['position'] or not a['anchor'] or not a['equipment_type'] or a['status']=='rejected': continue
            key=(a['source_document_id'],a['source_page'])
            d=next(d for d in p['documents'] if d['id']==key[0]);page=d['pages'][key[1]-1];w,h=page['width'],page['height']
            if key not in ids:
                ids[key]=len(images)+1
                images.append({'id':ids[key],'file_name':key[0]+f'/page-{key[1]}.png','width':w,'height':h,'document_sha256':d['sha256'],'split_group':p['metadata'].get('reference') or ident})
            cat=a['equipment_type'];categories.setdefault(cat,len(categories)+1);b=a['bbox']
            annotations.append({'id':len(annotations)+1,'image_id':ids[key],'category_id':categories[cat],
                'bbox':[b['x']*w,b['y']*h,b['w']*w,b['h']*h],'area':b['w']*w*b['h']*h,'iscrowd':0,
                'equipment_point':[a['anchor']['x']*w,a['anchor']['y']*h],'text':a['text'],'annotation_id':a['id'],
                'floor_id':a['floor_id'],'source_method':a['method'],'human_acceptance':accepted_at.get(a['id']),
                'reference_version':p['state']['mapping_version']})
        return {'info':{'version':p['state']['revision'],'project_id':ident,'split_policy':'group_by_building_or_document','training_started':False},
                'images':images,'annotations':annotations,'categories':[{'id':i,'name':name} for name,i in categories.items()]}
