import copy
import json

from fastapi.testclient import TestClient
import httpx
import pytest

from doemo_reconstruction.connection import connection_status, ENGINES
from doemo_reconstruction.workbench import Workbench, create_app
from doemo_reconstruction.ai_service.worker import Worker, create_worker
from doemo_reconstruction.ai_service.auth import verify
from test_ovh_workbench import ready_project, upload
from test_walls_service import keys


def responses():
    return {'/health': {'ready': True, 'draining': False, 'active': 0, 'unsaved': 0,
                        'pod_id': 'current-pod', 'worker_instance_id': 'current-worker'},
            '/models': [{'id': name, 'version': 'fixture-v1', 'configured': True,
                         'environment_present': True, 'functional_inference_verified': True}
                        for name in ENGINES]}


def test_configuration_alone_cannot_be_reported_as_connected():
    def unreachable(*args, **kwargs):
        raise httpx.ConnectError('private address must not leak')
    status = connection_status(False, unreachable)
    assert status['state'] == 'not_configured' and not status['can_analyze']
    status = connection_status(True, unreachable)
    assert status['state'] == 'unavailable' and not status['can_analyze']
    assert 'private address' not in json.dumps(status)


@pytest.mark.parametrize('change,state', [
    ({'ready': False}, 'starting'), ({'active': 1}, 'busy'),
    ({'draining': True}, 'busy'), ({'unsaved': 1}, 'not_ready'),
    ({'warmup_error': 'RuntimeError'}, 'not_ready'),
    ({'pod_id': None}, 'invalid_configuration_or_contract'),
    ({'ready': 'true'}, 'invalid_configuration_or_contract'),
])
def test_worker_state_is_checked_before_an_inference(change, state):
    payloads = responses()
    payloads['/health'].update(change)
    status = connection_status(True, lambda method, path, **kw: payloads[path])
    assert status['state'] == state and not status['can_analyze']


def test_all_three_models_need_success_and_versions_without_placeholders():
    payloads = responses()
    remote = lambda method, path, **kw: payloads[path]
    assert connection_status(True, remote)['can_analyze']
    payloads['/models'][1]['functional_inference_verified'] = False
    assert connection_status(True, remote)['state'] == 'starting'
    payloads['/models'][1]['functional_inference_verified'] = True
    payloads['/models'][1]['version'] = 'to-verify'
    assert connection_status(True, remote)['state'] == 'invalid_configuration_or_contract'
    payloads['/models'] = responses()['/models'] + [responses()['/models'][0]]
    assert not connection_status(True, remote)['can_analyze']


@pytest.mark.parametrize('code,state', [(401, 'authentication_failed'), (403, 'authentication_failed'), (502, 'unavailable')])
def test_worker_errors_do_not_expose_endpoint_or_token(code, state):
    def rejected(*args, **kw):
        request = httpx.Request('GET', 'https://private-host/health', headers={'Authorization': 'private-token'})
        httpx.Response(code, request=request, text='sensitive server detail').raise_for_status()
    status = connection_status(True, rejected)
    assert status['state'] == state
    assert not any(s in json.dumps(status) for s in ('private-host', 'private-token', 'sensitive server detail'))


def test_status_route_uses_active_server_configuration_and_requires_session(tmp_path, monkeypatch):
    bench = Workbench(tmp_path, 'https://private.example', '/unused-in-fixture')
    payloads = responses()
    monkeypatch.setattr(bench, 'remote', lambda method, path, **kw: payloads[path])
    with TestClient(create_app(bench, start_worker=False)) as client:
        assert client.get('/runpod/status').status_code == 401
        status = client.get('/runpod/status', headers={'X-Doemo-User': 'alice'}).json()
        assert status['state'] == 'ready'
        assert {m['id'] for m in status['engines']} == set(ENGINES)
        assert status['segmentation_qualified'] is False


def test_ovh_signed_calls_reach_each_adapter_and_keep_walls_pending(tmp_path, monkeypatch):
    """Full HTTP contracts with fake GPU adapters, not a claim of real GPU inference."""
    private, public = keys()
    key = tmp_path / 'private.pem'
    key.write_bytes(private)
    monkeypatch.setenv('RUNPOD_POD_ID', 'fixture-current-pod')
    calls = []
    class Engines:
        config = {name: {'version': 'fixture-v1'} for name in ENGINES}
        def models(self):
            return responses()['/models']
        def run(self, name, request):
            calls.append(name)
            out = {'engine': name, 'model_version': 'fixture-v1'}
            if name == 'qwen':
                out['zones'] = [{'id': request['regions'][0]['id'], 'label': 'unknown', 'note': 'fixture'}]
            if name == 'paddleocr':
                out['texts'] = [{'polygon': [[1, 1], [10, 1], [10, 6], [1, 6]], 'text': 'fixture', 'confidence': 0.5}]
            return out
    worker = Worker(Engines(), tmp_path / 'runpod')
    worker.ready = True
    bench = Workbench(tmp_path / 'ovh', 'https://private.example', str(key))
    ids, doc = ready_project(bench)
    doc['source']['sha256'] = 'a' * 64
    doc['levels'][0]['reference'] = 'data:image/png;base64,' + upload()['content']
    original_walls = copy.deepcopy(doc['levels'][0]['walls'])
    with bench.db() as db:
        db.execute('UPDATE projects SET document=? WHERE id=?', (json.dumps(doc), ids['id']))
    real_client = httpx.Client
    with TestClient(create_worker(worker, public, warmup=False)) as gpu:
        def transport(request):
            verify(public, request.headers['Authorization'].removeprefix('Bearer '), 'doemo-runpod', 'worker')
            response = gpu.request(request.method, request.url.path, content=request.content,
                                   headers=dict(request.headers))
            return httpx.Response(response.status_code, json=response.json())
        monkeypatch.setattr(httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(transport), **kw))
        status = connection_status(True, bench.remote)
        assert status['can_analyze'] and calls == []  # Status never triggers inference.
        task = bench.enqueue_ai('alice', ids['id'])
        assert bench.process_once()
        assert bench.task('alice', task['task_id'])['status'] == 'completed'
        assert calls == list(ENGINES)
        level = bench.project('alice', ids['id'])['document']['levels'][0]
        assert level['walls'] == original_walls
        assert level['ai_evidence'][task['task_id']]['texts'][0]['status'] == 'pending'
