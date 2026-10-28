"""Admin learning workspace. Examples, immutable datasets and versions are distinct.

No GPU training/evaluation/deployment adapter is installed in this release. Those
operations fail closed, independently per engine, without reserving the production
GPU. Qwen reference snapshots and reference-only evaluation run on OVH.
"""
import hashlib
import io
import json
import math
import uuid
import zipfile
from datetime import date
from typing import Literal
from PIL import Image
from fastapi import Depends, HTTPException
from fastapi.responses import Response
from pydantic import Field, model_validator
from .models import Model, Box, Point
from .store import Conflict
from .coordinates import frames

Engine = Literal['qwen','paddleocr','rtmdet','architecture']
Kind = Literal['wall','door','opening','equipment','text','other']
PREFIX='/projects/training'
ENGINES={
 'qwen':{'name':'Qwen3.5-9B','function':'Compréhension des plans et conventions DOEMO'},
 'paddleocr':{'name':'PaddleOCR','function':'Reconnaissance des écritures'},
 'rtmdet':{'name':'RTMDet','function':'Détection des équipements'},
 'architecture':{'name':'IA architecturale','function':'Axes médians, portes et ouvertures — moteur à développer'}}


def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(encoded(value).encode()).hexdigest()
def audit(c,actor,action,entity,detail=None):
 c.execute('INSERT INTO training_audit(actor,action,entity,detail) VALUES(?,?,?,?)',(actor,action,entity,encoded(detail or {})))


class Category(Model):
 code: str=Field(pattern=r'^[A-Z][A-Z0-9_]{1,50}$')
 name: str=Field(min_length=1,max_length=100)
 kind: Kind
 active: bool=True


class Label(Model):
 id: str=Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
 category: str=Field(max_length=50)
 bbox: Box
 anchor: Point|None=None
 segments: list[tuple[Point,Point]]=Field(default_factory=list,max_length=1000)
 mask_polygons: list[list[Point]]=Field(default_factory=list,max_length=100)
 text: str=Field(default='',max_length=4000)
 origin: str=Field(default='manual',max_length=100)
 # Human acknowledgement is per label, never inferred from AI confidence.
 checked: bool=False

 @model_validator(mode='after')
 def masks(self):
  if any(not 3<=len(p)<=5000 for p in self.mask_polygons):raise ValueError('Polygone de masque invalide')
  return self


class Example(Model):
 revision: int=Field(default=0,ge=0)
 engine: Engine
 project_id: str
 document_id: str
 page: int=Field(ge=1)
 floor_id: str|None=None
 region: Box=Field(default_factory=lambda:Box(x=0,y=0,w=1,h=1))
 rotation: Literal[0,90,180,270]=0
 labels: list[Label]=Field(default_factory=list,max_length=1000)
 interpretation: str=Field(default='',max_length=16000)
 observed: str=Field(default='',max_length=16000)
 convention: str=Field(default='',max_length=400)
 notes: str=Field(default='',max_length=4000)
 junctions: list[Point]=Field(default_factory=list,max_length=1000)

 @model_validator(mode='after')
 def unique(self):
  if len({a.id for a in self.labels})!=len(self.labels):raise ValueError('Identifiants d’annotation dupliqués')
  return self


class Decision(Model):
 revision: int=Field(ge=0)
 status: Literal['validated','rejected']
 reason: str=Field(default='',max_length=2000)


class Dataset(Model):
 engine: Engine
 name: str=Field(min_length=1,max_length=120)
 example_ids: list[str]=Field(min_length=1,max_length=500)


class Run(Model):
 engine: Engine
 dataset_id: str
 epochs: int=Field(default=10,ge=1,le=100)
 batch_size: int=Field(default=1,ge=1,le=16)
 learning_rate: float=Field(default=0.0001,gt=0,le=0.01)


class Version(Model):
 name: str=Field(min_length=1,max_length=120)
 dataset_id: str
 run_id: str|None=None


class Confirm(Model):
 confirmed: bool=False


def subtract(segment,box):
 """Clip an opening out of a centerline, preserving the two remaining segments."""
 a,b=segment;dx=b.x-a.x;dy=b.y-a.y;lo,hi=0.,1.
 for origin,direction,left,right in ((a.x,dx,box.x,box.x+box.w),(a.y,dy,box.y,box.y+box.h)):
  if abs(direction)<1e-12:
   if origin<left or origin>right:return [segment]
  else:
   t1,t2=sorted(((left-origin)/direction,(right-origin)/direction));lo=max(lo,t1);hi=min(hi,t2)
 if lo>=hi:return [segment]
 def at(t):return Point(x=min(1,max(0,a.x+t*dx)),y=min(1,max(0,a.y+t*dy)))
 return ([(a,at(lo))] if lo>1e-8 else [])+([(at(hi),b)] if hi<1-1e-8 else [])


def normalize_labels(data,categories):
 for a in data.labels:
  if a.category not in categories or not categories[a.category]['active']:raise ValueError('Catégorie absente ou désactivée')
 openings=[a.bbox for a in data.labels if categories[a.category]['kind'] in ('opening','door')]
 seen=set()
 for a in data.labels:
  kind=categories[a.category]['kind']
  if kind!='wall' and a.segments:raise ValueError('Axes réservés aux murs')
  if kind=='wall':
   lines=a.segments
   for box in openings:lines=[s for segment in lines for s in subtract(segment,box)]
   if not lines:raise ValueError('Mur sans axe ; supprimer le mur entièrement ouvert')
   for p,q in lines:
    if math.hypot(p.x-q.x,p.y-q.y)<1e-6:raise ValueError('Axe de mur nul')
    key=tuple(sorted(((round(p.x,8),round(p.y,8)),(round(q.x,8),round(q.y,8)))))
    if key in seen:raise ValueError('Axe de mur dupliqué')
    seen.add(key)
   a.segments=lines
   xs=[p.x for s in lines for p in s];ys=[p.y for s in lines for p in s]
   x=max(0,min(xs)-.00001);y=max(0,min(ys)-.00001)
   a.bbox=Box(x=x,y=y,w=min(1-x,max(xs)-x+.00001),h=min(1-y,max(ys)-y+.00001))
  region=data.region
  points=[Point(x=a.bbox.x,y=a.bbox.y),Point(x=min(1,a.bbox.x+a.bbox.w),y=min(1,a.bbox.y+a.bbox.h))]
  if a.anchor:points.append(a.anchor)
  if any(p.x<region.x-1e-5 or p.y<region.y-1e-5 or p.x>region.x+region.w+1e-5 or p.y>region.y+region.h+1e-5 for p in points):
   raise ValueError('Annotation ou implantation hors du niveau sélectionné')
 return data


def authorized(c,project_id):
 row=c.execute('SELECT metadata FROM projects WHERE id=?',(project_id,)).fetchone()
 if not row or not json.loads(row[0]).get('training_authorized'):
  raise ValueError('Autorisation explicite de réutilisation du projet requise')


def row_example(c,ident):
 row=c.execute('SELECT * FROM training_examples WHERE id=?',(ident,)).fetchone()
 if not row:raise LookupError()
 value=dict(row);value['data']=json.loads(value['data']);return value


def row_dataset(c,ident):
 row=c.execute('SELECT * FROM training_datasets WHERE id=?',(ident,)).fetchone()
 if not row:raise LookupError()
 value=dict(row);value['snapshot']=json.loads(value['snapshot'])
 for pid in {e['project_id'] for e in value['snapshot']['examples']}:authorized(c,pid)
 return value


def split_examples(examples):
 # Union by building AND original document hash: duplicated documents cannot leak.
 parent={e['id']:e['id'] for e in examples}
 def find(x):
  while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
  return x
 keys={}
 for e in examples:
  for key in ('building:'+e['building_key'],'document:'+e['source']['sha256']):
   if key in keys:parent[find(e['id'])]=find(keys[key])
   else:keys[key]=e['id']
 groups={}
 for e in examples:groups.setdefault(find(e['id']),[]).append(e)
 # Stable ordering within this immutable snapshot. Each group has one split.
 ordered=sorted(groups.values(),key=lambda es:min(e['source']['sha256']+e['building_key'] for e in es))
 for i,group in enumerate(ordered):
  split='test' if len(ordered)>=3 and i==len(ordered)-1 else 'validation' if len(ordered)>=3 and i==len(ordered)-2 else 'train'
  for e in group:e['split']=split;e['split_group']=digest(sorted({x['building_key']+x['source']['sha256'] for x in group}))[:24]
 return len(groups)


def coco(snapshot):
 categories=[dict(id=i+1,name=c['name'],code=c['code']) for i,c in enumerate(snapshot['categories']) if c['kind']!='wall']
 ids={c['code']:c['id'] for c in categories};images=[];annotations=[];lookup={};seen=set()
 for e in snapshot['examples']:
  d=e['data'];source=e['source'];key=(source['sha256'],d['page'])
  if key not in lookup:
   lookup[key]=len(images)+1;images.append(dict(id=lookup[key],file_name=f"images/{lookup[key]}.png",width=source['page']['width'],height=source['page']['height'],split=e['split'],document_sha256=source['sha256'],page=d['page']))
  for a in d['labels']:
   if a['category'] not in ids:continue
   fingerprint=(lookup[key],digest(a))
   if fingerprint in seen:continue
   seen.add(fingerprint);b=a['bbox'];w=source['page']['width'];h=source['page']['height'];box=[b['x']*w,b['y']*h,b['w']*w,b['h']*h]
   annotations.append(dict(id=len(annotations)+1,image_id=lookup[key],category_id=ids[a['category']],bbox=box,area=box[2]*box[3],iscrowd=0,equipment_anchor=a['anchor'],transcription=a['text'],example_id=e['id']))
 return dict(images=images,annotations=annotations,categories=categories,info={'format':'doemo.training-coco/1','walls':'See examples.json centerlines; no invented segmentation masks'})


def attach_training(app,store,admin,get,doc):
 def cats(c):return {r['code']:dict(r) for r in c.execute('SELECT * FROM training_categories ORDER BY code')}
 def save_revision(c,value,who,action):
  c.execute('INSERT INTO training_revisions(example_id,revision,status,data,actor) VALUES(?,?,?,?,?)',(value['id'],value['revision'],value['status'],encoded(value['data']),who.login))
  audit(c,who.login,action,value['id'],{'revision':value['revision']})

 @app.get(PREFIX+'/openapi')
 def openapi(who=Depends(admin)):
  schema=app.openapi()
  return dict(schema,info={'title':'DOEMO Training API — backend OVH privé','version':'1.0.0'},paths={p:v for p,v in schema['paths'].items() if p.startswith(PREFIX)})

 @app.get(PREFIX+'/capabilities')
 def capabilities(who=Depends(admin)):
  return {'engines':{k:dict(v,inference_adapter=k!='architecture',training=False,evaluation=False,deployment=False,reference_versions=k=='qwen',driver_status='implemented_gpu_acceptance_pending' if k=='rtmdet' else 'not_implemented',reason='Entraînement non disponible : aucun pipeline GPU compatible validé et raccordé.',minimum_recommended_examples=100) for k,v in ENGINES.items()},'contract':'doemo.training/1'}

 @app.get(PREFIX+'/categories')
 def categories(who=Depends(admin)):
  with store.connect() as c:return list(cats(c).values())

 @app.put(PREFIX+'/categories/{code}')
 def category(code:str,data:Category,who=Depends(admin)):
  if code!=data.code:raise ValueError('Code incompatible')
  with store.connect() as c:
   c.execute('BEGIN IMMEDIATE');old=cats(c).get(code)
   if old and old['kind']!=data.kind:raise ValueError('Créer une nouvelle catégorie pour changer sa géométrie')
   c.execute('INSERT INTO training_categories VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET name=excluded.name,active=excluded.active',(code,data.name,data.kind,data.active))
   audit(c,who.login,'category.save',code)
  return data

 @app.get(PREFIX+'/examples')
 def examples(engine:Engine,project_id:str='',category:str='',status:str='',since:date|None=None,who=Depends(admin)):
  with store.connect() as c:
   values=[row_example(c,r[0]) for r in c.execute('SELECT id FROM training_examples WHERE engine=? ORDER BY updated DESC,id',(engine,))]
  return [e for e in values if (not project_id or e['project_id']==project_id) and (not status or e['status']==status) and (not since or e['updated'][:10]>=since.isoformat()) and (not category or any(a['category']==category for a in e['data']['labels']))]

 @app.post(PREFIX+'/examples')
 def create_example(data:Example,who=Depends(admin)):
  source,_=doc(data.project_id,data.document_id,who,data.page)
  if source['role']!='survey':raise ValueError('Choisir un relevé source')
  if data.revision!=0:raise Conflict('Une création commence à la révision zéro')
  with store.connect() as c:
   c.execute('BEGIN IMMEDIATE');normalize_labels(data,cats(c));ident=uuid.uuid4().hex
   c.execute('INSERT INTO training_examples(id,engine,project_id,document_id,page,revision,status,data,author) VALUES(?,?,?,?,?,0,?,?,?)',(ident,data.engine,data.project_id,data.document_id,data.page,'draft',data.model_dump_json(),who.login))
   value=row_example(c,ident);save_revision(c,value,who,'example.create');return value

 @app.put(PREFIX+'/examples/{ident}')
 def save_example(ident:str,data:Example,who=Depends(admin)):
  with store.connect() as c:
   c.execute('BEGIN IMMEDIATE');old=row_example(c,ident)
   if old['revision']!=data.revision:raise Conflict('Exemple modifié : recharger avant de sauvegarder')
   if any(old[k]!=getattr(data,k) for k in ('engine','project_id','document_id','page')):raise ValueError('Source immuable ; créer un nouvel exemple')
   normalize_labels(data,cats(c));data.revision+=1
   c.execute("UPDATE training_examples SET revision=?,status='draft',data=?,updated=CURRENT_TIMESTAMP WHERE id=?",(data.revision,data.model_dump_json(),ident))
   value=row_example(c,ident);save_revision(c,value,who,'example.save');return value

 @app.post(PREFIX+'/examples/{ident}/decision')
 def decision(ident:str,data:Decision,who=Depends(admin)):
  with store.connect() as c:
   c.execute('BEGIN IMMEDIATE');e=row_example(c,ident)
   if e['revision']!=data.revision:raise Conflict('Exemple modifié : recharger')
   if data.status=='validated':
    authorized(c,e['project_id']);v=Example.model_validate(e['data']);catalogue=cats(c);normalize_labels(v,catalogue)
    if not v.labels and not (v.engine=='qwen' and v.interpretation.strip()):raise ValueError('Ajouter une correction avant validation')
    for a in v.labels:
     kind=catalogue[a.category]['kind']
     if not a.checked:raise ValueError('Vérifier explicitement chaque annotation')
     if kind=='equipment' and not a.anchor:raise ValueError('Pointer l’implantation réelle de chaque équipement')
     if kind=='text' and not a.text.strip():raise ValueError('Renseigner la transcription exacte')
    if v.engine=='qwen' and not v.interpretation.strip():raise ValueError('Renseigner l’interprétation corrigée')
    if v.engine=='paddleocr' and (not v.labels or any(catalogue[a.category]['kind']!='text' for a in v.labels)):raise ValueError('Le dataset OCR requiert des régions de texte transcrites')
    if v.engine=='rtmdet' and (not v.labels or any(catalogue[a.category]['kind'] not in ('equipment','door','opening','other') for a in v.labels)):raise ValueError('Choisir des catégories de détection')
    if v.engine=='architecture' and (not v.labels or any(catalogue[a.category]['kind'] not in ('wall','door','opening') for a in v.labels)):raise ValueError('Choisir des murs, portes ou ouvertures')
   elif not data.reason.strip():raise ValueError('Indiquer le motif du rejet')
   e['data']['revision']+=1
   c.execute('UPDATE training_examples SET revision=revision+1,status=?,data=?,updated=CURRENT_TIMESTAMP WHERE id=?',(data.status,encoded(e['data']),ident))
   value=row_example(c,ident);save_revision(c,value,who,'example.'+data.status)
   audit(c,who.login,'example.decision_reason',ident,{'reason':data.reason});return value

 @app.get(PREFIX+'/datasets')
 def datasets(engine:Engine,who=Depends(admin)):
  with store.connect() as c:return [dict(r) for r in c.execute('SELECT id,engine,name,version,sha256,author,created FROM training_datasets WHERE engine=? ORDER BY created DESC,version DESC',(engine,))]

 @app.post(PREFIX+'/datasets')
 def create_dataset(data:Dataset,who=Depends(admin)):
  with store.connect() as c:
   c.execute('BEGIN IMMEDIATE');items=[];catalogue=cats(c)
   for ident in sorted(set(data.example_ids)):
    e=row_example(c,ident)
    if e['engine']!=data.engine or e['status']!='validated':raise ValueError('Sélectionner uniquement des exemples validés du même moteur')
    authorized(c,e['project_id']);p=get(e['project_id'],who);source,_=doc(e['project_id'],e['document_id'],who,e['page'])
    address=' '.join(p['metadata'].get('address','').casefold().split())
    e['building_key']=address or p['id'];e['source']={'sha256':source['sha256'],'name':source['name'],'page':source['pages'][e['page']-1]}
    e['transforms']=frames(e['source']['page'],e['data']['region'],e['data']['rotation']);items.append(e)
   groups=split_examples(items);used={a['category'] for e in items for a in e['data']['labels']}
   snapshot={'format':'doemo.training-dataset/1','engine':data.engine,'categories':[catalogue[x] for x in sorted(used)],'examples':items,'groups':groups,'split_policy':'connected_building_and_document','warnings':(['Au moins trois bâtiments/documents indépendants sont nécessaires pour séparer train, validation et test.'] if groups<3 else [])}
   version=c.execute('SELECT coalesce(max(version),0)+1 FROM training_datasets WHERE engine=? AND name=?',(data.engine,data.name.strip())).fetchone()[0]
   if not data.name.strip():raise ValueError('Nom de dataset requis')
   ident=uuid.uuid4().hex
   c.execute('INSERT INTO training_datasets(id,engine,name,version,snapshot,sha256,author) VALUES(?,?,?,?,?,?,?)',(ident,data.engine,data.name.strip(),version,encoded(snapshot),digest(snapshot),who.login))
   audit(c,who.login,'dataset.freeze',ident,{'version':version,'examples':len(items)});return row_dataset(c,ident)

 @app.get(PREFIX+'/datasets/{ident}')
 def dataset_get(ident:str,who=Depends(admin)):
  with store.connect() as c:return row_dataset(c,ident)

 @app.get(PREFIX+'/datasets/{ident}/export')
 def dataset_export(ident:str,who=Depends(admin)):
  with store.connect() as c:
   value=row_dataset(c,ident);snapshot=value['snapshot'];audit(c,who.login,'dataset.export',ident)
  # A complete bundle, with real source rasters, OCR crops and all geometry.
  output=io.BytesIO();total=0;seen=set();coco_data=coco(snapshot);ocr=[];qwen=[]
  with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as bundle:
   bundle.writestr('examples.json',encoded(snapshot));bundle.writestr('coco.json',encoded(coco_data))
   for e in snapshot['examples']:
    d=e['data'];source=e['source'];_,directory=doc(e['project_id'],e['document_id'],who,e['page'])
    path=directory/f"page-{e['page']}.png";total+=path.stat().st_size
    if total>256*1024**2:raise ValueError('Dataset trop volumineux pour cet export ; créer plusieurs versions plus petites')
    image=next(i for i in coco_data['images'] if i['document_sha256']==source['sha256'] and i['page']==e['page'])
    if image['id'] not in seen:bundle.write(path,image['file_name']);seen.add(image['id'])
    if value['engine']=='qwen':qwen.append({'image':image['file_name'],'split':e['split'],'messages':[{'role':'user','content':d['convention'] or 'Interpréter ce relevé.'},{'role':'assistant','content':d['interpretation']}]})
    if value['engine']=='paddleocr':
     with Image.open(path) as im:
      for a in d['labels']:
       b=a['bbox'];crop=im.crop((max(0,math.floor(b['x']*im.width)),max(0,math.floor(b['y']*im.height)),min(im.width,math.ceil((b['x']+b['w'])*im.width)),min(im.height,math.ceil((b['y']+b['h'])*im.height))))
       data=io.BytesIO();crop.save(data,'PNG');filename=f"ocr/{e['id']}-{a['id']}.png";bundle.writestr(filename,data.getvalue());ocr.append({'image':filename,'text':a['text'],'split':e['split'],'bbox':b,'example_id':e['id']})
   if ocr:bundle.writestr('ocr.jsonl','\n'.join(encoded(x) for x in ocr))
   if qwen:bundle.writestr('qwen.jsonl','\n'.join(encoded(x) for x in qwen))
  return Response(output.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="DOEMO-dataset-{ident}.zip"','Cache-Control':'private, no-store'})

 @app.get(PREFIX+'/models')
 def models(engine:Engine,who=Depends(admin)):
  with store.connect() as c:
   deployment=dict(c.execute('SELECT * FROM training_deployments WHERE engine=?',(engine,)).fetchone())
   rows=[dict(r) for r in c.execute('SELECT * FROM training_versions WHERE engine=? ORDER BY created DESC,id',(engine,))]
  for row in rows:row['manifest']=json.loads(row['manifest']);row['evaluation']=json.loads(row['evaluation']) if row['evaluation'] else None
  return dict(ENGINES[engine],engine=engine,deployment=deployment,versions=rows,base_status='Configuration d’inférence existante non attestée par ce registre' if engine!='architecture' else 'Moteur non implémenté')

 @app.post(PREFIX+'/models/{engine}/versions')
 def version(engine:Engine,data:Version,who=Depends(admin)):
  with store.connect() as c:
   c.execute('BEGIN IMMEDIATE');dataset=row_dataset(c,data.dataset_id)
   if dataset['engine']!=engine:raise ValueError('Dataset d’un autre moteur')
   if data.run_id:
    run=c.execute('SELECT * FROM training_runs WHERE id=? AND engine=?',(data.run_id,engine)).fetchone()
    if not run or run['status']!='completed' or run['dataset_id']!=data.dataset_id:raise ValueError('Un entraînement réellement terminé avec ce dataset est requis')
    # A trusted GPU artifact/evaluation ingestion adapter must be installed first.
    raise HTTPException(503,'Enregistrement de poids non disponible : vérification des artefacts GPU non raccordée')
   if engine!='qwen':raise ValueError('Un entraînement terminé est requis pour enregistrer des poids')
   rules={}
   for e in dataset['snapshot']['examples']:
    if e['split']!='train':continue
    key=e['data']['convention'].strip()
    if key:
     text=e['data']['interpretation']
     if key in rules and rules[key]!=text:raise ValueError('Convention avec interprétations contradictoires')
     rules[key]=text
   if not rules:raise ValueError('Ajouter des conventions Qwen dans les exemples train')
   ident=uuid.uuid4().hex;manifest={'kind':'reference','weights_trained':False,'rules':rules,'dataset_sha256':dataset['sha256'],'artifact_sha256':digest(rules),'parameters':{},'metrics':None,'logs':[]}
   c.execute('INSERT INTO training_versions(id,engine,name,method,dataset_id,status,manifest,author) VALUES(?,?,?,?,?,?,?,?)',(ident,engine,data.name,'reference',data.dataset_id,'development',encoded(manifest),who.login))
   audit(c,who.login,'version.save_reference',ident);return {'id':ident,'status':'development','method':'reference','weights_trained':False}

 @app.post(PREFIX+'/models/{engine}/{ident}/test')
 def test_version(engine:Engine,ident:str,who=Depends(admin)):
  with store.connect() as c:
   c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM training_versions WHERE id=? AND engine=?',(ident,engine)).fetchone()
   if not row:raise LookupError()
   if row['method']!='reference':raise HTTPException(503,'Évaluation GPU non disponible')
   dataset=row_dataset(c,row['dataset_id']);held=[e for e in dataset['snapshot']['examples'] if e['split']=='test']
   if not held:raise ValueError('Aucun document réservé au test dans ce dataset')
   rules=json.loads(row['manifest'])['rules'];active=c.execute('SELECT version_id FROM training_deployments WHERE engine=?',(engine,)).fetchone()[0]
   baseline=c.execute('SELECT manifest FROM training_versions WHERE id=?',(active,)).fetchone() if active else None
   previous=json.loads(baseline[0]).get('rules',{}) if baseline else {}
   def score(mapping):return sum(mapping.get(e['data']['convention'].strip())==e['data']['interpretation'] for e in held)/len(held)
   result={'scope':'reference_lookup_only','model_inference_tested':False,'test_examples':len(held),'candidate_exact_match':score(rules),'baseline_exact_match':score(previous),'baseline_version':active,'baseline_available':bool(baseline),'publication_eligible':False}
   c.execute('UPDATE training_versions SET evaluation=? WHERE id=?',(encoded(result),ident));audit(c,who.login,'version.test_reference',ident,result);return result

 @app.get(PREFIX+'/models/qwen/{ident}/reference')
 def reference(ident:str,q:str='',who=Depends(admin)):
  if len(q)>1000:raise ValueError('Recherche trop longue')
  with store.connect() as c:
   row=c.execute("SELECT manifest,dataset_id FROM training_versions WHERE id=? AND engine='qwen' AND method='reference'",(ident,)).fetchone()
   if not row:raise LookupError()
   row_dataset(c,row['dataset_id']);rules=json.loads(row['manifest'])['rules']
  query=q.casefold().strip()
  return {'version_id':ident,'method':'lexical_reference_lookup','weights_modified':False,
          'matches':[{'convention':k,'interpretation':v} for k,v in rules.items() if not query or query in k.casefold() or k.casefold() in query][:30]}

 @app.post(PREFIX+'/models/{engine}/{ident}/{action}')
 def model_action(engine:Engine,ident:str,action:Literal['approve','publish','rollback'],data:Confirm,who=Depends(admin)):
  with store.connect() as c:
   row=c.execute('SELECT * FROM training_versions WHERE id=? AND engine=?',(ident,engine)).fetchone()
   if not row:raise LookupError()
   row_dataset(c,row['dataset_id'])
   audit(c,who.login,'version.'+action+'.refused',ident,{'confirmed':data.confirmed})
  if not data.confirmed:raise ValueError('Confirmation explicite requise')
  if action=='approve':raise HTTPException(409,'Évaluation réelle du modèle et comparaison à la production requises ; le test du référentiel seul ne suffit pas')
  if row['status'] not in ('approved','production'):raise HTTPException(409,'Version approuvée requise')
  raise HTTPException(503,'Publication et retour arrière non disponibles : adaptateur d’activation GPU versionnée non raccordé')

 @app.get(PREFIX+'/runs')
 def runs(engine:Engine,who=Depends(admin)):
  with store.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM training_runs WHERE engine=? ORDER BY created DESC',(engine,))]

 @app.get(PREFIX+'/runs/{ident}')
 def run_status(ident:str,who=Depends(admin)):
  with store.connect() as c:
   row=c.execute('SELECT * FROM training_runs WHERE id=?',(ident,)).fetchone()
   if not row:raise LookupError()
   result=dict(row);result['parameters']=json.loads(result['parameters']);result['result']=json.loads(result['result']) if result['result'] else None
   return result

 @app.get(PREFIX+'/runs/{ident}/logs')
 def run_logs(ident:str,who=Depends(admin)):
  with store.connect() as c:
   if not c.execute('SELECT 1 FROM training_runs WHERE id=?',(ident,)).fetchone():raise LookupError()
   return [dict(r) for r in c.execute('SELECT * FROM training_audit WHERE entity=? ORDER BY id',(ident,))]

 @app.post(PREFIX+'/runs')
 def launch(data:Run,who=Depends(admin)):
  with store.connect() as c:
   dataset=row_dataset(c,data.dataset_id)
   if dataset['engine']!=data.engine:raise ValueError('Dataset incompatible')
   audit(c,who.login,'training.launch.refused',data.dataset_id,{'reason':'pipeline_unavailable','engine':data.engine})
  raise HTTPException(503,'Entraînement non disponible : aucun pipeline GPU compatible validé et raccordé. Aucun GPU démarré ni coût engagé.')

 @app.post(PREFIX+'/runs/{ident}/cancel')
 def cancel(ident:str,who=Depends(admin)):
  with store.connect() as c:
   row=c.execute('SELECT status FROM training_runs WHERE id=?',(ident,)).fetchone()
   if not row:raise LookupError()
   if row['status'] in ('completed','failed','cancelled'):raise Conflict('Tâche déjà terminée')
   audit(c,who.login,'training.cancel.refused',ident,{'reason':'pipeline_unavailable'})
  raise HTTPException(503,'Arrêt GPU non raccordé ; aucune interruption simulée')

 @app.get(PREFIX+'/audit')
 def journal(who=Depends(admin)):
  with store.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM training_audit ORDER BY id DESC LIMIT 200')]
