import hashlib
import importlib.util
import json
from pathlib import Path

import httpx
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from doemo_reconstruction.ai_service.worker import Worker, create_worker
from test_walls_service import keys


def module(name):
    path = Path(__file__).parents[1] / 'runpod' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


probe = module('probe_client')
serve = module('serve_test')


def sample(tmp_path):
    image = tmp_path / 'page.png'
    Image.new('RGB', (80, 60), 'white').save(image)
    return image, {'project_id': 'page-one-test', 'page': 1, 'source_sha256': 'a' * 64,
                   'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                   'width': 80, 'height': 60}


def test_test_client_requires_tls_or_loopback_tunnel():
    for url in ('https://private.example', 'http://127.0.0.1:8009', 'http://[::1]:8009'):
        assert probe.validate_url(url)
    for url in ('http://private.example', 'https://user:secret@private.example',
                'https://private.example?token=secret', 'file:///tmp/x', 'https://private.example/path'):
        with pytest.raises(ValueError):
            probe.validate_url(url)


def test_preflight_blocks_placeholder_config_without_modifying_existing_models(tmp_path):
    _, public = keys()
    public_path = tmp_path / 'public.pem'
    public_path.write_bytes(public)
    config = {}
    pythons = {}
    for name, fields in serve.MODEL_PATHS.items():
        config[name] = {'version': name + '-verified-local-v1'}
        pythons[name] = str(tmp_path / (name + '-python'))
        Path(pythons[name]).touch()
        for field, kind in fields.items():
            path = tmp_path / (name + '-' + field)
            path.mkdir() if kind == 'directory' else path.write_bytes(b'existing-model')
            config[name][field] = str(path)
    config_path = tmp_path / 'models.json'
    config_path.write_text(json.dumps(config))
    assert serve.check_configuration(config_path, public_path, pythons) == []
    config['paddleocr']['version'] = 'existing-local-models-to-verify'
    config['rtmdet']['checkpoint'] = '/REPLACE_WITH_EXISTING_CHECKPOINT.pth'
    config_path.write_text(json.dumps(config))
    errors = serve.check_configuration(config_path, public_path, pythons)
    assert len(errors) == 2
    assert (tmp_path / 'rtmdet-checkpoint').read_bytes() == b'existing-model'


def test_probe_end_to_end_auth_provenance_and_replay_without_recomputing(tmp_path, monkeypatch):
    private, public = keys()
    image, manifest = sample(tmp_path)
    monkeypatch.setenv('RUNPOD_POD_ID', 'current-test-pod')
    class FakeEngines:
        config = {name: {'version': 'fixture-v1'} for name in ('paddleocr', 'qwen', 'rtmdet')}
        calls = []
        def models(self):
            return [{'id': name, 'version': 'fixture-v1', 'functional_inference_verified': True}
                    for name in self.config]
        def run(self, name, request):
            self.calls.append(name)
            return {'engine': name, 'model_version': 'fixture-v1', 'fixture_only': True}
    engines = FakeEngines()
    worker = Worker(engines, tmp_path / 'persistent')
    worker.ready = True
    with TestClient(create_worker(worker, public, warmup=False)) as client:
        assert client.get('/health').status_code == 401
        assert client.get('/openapi.json').status_code == 404
        names = ['paddleocr', 'qwen', 'rtmdet']
        first = probe.run_probe(client, private, image, manifest, tmp_path / 'receipt', names)
        second = probe.run_probe(client, private, image, manifest, tmp_path / 'receipt', names)
        assert first['job_id'] == second['job_id'] and engines.calls == names
        assert first['wall_segmentation_verified'] is False
        request = probe.make_request(image, manifest, engines.models(), names)
        result = json.loads((tmp_path / 'receipt/evidence.json').read_text())
        for mutation in ({'source_sha256': 'b' * 64}, {'page': 2},
                         {'executed_on': {'pod_id': 'old-pod', 'worker_instance_id': worker.instance_id}}):
            with pytest.raises(ValueError):
                probe.validate_result({**result, **mutation}, request, first['job_id'], first['worker_identity'])
        result['engines']['qwen']['model_version'] = 'wrong-version'
        with pytest.raises(ValueError):
            probe.validate_result(result, request, first['job_id'], first['worker_identity'])
        changed = {**manifest, 'page': 2}
        with pytest.raises(ValueError):
            probe.run_probe(client, private, image, changed, tmp_path / 'receipt', names)
        assert engines.calls == names


def test_probe_refuses_wrong_image_and_unverified_models(tmp_path):
    image, manifest = sample(tmp_path)
    models = [{'id': 'qwen', 'version': 'v1', 'functional_inference_verified': True}]
    with pytest.raises(ValueError):
        probe.make_request(image, {**manifest, 'image_sha256': 'b' * 64}, models, ['qwen'])
    models[0]['functional_inference_verified'] = False
    with pytest.raises(ValueError):
        probe.make_request(image, manifest, models, ['qwen'])


def test_timeout_receipt_is_reused_instead_of_starting_another_job(tmp_path):
    private, _ = keys()
    image, manifest = sample(tmp_path)
    seen = []
    def transport(request):
        if request.url.path == '/health':
            return httpx.Response(200, json={'ready': True, 'active': 0, 'pod_id': 'pod',
                                            'worker_instance_id': 'instance'})
        if request.url.path == '/models':
            return httpx.Response(200, json=[{'id': 'qwen', 'version': 'v1',
                                              'functional_inference_verified': True}])
        seen.append(request.url.path)
        raise httpx.ReadTimeout('fixture timeout', request=request)
    with httpx.Client(base_url='https://test.example', transport=httpx.MockTransport(transport)) as client:
        for _ in range(2):
            with pytest.raises(httpx.ReadTimeout):
                probe.run_probe(client, private, image, manifest, tmp_path / 'receipt', ['qwen'])
    assert len(seen) == 2 and seen[0] == seen[1]
    assert not (tmp_path / 'receipt/report.json').exists()
