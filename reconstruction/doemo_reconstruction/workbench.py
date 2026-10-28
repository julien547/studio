"""Authenticated PHP -> local Unix socket workbench. No RunPod lifecycle control."""
import base64
from contextlib import asynccontextmanager, contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException
import httpx
from PIL import Image

from .geometry import validate
from .export import export_svg, connector_payload, training_records
from .ai_service.jobs import canonical
from .ai_service.auth import issue
from .ai_service.contracts import validate_request
from .ai_service.evidence import attach_evidence
from .ai_service.limits import BodyLimit
from .connection import connection_status, inspect_worker, ENGINES


class Conflict(ValueError):
    pass


class Workbench:
    def __init__(self, root, remote_url='', key_path=''):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.remote_url, self.key_path = remote_url.rstrip('/'), key_path
        if remote_url:
            from urllib.parse import urlsplit
            url = urlsplit(remote_url)
            if (not url.hostname or url.username or url.password or url.query or url.fragment
                    or url.path not in ('', '/') or not (url.scheme == 'https' or
                    (url.scheme == 'http' and url.hostname in ('127.0.0.1', '::1')))):
                raise ValueError('HTTPS ou tunnel local requis')
        self.stop = threading.Event()
        with self.db() as db:
            db.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
                page INTEGER NOT NULL, created REAL NOT NULL, version INTEGER NOT NULL DEFAULT 0,
                document TEXT);
              CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, kind TEXT NOT NULL,
                status TEXT NOT NULL, created REAL NOT NULL, result TEXT, error TEXT);
              CREATE TABLE IF NOT EXISTS saves (
                project TEXT NOT NULL, version INTEGER NOT NULL, actor TEXT NOT NULL,
                created REAL NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(project,version));
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.root / 'workbench.sqlite3', timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def project(self, actor, project_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM projects WHERE id=? AND owner=?', (project_id, actor)).fetchone()
        if row is None:
            raise KeyError('Projet introuvable')
        out = dict(row)
        out['document'] = json.loads(out['document']) if out['document'] else None
        return out

    def projects(self, actor):
        with self.db() as db:
            return [dict(row) for row in db.execute(
                'SELECT id,name,page,created,version,document IS NOT NULL AS available '
                'FROM projects WHERE owner=? ORDER BY created DESC LIMIT 100', (actor,))]

    def upload(self, actor, body):
        data = base64.b64decode(body['content'], validate=True)
        page = body.get('page', 1)
        name = body.get('name', 'Plan')
        if (not data or len(data) > 20 * 1024**2 or type(page) is not int or not 1 <= page <= 10000
                or not isinstance(name, str) or not 1 <= len(name) <= 160 or any(ord(c) < 32 for c in name)):
            raise ValueError('Fichier ou page invalide')
        if data[:5] != b'%PDF-':
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('PNG', 'JPEG') or image.width * image.height > 20_000_000:
                    raise ValueError('PNG/JPEG de moins de 20 mégapixels requis')
                image.verify()
            if page != 1:
                raise ValueError('Une image ne contient qu’une page')
        project_id, task_id = str(uuid.uuid4()), str(uuid.uuid4())
        directory = self.root / project_id
        directory.mkdir(mode=0o700)
        (directory / 'source').write_bytes(data)
        with self.db() as db:
            db.execute('INSERT INTO projects(id,owner,name,page,created) VALUES(?,?,?,?,?)',
                       (project_id, actor, name, page, time.time()))
            db.execute('INSERT INTO tasks(id,project,kind,status,created) VALUES(?,?,?,?,?)',
                       (task_id, project_id, 'geometry', 'queued', time.time()))
        return {'id': project_id, 'task_id': task_id}

    def save(self, actor, project_id, body):
        doc = validate(body['document'])
        version = body['expected_version']
        if type(version) is not int:
            raise ValueError('Version invalide')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM projects WHERE id=? AND owner=?', (project_id, actor)).fetchone()
            if row is None:
                raise KeyError('Projet introuvable')
            if row['version'] != version or row['document'] is None:
                raise Conflict('Projet modifié ailleurs : recharger avant de sauvegarder')
            old = json.loads(row['document'])
            if doc['source'] != old['source'] or len(doc['levels']) != len(old['levels']):
                raise ValueError('Source différente')
            for level, before in zip(doc['levels'], old['levels']):
                for key in ('id', 'source_page', 'width', 'height', 'unit', 'coordinate', 'reference'):
                    if level.get(key) != before.get(key):
                        raise ValueError('Référence ou coordonnées modifiées')
                if level.get('scale') and level.get('scale') != before.get('scale'):
                    level['scale']['validated_by'] = actor
            if not isinstance(doc.get('history'), list) or len(doc['history']) > 3000:
                raise ValueError('Historique invalide')
            previous = old.get('history', [])
            if doc['history'][:len(previous)] != previous:
                raise ValueError('Historique serveur modifié')
            for entry in doc['history'][len(previous):]:
                entry['actor'] = actor
            encoded = canonical(doc)
            db.execute('UPDATE projects SET document=?,version=version+1 WHERE id=?', (encoded, project_id))
            db.execute('INSERT INTO saves VALUES(?,?,?,?,?)',
                       (project_id, version + 1, actor, time.time(), hashlib.sha256(encoded.encode()).hexdigest()))
        return {'version': version + 1, 'document': doc}

    def enqueue_ai(self, actor, project_id):
        project = self.project(actor, project_id)
        if not project['document']:
            raise Conflict('Extraction non terminée')
        if not self.remote_url or not self.key_path:
            raise Conflict('Connexion RunPod non configurée sur OVH')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT id FROM tasks WHERE project=? AND kind='ai' AND status IN ('queued','running','interrupted')",
                          (project_id,)).fetchone():
                raise Conflict('Une analyse existe déjà ou attend une vérification après interruption')
            task_id = str(uuid.uuid4())
            db.execute('INSERT INTO tasks(id,project,kind,status,created) VALUES(?,?,?,?,?)',
                       (task_id, project_id, 'ai', 'queued', time.time()))
        return {'task_id': task_id}

    def task(self, actor, task_id):
        with self.db() as db:
            row = db.execute('SELECT t.* FROM tasks t JOIN projects p ON p.id=t.project '
                             'WHERE t.id=? AND p.owner=?', (task_id, actor)).fetchone()
        if row is None:
            raise KeyError('Travail introuvable')
        return dict(row)

    def remote(self, method, path, payload=None, timeout=20):
        key = Path(self.key_path).read_bytes()
        with httpx.Client(base_url=self.remote_url, timeout=timeout, follow_redirects=False) as client:
            response = client.request(method, path, json=payload, headers={
                'Authorization': 'Bearer ' + issue(key, 'doemo-runpod', 'worker')})
            response.raise_for_status()
            return response.json()

    def ai_result(self, project, task_id):
        doc = project['document']
        level = doc['levels'][0]
        data = base64.b64decode(level['reference'].split(',', 1)[1], validate=True)
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
        state, health, versions, _ = inspect_worker(self.remote)
        if state != 'ready':
            raise Conflict('RunPod non prêt ; vérifier le panneau Serveur IA')
        names = list(ENGINES)
        request, _ = validate_request({'project_id': project['id'], 'page': level['source_page'],
            'source_sha256': doc['source']['sha256'], 'image_sha256': hashlib.sha256(data).hexdigest(),
            'image_base64': base64.b64encode(data).decode(), 'width': width, 'height': height,
            'regions': [], 'engines': names, 'model_versions': {name: versions[name] for name in names},
            'parameters': {'diagnostic_only': True}})
        result = self.remote('POST', '/infer/' + task_id, request, timeout=2800)
        if (result.get('job_id') != task_id or result.get('model_versions') != request['model_versions']
                or set(result.get('engines', {})) != set(names)
                or result.get('executed_on') != {k: health[k] for k in ('pod_id', 'worker_instance_id')}):
            raise ValueError('Résultat RunPod incohérent')
        for name in names:
            if result['engines'][name].get('model_version') != versions[name] or result['engines'][name].get('engine') != name:
                raise ValueError('Moteur ou version incohérente')
        attach_evidence(doc, level['id'], result, request)
        return result, request

    def process_once(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return False
            task = dict(row)
            db.execute("UPDATE tasks SET status='running' WHERE id=?", (task['id'],))
            project = dict(db.execute('SELECT * FROM projects WHERE id=?', (task['project'],)).fetchone())
            project['document'] = json.loads(project['document']) if project['document'] else None
        try:
            if task['kind'] == 'geometry':
                directory = self.root / project['id']
                output = directory / 'extracted.json'
                command = ['/usr/bin/timeout', '--kill-after=5', '180', '/usr/bin/prlimit',
                           '--as=3221225472', '--cpu=170', '--fsize=67108864', sys.executable,
                           '-m', 'doemo_reconstruction.cli', 'reconstruct', str(directory / 'source'),
                           str(output), '--pages', str(project['page'])]
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           start_new_session=True)
                try:
                    if process.wait(timeout=190):
                        raise ValueError('Extraction échouée')
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    raise
                document = validate(json.loads(output.read_text()))
                document['source']['name'] = project['name']
                result = {'walls_pending': sum(len(l['walls']) for l in document['levels']),
                          'segmentation_qualified': False}
            else:
                result, request = self.ai_result(project, task['id'])
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                if task['kind'] == 'ai':
                    # Merge observations into the latest saved drawing, never the older submitted snapshot.
                    latest = json.loads(db.execute('SELECT document FROM projects WHERE id=?',
                                                   (project['id'],)).fetchone()['document'])
                    document = attach_evidence(latest, latest['levels'][0]['id'], result, request)
                db.execute('UPDATE projects SET document=?,version=version+1 WHERE id=?',
                           (canonical(document), project['id']))
                db.execute("UPDATE tasks SET status='completed',result=? WHERE id=?", (canonical(result), task['id']))
        except Exception as error:
            # Ambiguous network/server outcomes can mean the remote GPU is still working: no automatic retry.
            uncertain = task['kind'] == 'ai' and (isinstance(error, httpx.TransportError) or
                         (isinstance(error, httpx.HTTPStatusError) and error.response.status_code >= 500))
            with self.db() as db:
                db.execute('UPDATE tasks SET status=?,error=? WHERE id=?',
                           ('interrupted' if uncertain else 'failed',
                            'Résultat à vérifier sur RunPod avant toute relance.' if uncertain else
                            'Traitement échoué : vérifier le fichier et la configuration du service.', task['id']))
        return True

    def loop(self):
        while not self.stop.is_set():
            if not self.process_once():
                self.stop.wait(1)


def create_app(workbench, start_worker=True):
    @asynccontextmanager
    async def lifespan(app):
        with workbench.db() as db:
            db.execute("UPDATE tasks SET status='interrupted',error='Service redémarré : résultat à vérifier.' WHERE status='running'")
        if start_worker:
            threading.Thread(target=workbench.loop, daemon=True).start()
        yield
        workbench.stop.set()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(BodyLimit, limit=32 * 1024**2)

    def actor(x_doemo_user: str = Header(default='')):
        if not x_doemo_user or len(x_doemo_user) > 128 or any(ord(c) < 32 for c in x_doemo_user):
            raise HTTPException(401, 'Session requise')
        return x_doemo_user

    def safe(call):
        try:
            return call()
        except KeyError:
            raise HTTPException(404, 'Projet ou travail introuvable')
        except Conflict as error:
            raise HTTPException(409, str(error))
        except (ValueError, TypeError, IndexError, AttributeError):
            raise HTTPException(422, 'Document ou demande invalide')

    @app.get('/health')
    def health(user=Depends(actor)):
        return {'ready': True, 'version': '0.3.1', 'runpod_configured': bool(workbench.remote_url and workbench.key_path),
                'runpod_inference_verified': False, 'specialized_segmentation': 'not_qualified', 'user': user}

    @app.get('/runpod/status')
    def runpod_status(user=Depends(actor)):
        return connection_status(bool(workbench.remote_url and workbench.key_path), workbench.remote)

    @app.get('/projects')
    def listing(user=Depends(actor)):
        return workbench.projects(user)

    @app.post('/projects', status_code=202)
    def upload(body: dict, user=Depends(actor)):
        return safe(lambda: workbench.upload(user, body))

    @app.get('/projects/{project_id}')
    def project(project_id: str, user=Depends(actor)):
        return safe(lambda: workbench.project(user, project_id))

    @app.post('/projects/{project_id}/save')
    def save(project_id: str, body: dict, user=Depends(actor)):
        return safe(lambda: workbench.save(user, project_id, body))

    @app.post('/projects/{project_id}/analyze', status_code=202)
    def analyze(project_id: str, user=Depends(actor)):
        return safe(lambda: workbench.enqueue_ai(user, project_id))

    @app.get('/tasks/{task_id}')
    def task(task_id: str, user=Depends(actor)):
        return safe(lambda: workbench.task(user, task_id))

    @app.get('/projects/{project_id}/export/{kind}')
    def export(project_id: str, kind: str, user=Depends(actor)):
        def make():
            doc = workbench.project(user, project_id)['document']
            if doc is None:
                raise Conflict('Extraction non terminée')
            if kind in ('svg', 'preview'):
                return {'content': export_svg(doc['levels'][0], kind == 'svg'), 'extension': 'svg'}
            if kind == 'illustrator':
                return {'content': canonical(connector_payload(doc)), 'extension': 'json'}
            if kind == 'training':
                return {'content': '\n'.join(canonical(r) for r in training_records(doc)), 'extension': 'jsonl'}
            raise KeyError()
        return safe(make)
    return app


def main():
    import uvicorn
    # Deliberately no TCP bind option. Only the session-authenticated PHP bridge may access this socket.
    socket = os.environ.get('DOEMO_REDESSIN_SOCKET', '/run/doemo-redessin/api.sock')
    workbench = Workbench(os.environ.get('DOEMO_REDESSIN_DATA', '/var/lib/doemo-redessin'),
                          os.environ.get('DOEMO_RUNPOD_URL', ''), os.environ.get('DOEMO_OVH_PRIVATE_KEY', ''))
    uvicorn.run(create_app(workbench), uds=socket, workers=1, proxy_headers=False, access_log=False)


if __name__ == '__main__':
    main()
