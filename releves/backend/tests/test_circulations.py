import copy
import json
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon
from doemo_releves.api import create_app
from doemo_releves import circulations as g


def line(ident,points,role='wall',closed=False,filled=False,width=0):
    return dict(id=ident,role=role,nodes=[[*p,*p,*p] for p in points],closed=closed,filled=filled,stroke_width=width)


def source(paths=None,shell=None,texts=None):
    return g.Source(provider='illustrator',document_id='fixture-plan',source_name='fixture.ai',source_sha256='1'*64,architecture_sha256='2'*64,
        color_space='RGB',artboards=[(0,100,100,0)],levels=[dict(id='rdc',name='RDC',artboard=0,footprint=dict(shell=shell or [(0,0),(100,0),(100,100),(0,100)]))],
        paths=paths or [],texts=texts if texts is not None else [dict(text='Couloir',point=(15,50),level='rdc')])


def doorway():
    return source([line('w1',[(40,0),(40,45)],width=2),line('w2',[(40,55),(40,100)],width=2),line('seuil',[(40,45),(40,55)],role='door_threshold')],
                  texts=[dict(text='Couloir',point=(15,50),level='rdc'),dict(text='Bureau',point=(65,50),level='rdc')])


@pytest.mark.parametrize('shell',[
    [(0,0),(100,0),(100,100),(0,100)],
    [(0,0),(100,0),(100,20),(20,20),(20,100),(0,100)],
    [(0,70),(40,70),(40,0),(60,0),(60,70),(100,70),(100,100),(0,100)],
    [(0,0),(100,0),(100,100),(80,100),(80,20),(20,20),(20,100),(0,100)],
    [(10,0),(100,90),(90,100),(0,10)],
])
def test_rect_l_t_u_diagonal_preserve_true_outline(shell):
    s=source(shell=shell,texts=[]);result=g.reconstruct(s,g.Rules());assert len(result['regions'])==1
    assert g.poly(result['regions'][0]['shape']).symmetric_difference(Polygon(shell)).area<1e-6
    assert result['regions'][0]['status']=='proposed'


def test_threshold_prevents_room_fill_and_passage_is_not_closed():
    s=doorway();v=g.reconstruct(s,g.Rules());assert len(v['regions'])==2
    corridor=next(r for r in v['regions'] if r['category']=='circulation');room=next(r for r in v['regions'] if r['category']=='room')
    assert g.poly(corridor['shape']).intersection(g.poly(room['shape'])).area==0
    assert g.poly(corridor['shape']).bounds[2]==40
    s.paths[-1].role='passage';v=g.reconstruct(s,g.Rules());assert not any(r['suggested'] for r in v['regions'])
    assert any('incompatibles' in r['reason'] for r in v['regions'])


def test_incomplete_wall_never_snapped_across_a_gap():
    v=g.reconstruct(source([line('gap',[(40,0),(40,99)])]),g.Rules(gap_tolerance_pt=2))
    assert any('incomplètes' in w for w in v['warnings'])
    assert not any(r['suggested'] for r in v['regions'])


def test_obstacle_is_real_hole_existing_green_removed_not_recolored():
    obstacle=line('stair',[(30,30),(70,30),(70,70),(30,70)],role='obstacle',closed=True,filled=True)
    green=line('old',[(0,0),(10,0),(10,10),(0,10)],role='existing_green',closed=True,filled=True)
    v=g.reconstruct(source([obstacle,green]),g.Rules());assert sum(g.poly(r['shape']).area for r in v['regions'])==8300
    assert any(r['shape']['holes'] for r in v['regions'])


def test_hall_and_stair_rules_never_override_room_exclusion():
    assert g.classify(['HALL'],g.Rules())[0]=='unknown'
    assert g.classify(['HALL'],g.Rules(include=['hall']))[0]=='circulation'
    assert g.classify(['Couloir','Bureau'],g.Rules())[0]=='unknown'
    assert g.classify(['Escalier'],g.Rules())[0]=='technical'


def test_levels_disjoint_curves_and_invalid_geometry():
    s=source();s.levels.append(g.Level(id='etage',name='R+1',artboard=0,footprint=g.Shape(shell=[(0,0),(10,0),(10,10)])))
    with pytest.raises(ValueError):g.Source.model_validate(s.model_dump())
    curve=g.VectorPath(id='curve',nodes=[(0,0,0,0,0,50),(100,0,100,50,100,0)])
    pts=g.flatten(curve,.05);assert len(pts)>16 and max(p[1] for p in pts)>37
    with pytest.raises(ValueError):g.Shape(shell=[(0,0),(10,10),(0,10),(10,0)])


def test_edits_export_rejections_color_and_coordinate_safety():
    state=g.reconstruct(doorway(),g.Rules());ids=[r['id'] for r in state['regions']]
    g.edit(state,'reject',[ids[0]]);assert state['regions'][0]['status']=='rejected'
    with pytest.raises(ValueError):g.edit(state,'replace',[ids[0]],dict(shell=[(-5,0),(10,0),(10,10)]))
    with pytest.raises(ValueError):g.edit(state,'replace',[ids[0]],dict(shell=[(0,0),(99,0),(99,99),(0,99)]))
    g.edit(state,'accept',[ids[1]])
    with pytest.raises(ValueError):g.export(state)
    state['color']=dict(mode='RGB',values=[150,180,130],approved=True)
    result=g.export(state);assert len(result['regions'])==1 and result['native_ai_verified'] is False
    state['source']['provider']='pdf_audit'
    with pytest.raises(ValueError):g.export(state)


def test_merge_split_hole_require_revalidation():
    state=g.reconstruct(source(),g.Rules());r=state['regions'][0]
    g.edit(state,'split',[r['id']],[[50,-1],[50,101]])
    assert len(state['regions'])==2 and all(r['status']=='proposed' for r in state['regions'])
    g.edit(state,'merge',[r['id'] for r in state['regions']]);assert len(state['regions'])==1
    g.edit(state,'hole',[state['regions'][0]['id']],dict(shell=[(10,10),(20,10),(20,20),(10,20)]))
    assert g.poly(state['regions'][0]['shape']).area==9900


def test_api_versions_cache_permissions_history_learning_and_ai_labels(tmp_path):
    client=TestClient(create_app(tmp_path),headers={'X-Doemo-User':'alice','X-Doemo-Role':'admin'})
    project=client.post('/projects',json={'name':'Circulations'}).json();base='/projects/'+project['id']+'/circulations';payload={'source':doorway().model_dump()}
    response=client.post(base,json=payload);assert response.status_code==200,response.text
    state=response.json();path=base+'/fixture-plan'
    assert client.post(base,json=payload).json()['revision']==0
    assert client.get(path,headers={'X-Doemo-User':'bob','X-Doemo-Role':'dessinateur'}).status_code==404
    corridor=next(r for r in state['regions'] if r['category']=='circulation')
    assert client.get(path+'/point',params={'level':'rdc','x':15,'y':50}).json()==[corridor['id']]
    command={'revision':0,'operation':'accept','ids':[corridor['id']]}
    state=client.put(path,json=command).json();assert state['revision']==1
    assert client.put(path,json=command).status_code==409
    assert client.post(path+'/corrections').status_code==422
    assert client.put('/projects/'+project['id']+'/metadata',json={'training_authorized':True}).status_code==200
    ids=client.post(path+'/corrections').json()['ids'];assert len(ids)==1
    assert client.post(path+'/corrections').json()['ids']==ids
    rows=client.get('/projects/training/circulation-corrections').json();assert rows[0]['data']['region']['shape']==corridor['shape']
    restored=client.put(path,json={'revision':1,'operation':'restore','restore_revision':0}).json()
    assert restored['revision']==2 and all(r['status']=='proposed' for r in restored['regions'])
    assert len(client.get(path+'/history').json())==3
    assert client.post(path+'/ai-hints',json={'revision':2,'job_id':'absent'}).status_code==422
    # Corrections persist across application restart.
    again=TestClient(create_app(tmp_path),headers={'X-Doemo-User':'alice','X-Doemo-Role':'admin'})
    assert again.get(path).json()['revision']==2


def test_completed_ocr_hints_cannot_change_contours_or_rejected_regions(tmp_path):
    import io
    from PIL import Image
    client=TestClient(create_app(tmp_path),headers={'X-Doemo-User':'admin','X-Doemo-Role':'admin'})
    p=client.post('/projects',json={'name':'Source locale de test'}).json();image=io.BytesIO();Image.new('RGB',(100,100),'white').save(image,'PNG')
    client.post('/projects/'+p['id']+'/documents',data={'role':'survey'},files={'file':('fixture.png',image.getvalue(),'image/png')})
    p=client.get('/projects/'+p['id']).json();d=p['documents'][0];s=source(texts=[]);s.source_sha256=d['sha256']
    base='/projects/'+p['id']+'/circulations';v=client.post(base,json={'source':s.model_dump()}).json();path=base+'/fixture-plan'
    with client.app.state.store.connect() as c:
        c.execute('INSERT INTO jobs(id,project_id,actor,status,stage,payload,result) VALUES(?,?,?,?,?,?,?)',('ocr',p['id'],'admin','completed','fixture',json.dumps({'engine':'paddleocr','document_id':d['id'],'page':1}),json.dumps({'annotations':[{'text':'Couloir','bbox':{'x':.2,'y':.2,'w':.1,'h':.1}}]})))
    hints=client.post(path+'/ai-hints',json={'revision':0,'job_id':'ocr'}).json()
    assert hints['regions'][0]['shape']==v['regions'][0]['shape'] and hints['regions'][0]['category']=='circulation'
    assert hints['regions'][0]['status']=='proposed' and not hints['regions'][0]['suggested']
    rejected=client.put(path,json={'revision':1,'operation':'reject','ids':[v['regions'][0]['id']]}).json()
    final=client.post(path+'/ai-hints',json={'revision':2,'job_id':'ocr'}).json()
    assert final['regions'][0]['status']=='rejected'
    client.put('/projects/'+p['id']+'/metadata',json={'training_authorized':True})
    key=client.post(path+'/corrections').json()['ids'][0]
    reply=client.post('/projects/training/circulation-corrections/'+key+'/example',json={'source_document_id':d['id'],'page':1})
    assert reply.status_code==200,reply.text
    examples=client.get('/projects/training/examples?engine=qwen').json()
    assert len(examples)==1 and examples[0]['status']=='draft'
    assert '[0.0, 0.0, 100.0, 100.0]' in examples[0]['data']['convention']
    assert json.loads(examples[0]['data']['interpretation'])['correction_type']=='reject'
    assert client.post('/projects/training/circulation-corrections/'+key+'/example',json={'source_document_id':d['id'],'page':1}).json()==reply.json()
