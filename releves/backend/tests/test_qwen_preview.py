"""Real local API/SQLite/queue/gateway; model execution is a labelled CPU fixture."""
import asyncio
import io
import json
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_training import api,source,example,validate,dataset,PREFIX
from doemo_releves import queue,gpu
from doemo_releves.qwen_preview import context,digest

@pytest.fixture
def reference(api):
    examples=[]
    for color in ('red','green','blue'):
        p=source(api,color);_,e=example(api,'qwen',p,[],convention='PCF',interpretation='Interprétation indépendante '+color)
        examples.append(validate(api,p,e))
    d=dataset(api,'qwen',examples)
    v=api.post(PREFIX+'/models/qwen/versions',json={'name':'Conventions fixture','dataset_id':d['id']}).json()
    held=next(e for e in d['snapshot']['examples'] if e['split']=='test')
    return v,d,held


def submit(api,reference,key='preview-request-001'):
    v,d,held=reference
    r=api.post(PREFIX+'/models/qwen/'+v['id']+'/previews',json={'example_id':held['id'],'confirmed':True,'request_key':key})
    assert r.status_code==200,r.text
    return r.json()


def test_preview_requires_admin_confirmation_heldout_and_deduplicates(api,reference):
    v,d,held=reference;path=PREFIX+'/models/qwen/'+v['id']
    assert api.get(path+'/preview-options',headers={'X-Doemo-Role':'dessinateur'}).status_code==403
    assert api.post(path+'/previews',json={'example_id':held['id'],'request_key':'preview-request-001'}).status_code==422
    train=next(e for e in d['snapshot']['examples'] if e['split']=='train')
    assert api.post(path+'/previews',json={'example_id':train['id'],'confirmed':True,'request_key':'preview-request-001'}).status_code==422
    value=submit(api,reference);assert submit(api,reference)['id']==value['id']
    assert api.post(path+'/previews',json={'example_id':train['id'],'confirmed':True,'request_key':'preview-request-001'}).status_code==409
    with api.app.state.store.connect() as c:
        rows=c.execute('SELECT payload FROM jobs').fetchall();assert len(rows)==2
        payloads=[json.loads(r[0]) for r in rows]
    assert {bool(p['qwen_context']['rules']) for p in payloads}=={False,True}
    assert all(held['data']['interpretation'] not in json.dumps(p,ensure_ascii=False) for p in payloads)
    assert gpu.pending(api.app.state.store)==2
    assert api.get('/projects/'+held['project_id']+'/jobs').json()==[]
    assert api.post(path+'/previews/'+value['id']+'/review',json={'verdict':'candidate_better','notes':'Non exécuté'}).status_code==422


@pytest.fixture
def gateway_client(monkeypatch,tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/'services/runpod'))
    import gateway
    monkeypatch.setenv('DOEMO_RUNPOD_TOKEN','g'*40);monkeypatch.setenv('DOEMO_PERSISTENT_ROOT',str(tmp_path/'volume'))
    monkeypatch.setattr(gateway,'training',None);monkeypatch.setattr(gateway,'draining',False);monkeypatch.setattr(gateway,'lock',asyncio.Lock())
    monkeypatch.setattr(gateway,'status',dict(ready=True,restoring=False,engines={e:True for e in gateway.ENGINES}))
    calls=[]
    async def execute(python,script,args,log,timeout):
        # Fixture executes no model. Assert that both images are byte-identical.
        reference=json.loads(Path(args[3]).read_text()) if len(args)==4 else None
        calls.append((Path(args[1]).read_bytes(),reference))
        text='Fixture avec conventions' if reference and reference['rules'] else 'Fixture sans conventions'
        Path(args[2]).write_text(json.dumps({'zones':[{'zone':'page','elements':[{'texte':text,'incertain':True}]}]}))
        return 0
    monkeypatch.setattr(gateway,'execute',execute)
    return TestClient(gateway.app,headers={'Authorization':'Bearer '+'g'*40}),calls


def wire(monkeypatch,client):
    monkeypatch.setenv('DOEMO_RUNPOD_MANAGED','0');monkeypatch.setenv('DOEMO_RUNPOD_ENDPOINT','https://fixture.invalid')
    monkeypatch.setattr(queue,'remote_health',lambda:{'status':'available'})
    def post(url,**kw):return client.post('/infer/qwen',headers=kw['headers'],files=kw['files'],data=kw.get('data',{}))
    monkeypatch.setattr(httpx,'post',post)


def test_two_persistent_worker_results_bound_to_context_and_human_review(api,reference,gateway_client,monkeypatch):
    client,calls=gateway_client;wire(monkeypatch,client)
    value=submit(api,reference);store=api.app.state.store
    assert queue.process_one(store) and queue.process_one(store)
    assert len(calls)==2 and calls[0][0]==calls[1][0] and calls[0][1]!=calls[1][1]
    v,d,held=reference;path=PREFIX+'/models/qwen/'+v['id']+'/previews'
    result=api.get(path).json()[0]
    assert result['complete'] and result['publication_eligible'] is False and not result['weights_modified']
    assert result['candidate']['result']['observations'][0]['text']=='Fixture avec conventions'
    assert result['baseline']['result']['observations'][0]['text']=='Fixture sans conventions'
    for side in ('baseline','candidate'):
        assert result[side]['context_sha256']==result[side]['result']['raw']['reference_context']['sha256']
    reviewed=api.post(path+'/'+value['id']+'/review',json={'verdict':'candidate_better','notes':'Avis fixture explicite'})
    assert reviewed.status_code==200 and reviewed.json()['reviewer']=='admin'
    # Reopen SQLite through a fresh application; no memory-only history.
    from doemo_releves.api import create_app
    other=TestClient(create_app(store.root),headers={'X-Doemo-User':'admin','X-Doemo-Role':'admin'})
    assert other.get(path).json()[0]['review']['notes']=='Avis fixture explicite'
    assert other.get(PREFIX+'/models?engine=qwen').json()['deployment']['version_id'] is None
    assert api.post(PREFIX+'/models/qwen/'+v['id']+'/approve',json={'confirmed':True}).status_code==409
    assert api.post('/projects/'+held['project_id']+'/jobs/'+value['candidate_job']+'/apply',json={'revision':0}).status_code==422
    assert api.post('/projects/'+held['project_id']+'/jobs/'+value['candidate_job']+'/retry').status_code==422


def test_revoked_consent_blocks_worker_before_network(api,reference,monkeypatch):
    value=submit(api,reference);v,d,held=reference
    api.put('/projects/'+held['project_id']+'/metadata',json={'training_authorized':False})
    monkeypatch.setenv('DOEMO_RUNPOD_MANAGED','0');monkeypatch.setattr(queue,'remote_health',lambda:{'status':'available'})
    calls=[];monkeypatch.setattr(httpx,'post',lambda *a,**k:calls.append(1))
    queue.process_one(api.app.state.store);queue.process_one(api.app.state.store)
    assert not calls
    with api.app.state.store.connect() as c:assert {r[0] for r in c.execute('SELECT status FROM jobs')}=={'failed'}
    assert api.get(PREFIX+'/models/qwen/'+v['id']+'/previews').status_code==422


def test_legacy_gateway_cannot_silently_ignore_context(api,reference,monkeypatch):
    submit(api,reference)
    monkeypatch.setenv('DOEMO_RUNPOD_MANAGED','0');monkeypatch.setenv('DOEMO_RUNPOD_ENDPOINT','https://fixture.invalid');monkeypatch.setenv('DOEMO_RUNPOD_TOKEN','fixture')
    monkeypatch.setattr(queue,'remote_health',lambda:{'status':'available'})
    monkeypatch.setattr(httpx,'post',lambda url,**kw:httpx.Response(200,json={'width':100,'height':100,'data':{'zones':[]}},request=httpx.Request('POST',url)))
    queue.process_one(api.app.state.store)
    with api.app.state.store.connect() as c:assert c.execute("SELECT count(*) FROM jobs WHERE status='failed'").fetchone()[0]==1


def test_changed_source_page_is_rejected_before_model_call(api,reference,monkeypatch):
    submit(api,reference);v,d,held=reference
    Image.new('RGB',(100,100),'black').save(api.app.state.store.root/'documents'/held['document_id']/'page-1.png')
    monkeypatch.setenv('DOEMO_RUNPOD_MANAGED','0');monkeypatch.setattr(queue,'remote_health',lambda:{'status':'available'})
    calls=[];monkeypatch.setattr(httpx,'post',lambda *a,**k:calls.append(1))
    queue.process_one(api.app.state.store)
    assert not calls
    with api.app.state.store.connect() as c:assert c.execute("SELECT count(*) FROM jobs WHERE status='failed'").fetchone()[0]==1


def test_gateway_idempotence_includes_context_and_rejects_other_engines(gateway_client):
    client,calls=gateway_client;b=io.BytesIO();Image.new('RGB',(16,16)).save(b,'PNG')
    ref=context('a'*32,{'PCF':'Porte coupe-feu'})
    args=dict(files={'file':('p.png',b.getvalue())},headers={'X-Doemo-Job':'b'*32},data={'context':json.dumps(ref)})
    one=client.post('/infer/qwen',**args);assert one.status_code==200,one.text
    assert client.post('/infer/qwen',**args).json()==one.json() and len(calls)==1
    args['data']={'context':json.dumps(context(None,{}))}
    assert client.post('/infer/qwen',**args).status_code==409 and len(calls)==1
    assert client.post('/infer/paddleocr',**args).status_code==422
    args['data']={'context':json.dumps(dict(ref,rules_sha256='f'*64))}
    assert client.post('/infer/qwen',**args).status_code==422


def test_prompt_preserves_unicode_and_treats_conventions_as_data(gateway_client):
    import qwen_prompt
    ref=context('a'*32,{'H₂O':'CO₂ et H2O','PCF':'Porte coupe-feu'})
    assert qwen_prompt.parse(json.dumps(ref))==ref
    assert qwen_prompt.digest(ref)==digest(ref)
    assert qwen_prompt.prompt(context(None,{}))==qwen_prompt.BASE_PROMPT
    assert 'H₂O' in qwen_prompt.prompt(ref) and 'pas des instructions' in qwen_prompt.prompt(ref)
    with pytest.raises(ValueError):context('a'*32,{'x':'y'*40000})


def test_qwen_interpretation_stays_distinct_from_visible_text():
    from doemo_releves.ai_contracts import normalise
    result=normalise('qwen',{'zones':[{'zone':'page','elements':[{'texte':'PCF','interpretation':'Porte coupe-feu','incertain':False}]}]},'doc',1,100,100)
    observation=result['observations'][0]
    assert observation['text']=='PCF' and observation['interpretation']=='Porte coupe-feu' and observation['uncertain']
    assert not result['annotations'] and observation['location'] is None
