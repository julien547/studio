import io
import json
from PIL import Image
from fastapi.testclient import TestClient
from doemo_releves.api import create_app
from test_core import minimal_pdf, project_fixture


def client(tmp_path):
    return TestClient(create_app(tmp_path/'private'),headers={'X-Doemo-User':'designer','X-Doemo-Role':'dessinateur'})


def test_owner_revision_and_orphan_guards(tmp_path):
    c=client(tmp_path)
    p=c.post('/projects',json={'name':'Audit'}).json();ident=p['id']
    assert c.get('/projects/'+ident,headers={'X-Doemo-User':'other'}).status_code==404
    assert c.get('/projects/'+ident,headers={'X-Doemo-Role':'technicien'}).status_code==403
    state=p['state'];state['revision']=99
    assert c.put(f'/projects/{ident}/state',json=state).status_code==409
    state['revision']=0
    assert c.put(f'/projects/{ident}/state',json=state).json()['state']['revision']==1
    assert c.get(f'/projects/{ident}/placements').status_code==422
    assert c.get('/projects/../../etc/passwd').status_code==404


def test_real_upload_render_and_access_control(tmp_path):
    c=client(tmp_path);p=c.post('/projects',json={'name':'Photo'}).json();ident=p['id']
    buffer=io.BytesIO();Image.new('RGB',(100,80),'white').save(buffer,'PNG')
    r=c.post(f'/projects/{ident}/documents',data={'role':'survey'},files={'file':('plan.png',buffer.getvalue(),'image/png')})
    assert r.status_code==200,r.text
    d=r.json()['documents'][0]
    assert d['pages'][0]['width']==100
    assert c.get(f'/projects/{ident}/documents/{d["id"]}/pages/1').content.startswith(b'\x89PNG')
    assert c.get(f'/projects/{ident}/documents/{d["id"]}/pages/1',headers={'X-Doemo-User':'other'}).status_code==404
    assert c.get(f'/projects/{ident}/documents/{d["id"]}/pages/2').status_code==404
    bad=c.post(f'/projects/{ident}/documents',data={'role':'survey'},files={'file':('x.pdf',b'invalid')})
    assert bad.status_code==422
    # A PDF uploaded under a wrong survey extension is rejected before parsing.
    assert c.post(f'/projects/{ident}/documents',data={'role':'survey'},files={'file':('x.exe',minimal_pdf())}).status_code==422
    renamed=c.post(f'/projects/{ident}/documents',data={'role':'target'},files={'file':('fake.ai',minimal_pdf())})
    assert renamed.status_code==422 and 'renommé' in renamed.json()['detail']


def test_library_requires_admin_and_no_phantom_reports(tmp_path):
    c=client(tmp_path)
    assert c.post('/libraries',files={'inventory':('x.json',b'{}')}).status_code==403
    p=c.post('/projects',json={'name':'A'}).json()
    assert c.post('/projects/'+p['id']+'/illustrator-reports',files={'file':('report.json',b'{}')}).status_code==422
    assert c.get('/projects/'+p['id']+'/illustrator-reports').json()==[]


def test_bundle_contains_exact_vector_bytes_and_native_scripts(tmp_path):
    import zipfile
    from doemo_releves.models import ProjectState
    from doemo_releves.library import digest
    c=client(tmp_path);store=c.app.state.store
    p,library=project_fixture();ident=store.create('designer','Synthetic verified exchange')
    directory=store.root/'libraries/sai/asset';directory.mkdir(parents=True)
    resource=directory/'file.ai';resource.write_bytes(minimal_pdf())
    library['assets'][0]['components'][0]['sha256']=digest(resource)
    store.put_library(library)
    with store.connect() as connection:
        for d in p['documents']:
            connection.execute('INSERT INTO documents VALUES(?,?,?)',(d['id'],ident,json.dumps({k:v for k,v in d.items() if k!='id'})))
    state=ProjectState.model_validate(p['state']);state.revision=0
    store.save(ident,'designer',state)
    response=c.get(f'/projects/{ident}/bundle')
    assert response.status_code==200,response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.read('library/asset/file.ai')==minimal_pdf()
        assert b'#target illustrator' in archive.read('DOEMO-Pose-Pictogrammes.jsx')
        exchange=json.loads(archive.read('placements.json'))
        assert exchange['project_id']==ident and not exchange['report']['native_ai_verified']
    resource.write_bytes(b'modified')
    assert c.get(f'/projects/{ident}/bundle').status_code==422
