import base64
import copy
import io
import json
import time
import uuid

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from doemo_reconstruction.workbench import Workbench, create_app
from doemo_reconstruction.geometry import edit
from test_reconstruction import document


def upload():
    data = io.BytesIO()
    Image.new('RGB', (128, 128), 'white').save(data, format='PNG')
    return {'content': base64.b64encode(data.getvalue()).decode(), 'name': 'plan.png', 'page': 1}


def ready_project(workbench, owner='alice'):
    ids = workbench.upload(owner, upload())
    doc = document()
    with workbench.db() as db:
        db.execute('UPDATE projects SET document=?,version=1 WHERE id=?', (json.dumps(doc), ids['id']))
        db.execute("UPDATE tasks SET status='completed' WHERE id=?", (ids['task_id'],))
    return ids, doc


def test_private_workbench_requires_actor_and_prevents_cross_user_access(tmp_path):
    bench = Workbench(tmp_path)
    with TestClient(create_app(bench, start_worker=False)) as client:
        assert client.get('/health').status_code == 401
        alice, bob = {'X-Doemo-User': 'alice'}, {'X-Doemo-User': 'bob'}
        result = client.post('/projects', headers=alice, json=upload())
        assert result.status_code == 202
        ids = result.json()
        assert client.get('/projects', headers=bob).json() == []
        for path in ('/projects/' + ids['id'], '/tasks/' + ids['task_id'],
                     '/projects/' + ids['id'] + '/export/svg'):
            assert client.get(path, headers=bob).status_code == 404
        assert client.post('/projects/' + ids['id'] + '/analyze', headers=bob).status_code == 404
        assert client.get('/health', headers=alice).json()['runpod_configured'] is False


def test_save_checks_revision_source_and_preserves_private_reference(tmp_path):
    bench = Workbench(tmp_path)
    ids, doc = ready_project(bench)
    edited = edit(doc, 'L', {'op': 'approve', 'id': doc['levels'][0]['walls'][0]['id']}, 'client-name')
    with TestClient(create_app(bench, start_worker=False)) as client:
        headers = {'X-Doemo-User': 'alice'}
        path = '/projects/' + ids['id'] + '/save'
        out = client.post(path, headers=headers, json={'expected_version': 1, 'document': edited})
        assert out.status_code == 200 and out.json()['version'] == 2
        assert out.json()['document']['history'][-1]['actor'] == 'alice'
        assert client.post(path, headers=headers, json={'expected_version': 1, 'document': edited}).status_code == 409
        stored = out.json()['document']
        bad = copy.deepcopy(stored)
        bad['source']['sha256'] = 'b' * 64
        assert client.post(path, headers=headers, json={'expected_version': 2, 'document': bad}).status_code == 422
        result = client.get('/projects/' + ids['id'] + '/export/svg', headers=headers)
        assert result.status_code == 200 and '<path' in result.json()['content']
        assert 'stroke="#000000"' in result.json()['content']
        assert bench.project('alice', ids['id'])['document'] == stored


def test_restart_does_not_repeat_unknown_remote_work_and_config_does_not_invent_readiness(tmp_path):
    bench = Workbench(tmp_path, 'http://127.0.0.1:8009', '/not-used-in-this-test')
    ids, _ = ready_project(bench)
    task = bench.enqueue_ai('alice', ids['id'])
    with bench.db() as db:
        db.execute("UPDATE tasks SET status='running' WHERE id=?", (task['task_id'],))
    with TestClient(create_app(bench, start_worker=False)) as client:
        headers = {'X-Doemo-User': 'alice'}
        health = client.get('/health', headers=headers).json()
        assert health['runpod_configured'] and not health['runpod_inference_verified']
        assert client.get('/tasks/' + task['task_id'], headers=headers).json()['status'] == 'interrupted'
        assert client.post('/projects/' + ids['id'] + '/analyze', headers=headers).status_code == 409
    assert bench.process_once() is False


def test_ai_observations_merge_into_latest_saved_drawing(tmp_path, monkeypatch):
    bench = Workbench(tmp_path, 'https://private.example', '/unused')
    ids, doc = ready_project(bench)
    task = bench.enqueue_ai('alice', ids['id'])
    def result(project, task_id):
        edited = edit(doc, 'L', {'op': 'approve', 'id': doc['levels'][0]['walls'][0]['id']}, 'alice')
        bench.save('alice', ids['id'], {'expected_version': 1, 'document': edited})
        request = {'image_sha256': 'c' * 64, 'width': 200, 'height': 200, 'regions': []}
        evidence = {'schema': 'doemo.ai.evidence/1', 'job_id': task_id,
                    'source_sha256': doc['source']['sha256'], 'page': doc['levels'][0]['source_page'],
                    'image_sha256': 'c' * 64, 'coordinate_space': 'input_image_pixels',
                    'width': 200, 'height': 200, 'model_versions': {}, 'engines': {}}
        return evidence, request
    monkeypatch.setattr(bench, 'ai_result', result)
    assert bench.process_once()
    after = bench.project('alice', ids['id'])
    assert after['document']['levels'][0]['walls'][0]['status'] == 'approved'
    assert task['task_id'] in after['document']['levels'][0]['ai_evidence']
    assert after['version'] == 3


def test_upload_and_url_validation(tmp_path):
    for url in ('http://gpu.example', 'https://user:secret@gpu.example', 'https://gpu.example?key=secret'):
        with pytest.raises(ValueError):
            Workbench(tmp_path, url)
    bench = Workbench(tmp_path)
    with TestClient(create_app(bench, start_worker=False)) as client:
        headers = {'X-Doemo-User': 'alice'}
        assert client.post('/projects', headers=headers, json={**upload(), 'page': 2}).status_code == 422
        assert client.post('/projects', headers=headers, json={**upload(), 'page': True}).status_code == 422
        assert client.post('/projects', headers=headers, json={**upload(), 'content': 'bad!'}).status_code == 422
