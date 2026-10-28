"""Local fixtures: no real AI call, deployment or Illustrator DOM execution."""
import copy
import io
import json
import zipfile
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from doemo_releves.api import create_app
from doemo_releves.models import Annotation,Box,Point,ProjectState,Mapping
from doemo_releves.placement import prepare,business_type
from doemo_releves.queue import process_one
from doemo_releves import gpu
from doemo_releves.library import digest
from test_core import project_fixture,minimal_pdf


def setup(tmp_path,data_root=None,owner="designer"):
    c=TestClient(create_app(data_root or tmp_path/'private'),headers={'X-Doemo-User':owner,'X-Doemo-Role':'dessinateur'})
    store=c.app.state.store;p,library=project_fixture();ident=store.create(owner,'Pose fixture')
    library['name']='SAI fixture';library['warnings']=[];library['assets']=[]
    for aid,name in [('pcf','Porte coupe-feu'),('ext','Extincteur portatif'),('vei','Vous êtes ici')]:
        directory=store.root/'libraries/sai'/aid;directory.mkdir(parents=True)
        resource=directory/'file.ai';resource.write_bytes(minimal_pdf())
        Image.new('RGB',(30,30),'red' if aid=='ext' else 'green').save(directory.parent/(aid+'.png'))
        library['assets'].append(dict(id=aid,name=name,type='graphic',groups=[],approved=True,verified=True,pictogram_candidate=True,preview=True,
            components=[{'role':'primary','archive_path':aid+'/file.ai','sha256':digest(resource)}]))
    store.put_library(library)
    with store.connect() as con:
        for d in p['documents']:con.execute('INSERT INTO documents VALUES(?,?,?)',(d['id'],ident,json.dumps({k:v for k,v in d.items() if k!='id'})))
        for code,asset in [('PCF','pcf'),('EXT_PORTATIF','ext'),('VEI','vei')]:
            row=json.loads(con.execute('SELECT data FROM equipment_catalogue WHERE code=?',(code,)).fetchone()[0]);row['asset_id']=asset
            con.execute('UPDATE equipment_catalogue SET data=? WHERE code=?',(json.dumps(row),code))
    directory=store.root/'documents/survey';directory.mkdir(parents=True);Image.new('RGB',(1000,1000),'white').save(directory/'page-1.png')
    state=ProjectState.model_validate(p['state']);state.revision=0;state.annotations=[];state.mappings=[]
    state.floors[0].source_document_id='survey';state.floors[0].source_region=Box(x=0,y=0,w=1,h=1)
    store.save(ident,'designer',state)
    return c,ident,library


def mark(ident,text,anchor=True):
    return Annotation(id=ident,source_document_id='survey',source_page=1,bbox=Box(x=.1,y=.1,w=.08,h=.05),text=text,
        anchor=Point(x=.7,y=.8) if anchor else None,anchor_kind='arrow_tip' if anchor else 'unknown')


@pytest.mark.parametrize('text,expected',[('PCF','PCF'),('porte coupe-feu','PCF'),('CO₂','EXT_PORTATIF'),('H₂O','EXT_PORTATIF'),('EXT 6L','EXT_PORTATIF'),('PE','VEI'),('Vous êtes ici','VEI'),('réserve',None),('PCF ?', None)])
def test_business_types(text,expected):
    assert business_type(text)==expected


def test_from_multimodal_queue_to_real_bundle_with_explicit_review(tmp_path,monkeypatch):
    c,ident,library=setup(tmp_path);store=c.app.state.store
    monkeypatch.setenv('DOEMO_RUNPOD_MANAGED','1');monkeypatch.setenv('DOEMO_RUNPOD_POD_ID','fixture-unused')
    monkeypatch.setenv('DOEMO_VISION_ENDPOINT','https://fixture.invalid/chat');monkeypatch.setenv('DOEMO_VISION_MODEL','fixture')
    import doemo_releves.worker as worker
    marks=[mark('pcf1','PCF'),mark('ext1','H₂O'),mark('ext2','CO₂'),mark('vei1','PE'),mark('unknown','???',False)]
    marks[2].anchor=Point(x=.6,y=.8) # Distinct extinguishers must both survive.
    def local_fixture(kind,payload):
        assert kind=='recognition' and payload['mode']=='multimodal'
        return {'annotations':[a.model_dump() for a in marks],'report':{'warnings':[]}}
    monkeypatch.setattr(worker,'run_job',local_fixture)
    r=c.post(f'/projects/{ident}/jobs',json={'document_id':'survey','page':1,'engine':'multimodal'});assert r.status_code==200,r.text
    job=r.json()['id'];assert gpu.pending(store,gpu_only=True)==0
    assert process_one(store)
    revision=c.get(f'/projects/{ident}').json()['state']['revision']
    r=c.post(f'/projects/{ident}/jobs/{job}/apply',json={'revision':revision});assert r.status_code==200,r.text
    body={'document_id':'survey','page':1,'revision':r.json()['state']['revision']}
    r=c.post(f'/projects/{ident}/prepare-placements',json=body);assert r.status_code==200,r.text
    result=r.json();s=result['project']['state'];a=s['annotations']
    assert [x['asset_id'] for x in a]==['pcf','ext','ext','vei',None]
    assert a[0]['anchor']=={'x':.7,'y':.8} and a[0]['bbox']['x']==.1
    assert a[-1]['anchor'] is None and a[-1]['equipment_type']==''
    assert result['summary']['preview_ready']==4 and not any(a[0]['review'].values())
    assert c.get(f'/projects/{ident}/bundle').status_code==422
    assert c.post(f'/projects/{ident}/prepare-placements',json=body).status_code==409
    assert c.post(f'/projects/{ident}/prepare-placements',json=dict(body,revision=s['revision']),headers={'X-Doemo-User':'other'}).status_code==404
    # Repeating the operation keeps annotation IDs and mapping version stable.
    again=c.post(f'/projects/{ident}/prepare-placements',json=dict(body,revision=s['revision'])).json()['project']['state']
    assert again==s
    for x in s['annotations']:
        if x['id']=='unknown':x['status']='rejected'
        else:x['status']='confirmed';x['review']={k:True for k in x['review']}
    for m in s['mappings']:m['confirmed']=True
    r=c.put(f'/projects/{ident}/state',json=s);assert r.status_code==200,r.text
    bundle=c.get(f'/projects/{ident}/bundle');assert bundle.status_code==200,bundle.text
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as z:
        exchange=json.loads(z.read('placements.json'))
        assert len(exchange['placements'])==4
        assert exchange['placements'][0]['x']==pytest.approx(350) and exchange['placements'][0]['y']==pytest.approx(400)
        assert {p['equipment_type'] for p in exchange['placements']}=={'PCF','EXT_PORTATIF','VEI'}
        for asset in ('pcf','ext','vei'):assert z.read(f'library/{asset}/file.ai')==minimal_pdf()
        assert b'#target illustrator' in z.read('DOEMO-Pose-Pictogrammes.jsx')
        assert 'doemo-core.js' in z.namelist()
    assert c.get(f'/libraries/sai/assets/vei/preview').content.startswith(b'\x89PNG')


def test_prepare_preserves_corrections_refuses_wrong_asset_and_ambiguity(tmp_path):
    c,ident,library=setup(tmp_path);state=ProjectState.model_validate(c.get(f'/projects/{ident}').json()['state'])
    corrected=mark('manual','PCF');corrected.equipment_type='DM';corrected.review.equipment=True;corrected.comment='Conserver'
    confirmed=mark('confirmed','PCF');confirmed.status='confirmed'
    state.annotations=[corrected,confirmed,mark('ambiguous','EX')]
    state.mappings=[Mapping(annotation='EX',equipment_type='PCF',asset_id='pcf',confirmed=True),Mapping(annotation='EX',equipment_type='EXT_PORTATIF',asset_id='ext',confirmed=True)]
    catalogue=[{'code':'PCF','active':True,'name':'Porte coupe-feu','asset_id':'ext'}]
    before=confirmed.model_dump();prepare(state,library,catalogue,'survey',1)
    assert state.annotations[0].equipment_type=='DM' and state.annotations[0].review.equipment and state.annotations[0].comment=='Conserver'
    assert state.annotations[1].model_dump()==before and state.annotations[2].asset_id is None
    state.annotations=[mark('wrong','PCF')];prepare(state,library,catalogue,'survey',1)
    assert state.annotations[0].asset_id is None
    # Only one exact, approved library-name match may fill a missing catalogue entry.
    state.annotations=[mark('vei','VEI')];prepare(state,library,[],'survey',1);assert state.annotations[0].asset_id=='vei'
    library['assets'].append(dict(library['assets'][-1],id='another-vei'))
    state.annotations=[mark('vei2','VEI')];prepare(state,library,[],'survey',1);assert state.annotations[0].asset_id is None
