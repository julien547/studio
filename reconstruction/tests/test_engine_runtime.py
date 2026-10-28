import copy
from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from doemo_reconstruction.ai_service import engines as engine_module
from doemo_reconstruction.ai_service.outputs import validate_output
from doemo_reconstruction.ai_service.worker import Worker, create_worker
from doemo_reconstruction.ai_service.auth import issue
from doemo_reconstruction.connection import connection_status
from test_inference_handoff import module
from test_runpod_connection import responses
from test_walls_service import keys


def qwen_output():
    return {'engine': 'qwen', 'model_version': 'local-v1', 'duration_seconds': 1,
            'zones': [{'id': 'page', 'label': 'unknown', 'uncertain': True,
                       'note': 'À contrôler', 'status': 'pending'}]}


def check(name, output):
    return validate_output(name, output, version='local-v1',
                           regions=[{'id': 'page', 'bbox': [0, 0, 80, 60]}], width=80, height=60)


@pytest.mark.parametrize('mutation', [
    {'zones': []}, {'zones': [qwen_output()['zones'][0]] * 2},
    {'engine': 'paddleocr'}, {'model_version': 'another-snapshot'},
    {'duration_seconds': float('nan')},
    {'zones': [{**qwen_output()['zones'][0], 'id': 'invented'}]},
    {'zones': [{**qwen_output()['zones'][0], 'uncertain': False}]},
    {'zones': [{**qwen_output()['zones'][0], 'walls': []}]},
])
def test_qwen_incomplete_or_invented_evidence_cannot_pass(mutation):
    assert check('qwen', qwen_output())
    with pytest.raises(ValueError):
        check('qwen', {**qwen_output(), **mutation})


def test_ocr_and_detections_can_be_empty_but_not_missing_or_outside_image():
    ocr = {'engine': 'paddleocr', 'model_version': 'local-v1', 'duration_seconds': 1,
           'texts': [], 'coordinate_space': 'input_image_pixels'}
    detector = {'engine': 'rtmdet', 'model_version': 'local-v1', 'duration_seconds': 1,
                'detections': [], 'architectural_wall_detector': False, 'usage': 'diagnostic_only'}
    assert check('paddleocr', ocr) and check('rtmdet', detector)
    for name, output, field in [('paddleocr', ocr, 'texts'), ('rtmdet', detector, 'detections')]:
        broken = {k: v for k, v in output.items() if k != field}
        with pytest.raises(ValueError):
            check(name, broken)
    ocr['texts'] = [{'polygon': [[1, 1], [10, 1], [10, 7]], 'text': 'DOEMO',
                     'confidence': .8, 'status': 'pending'}]
    assert check('paddleocr', ocr)
    for point in ([-1, 0], [81, 0], [1, float('nan')], [True, 1]):
        broken = copy.deepcopy(ocr)
        broken['texts'][0]['polygon'][0] = point
        with pytest.raises(ValueError):
            check('paddleocr', broken)
    detector['architectural_wall_detector'] = True
    with pytest.raises(ValueError):
        check('rtmdet', detector)


def test_real_subprocess_rejects_bad_output_and_keeps_config_snapshot(tmp_path, monkeypatch):
    """Exercise process boundaries with a synthetic runner, never a GPU model."""
    config = tmp_path / 'models.json'
    config.write_text(json.dumps({'qwen': {'version': 'local-v1'}}))
    script = tmp_path / 'runner.py'
    script.write_text('''import argparse,json
from pathlib import Path
p=argparse.ArgumentParser()
for name in ('engine','config','request','output'):p.add_argument('--'+name)
a=p.parse_args()
config=json.loads(Path(a.config).read_text())
request=json.loads(Path(a.request).read_text())
result={'engine':a.engine,'model_version':config[a.engine]['version'],'duration_seconds':0,
        'zones':[{'id':r['id'],'label':'unknown','uncertain':True,'note':'fixture','status':'pending'}
                 for r in request['regions']]}
if request.get('omit_zone'):result['zones']=[]
Path(a.output).write_text(json.dumps(result))
''')
    image = tmp_path / 'page.png'
    Image.new('RGB', (80, 60)).save(image)
    monkeypatch.setitem(engine_module.PYTHONS, 'qwen', sys.executable)
    engines = engine_module.Engines(config, script)
    config.write_text(json.dumps({'qwen': {'version': 'changed-during-job'}}))
    request = {'image_path': str(image), 'regions': [{'id': 'page', 'bbox': [0, 0, 80, 60]}]}
    with pytest.raises(ValueError):
        engines.run('qwen', {**request, 'omit_zone': True})
    assert engines.last_success == {}
    assert engines.run('qwen', request)['model_version'] == 'local-v1'
    assert 'qwen' in engines.last_success


def test_paddle3_rejects_truncated_parallel_lists_and_uses_local_names(tmp_path, monkeypatch):
    runner = module('engine_runner')
    options = {}
    payload = {'res': {'rec_polys': [[[1, 1], [9, 1], [9, 7], [1, 7]]],
                       'rec_texts': ['DOEMO'], 'rec_scores': []}}
    class OCR:
        def __init__(self, **kwargs):
            options.update(kwargs)
        def predict(self, image):
            return [SimpleNamespace(json=payload)]
    monkeypatch.setitem(sys.modules, 'paddle', SimpleNamespace(
        is_compiled_with_cuda=lambda: True, device=SimpleNamespace(cuda=SimpleNamespace(device_count=lambda: 1))))
    monkeypatch.setitem(sys.modules, 'paddleocr', SimpleNamespace(__version__='3.0.0', PaddleOCR=OCR))
    config = {'detection_model': str(tmp_path), 'recognition_model': str(tmp_path),
              'detection_model_name': 'existing-det', 'recognition_model_name': 'existing-rec'}
    with pytest.raises(ValueError, match='Incomplete'):
        runner.paddle({'image_path': '/fixture.png'}, config)
    payload['res']['rec_scores'] = [.9]
    assert runner.paddle({'image_path': '/fixture.png'}, config)['texts'][0]['text'] == 'DOEMO'
    assert options['text_recognition_model_name'] == 'existing-rec'
    assert options['device'] == 'gpu:0' and options['use_doc_unwarping'] is False


def test_qwen_requests_json_without_thinking_and_requires_every_zone(tmp_path, monkeypatch):
    import numpy as np
    runner = module('engine_runner')
    response = {'zones': [{k: v for k, v in qwen_output()['zones'][0].items() if k != 'status'}]}
    options = {}
    class Inputs(dict):
        def to(self, device):
            return self
    class Processor:
        @classmethod
        def from_pretrained(cls, path, **kwargs):
            assert kwargs['local_files_only'] and not kwargs['trust_remote_code']
            return cls()
        def apply_chat_template(self, messages, **kwargs):
            options.update(kwargs)
            return Inputs(input_ids=np.zeros((1, 1)))
        def batch_decode(self, *args, **kwargs):
            return [json.dumps(response)]
    class Model:
        device = 'cuda:0'
        @classmethod
        def from_pretrained(cls, path, **kwargs):
            assert kwargs['local_files_only'] and not kwargs['trust_remote_code']
            return cls()
        def eval(self):
            return self
        def generate(self, **kwargs):
            return np.zeros((1, 4))
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True), bfloat16='bf16', inference_mode=nullcontext))
    monkeypatch.setitem(sys.modules, 'transformers', SimpleNamespace(
        AutoProcessor=Processor, AutoModelForImageTextToText=Model))
    request = {'image_path': '/fixture.png', 'regions': [{'id': 'page', 'bbox': [0, 0, 80, 60]}]}
    assert runner.qwen(request, {'model': str(tmp_path)})['zones'][0]['status'] == 'pending'
    assert options['enable_thinking'] is False
    response['zones'] = []
    with pytest.raises(ValueError, match='Incomplete'):
        runner.qwen(request, {'model': str(tmp_path)})


def test_warmup_checks_other_engines_after_failure_and_reports_only_safe_codes(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=''))
    class Engines:
        def run(self, name, request):
            calls.append(name)
            if name == 'paddleocr':
                raise ValueError('secret path and model text must not leak')
    worker = Worker(Engines(), tmp_path)
    worker.warmup()
    health = worker.health()
    assert calls == ['paddleocr', 'qwen', 'rtmdet']
    assert not health['ready'] and not health['warming_up']
    assert health['startup']['paddleocr'] == {'state': 'failed', 'error_code': 'invalid_output'}
    assert health['startup']['qwen']['state'] == health['startup']['rtmdet']['state'] == 'passed'
    assert 'secret path' not in json.dumps(health)
    payloads = responses()
    payloads['/health'].update(health, pod_id='current-pod')
    status = connection_status(True, lambda method, path, **kw: payloads[path])
    assert status['state'] == 'not_ready' and not status['can_analyze']
    assert [e['startup_inference_verified'] for e in status['engines']] == [False, True, True]


def test_warmup_cannot_be_drained_or_reported_safe_to_stop(tmp_path, monkeypatch):
    private, public = keys()
    started, release = threading.Event(), threading.Event()
    monkeypatch.setenv('DOEMO_WORKER_EXCLUSIVE', '1')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=''))
    class Engines:
        def run(self, name, request):
            started.set()
            assert release.wait(5)
    worker = Worker(Engines(), tmp_path)
    thread = threading.Thread(target=worker.warmup)
    thread.start()
    try:
        assert started.wait(5)
        assert worker.health()['warming_up'] and not worker.health()['stop_safe']
        with TestClient(create_worker(worker, public, warmup=False)) as client:
            headers = {'Authorization': 'Bearer ' + issue(private, 'doemo-runpod', 'worker')}
            assert client.post('/drain', headers=headers).json() == {'drained': False}
    finally:
        release.set()
        thread.join(5)
    assert worker.ready and worker.health()['stop_safe']


def test_gpu_check_failure_does_not_claim_the_environments_are_absent(tmp_path, monkeypatch):
    def fail(*args, **kw):
        raise FileNotFoundError('/private/path')
    monkeypatch.setattr(subprocess, 'run', fail)
    worker = Worker(None, tmp_path)
    worker.warmup()
    health = worker.health()
    assert not health['ready'] and not health['warming_up']
    assert all(s == {'state': 'failed', 'error_code': 'gpu_unavailable'} for s in health['startup'].values())
    assert '/private/path' not in json.dumps(health)
