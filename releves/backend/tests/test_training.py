import io
import json
import zipfile
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from doemo_releves.api import create_app
from doemo_releves.store import Store
from doemo_releves.training import PREFIX,split_examples

@pytest.fixture
def api(tmp_path):
 return TestClient(create_app(tmp_path/'data'),headers={'X-Doemo-User':'admin','X-Doemo-Role':'admin'})

def source(api,color='white',address=''):
 p=api.post('/projects',json={'name':'Apprentissage','address':address}).json()
 b=io.BytesIO();Image.new('RGB',(100,100),color).save(b,'PNG')
 r=api.post('/projects/'+p['id']+'/documents',data={'role':'survey'},files={'file':('plan.png',b.getvalue(),'image/png')})
 assert r.status_code==200,r.text
 return api.get('/projects/'+p['id']).json()

def permit(api,p):
 r=api.put('/projects/'+p['id']+'/metadata',json={'training_authorized':True,'address':p['metadata'].get('address','')})
 assert r.status_code==200,r.text

def label(kind='HANDWRITING',**kw):
 return dict(id='a',category=kind,bbox={'x':.1,'y':.2,'w':.3,'h':.2},text='PCF',checked=True,**kw)

def example(api,engine='paddleocr',p=None,labels=None,**kw):
 p=p or source(api)
 r=api.post(PREFIX+'/examples',json=dict(engine=engine,project_id=p['id'],document_id=p['documents'][0]['id'],page=1,labels=labels if labels is not None else [label()],**kw))
 assert r.status_code==200,r.text
 return p,r.json()

def validate(api,p,e):
 permit(api,p);r=api.post(PREFIX+'/examples/'+e['id']+'/decision',json={'revision':e['revision'],'status':'validated'})
 assert r.status_code==200,r.text
 return r.json()

def dataset(api,engine,examples):
 r=api.post(PREFIX+'/datasets',json={'engine':engine,'name':'Dataset test','example_ids':[e['id'] for e in examples]})
 assert r.status_code==200,r.text
 return r.json()

@pytest.mark.parametrize('route',['capabilities','categories','examples?engine=qwen','datasets?engine=qwen','models?engine=qwen','runs?engine=qwen','audit','openapi'])
def test_every_training_page_requires_admin(api,route):
 assert api.get(PREFIX+'/'+route,headers={'X-Doemo-Role':'dessinateur'}).status_code==403


def test_examples_survive_restart_and_require_explicit_consent_and_review(api):
 p,e=example(api)
 r=api.post(PREFIX+'/examples/'+e['id']+'/decision',json={'revision':0,'status':'validated'})
 assert r.status_code==422 and 'Autorisation' in r.text
 e=validate(api,p,e)
 other=TestClient(create_app(api.app.state.store.root),headers={'X-Doemo-User':'admin','X-Doemo-Role':'admin'})
 assert other.get(PREFIX+'/examples?engine=paddleocr').json()[0]['status']=='validated'
 data=e['data'];data['labels'][0]['text']='CO₂'
 r=other.put(PREFIX+'/examples/'+e['id'],json=data);assert r.status_code==200
 assert r.json()['status']=='draft'
 assert other.put(PREFIX+'/examples/'+e['id'],json=data).status_code==409
 with Store(api.app.state.store.root).connect() as c:assert c.execute('SELECT count(*) FROM training_revisions').fetchone()[0]==3


def test_centerlines_preserve_opening_and_equipment_anchor_is_separate(api):
 wall=label('WALL',segments=[[{'x':.1,'y':.5},{'x':.9,'y':.5}]])
 opening=label('OPENING');opening.update(id='b',bbox={'x':.4,'y':.4,'w':.2,'h':.2})
 p,e=example(api,'architecture',labels=[wall,opening])
 segments=e['data']['labels'][0]['segments']
 assert len(segments)==2 and segments[0][1]['x']==pytest.approx(.4) and segments[1][0]['x']==pytest.approx(.6)
 validate(api,p,e)
 p,e=example(api,'rtmdet',labels=[label('FIRE')]);permit(api,p)
 assert api.post(PREFIX+'/examples/'+e['id']+'/decision',json={'revision':0,'status':'validated'}).status_code==422
 d=e['data'];d['labels'][0]['anchor']={'x':.8,'y':.9}
 e=api.put(PREFIX+'/examples/'+e['id'],json=d).json();validate(api,p,e)


def test_dataset_snapshot_immutable_complete_ocr_bundle_and_revocation(api):
 p,e=example(api);e=validate(api,p,e);d=dataset(api,'paddleocr',[e])
 assert d['snapshot']['groups']==1 and d['snapshot']['warnings']
 saved=d['sha256'];e['data']['labels'][0]['text']='H₂O'
 api.put(PREFIX+'/examples/'+e['id'],json=e['data'])
 assert api.get(PREFIX+'/datasets/'+d['id']).json()['sha256']==saved
 r=api.get(PREFIX+'/datasets/'+d['id']+'/export');assert r.status_code==200,r.text
 with zipfile.ZipFile(io.BytesIO(r.content)) as z:
  text=json.loads(z.read('ocr.jsonl'));assert text['text']=='PCF'
  with Image.open(io.BytesIO(z.read(text['image']))) as image:assert image.size==(30,20)
  assert 'images/1.png' in z.namelist() and 'examples.json' in z.namelist()
 api.put('/projects/'+p['id']+'/metadata',json={'training_authorized':False})
 assert api.get(PREFIX+'/datasets/'+d['id']+'/export').status_code==422


def test_connected_building_and_duplicate_document_never_leak_splits():
 values=[{'id':'a','building_key':'A','source':{'sha256':'shared'}}, {'id':'b','building_key':'B','source':{'sha256':'shared'}}, {'id':'c','building_key':'B','source':{'sha256':'other'}}, {'id':'d','building_key':'D','source':{'sha256':'d'}}, {'id':'e','building_key':'E','source':{'sha256':'e'}}]
 assert split_examples(values)==3
 assert values[0]['split']==values[1]['split']==values[2]['split']
 assert {v['split'] for v in values}=={'train','validation','test'}


def test_qwen_reference_is_saved_without_claiming_fine_tuning_or_publication(api):
 examples=[]
 for color in ('red','green','blue'):
  p=source(api,color);p,e=example(api,'qwen',p,[],convention='PCF',interpretation='Porte coupe-feu')
  examples.append(validate(api,p,e))
 d=dataset(api,'qwen',examples)
 r=api.post(PREFIX+'/models/qwen/versions',json={'name':'Conventions v1','dataset_id':d['id']});assert r.status_code==200,r.text
 v=r.json();assert v['weights_trained'] is False
 evaluation=api.post(PREFIX+'/models/qwen/'+v['id']+'/test').json()
 assert evaluation['candidate_exact_match']==1 and not evaluation['model_inference_tested']
 for action in ('approve','publish','rollback'):
  assert api.post(PREFIX+'/models/qwen/'+v['id']+'/'+action,json={'confirmed':True}).status_code==409
 assert api.get(PREFIX+'/models?engine=qwen').json()['deployment']['version_id'] is None
 assert api.get(PREFIX+'/models?engine=rtmdet').json()['versions']==[]
 assert api.post(PREFIX+'/runs',json={'engine':'qwen','dataset_id':d['id']}).status_code==503
 assert api.get(PREFIX+'/runs?engine=qwen').json()==[]


def test_rejected_or_foreign_engine_example_cannot_enter_dataset(api):
 p,e=example(api);permit(api,p)
 assert api.post(PREFIX+'/datasets',json={'engine':'paddleocr','name':'bad','example_ids':[e['id']]}).status_code==422
 e=validate(api,p,e)
 assert api.post(PREFIX+'/datasets',json={'engine':'rtmdet','name':'bad','example_ids':[e['id']]}).status_code==422
 r=api.post(PREFIX+'/examples/'+e['id']+'/decision',json={'revision':e['revision'],'status':'rejected','reason':'transcription erronée'})
 assert r.status_code==200
 assert api.post(PREFIX+'/datasets',json={'engine':'paddleocr','name':'bad','example_ids':[e['id']]}).status_code==422
