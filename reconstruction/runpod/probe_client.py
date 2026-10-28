#!/usr/bin/env python3
"""Signed OVH-side test of real RunPod inference; no Pod lifecycle operations."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from doemo_reconstruction.ai_service.auth import issue
from doemo_reconstruction.ai_service.contracts import validate_request
from doemo_reconstruction.ai_service.jobs import canonical


def validate_url(value):
    parsed = urlsplit(value)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('', '/')):
        raise ValueError('URL de service sans identifiant, chemin, requête ni fragment attendue')
    if parsed.scheme != 'https' and not (
            parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', '::1')):
        raise ValueError('HTTPS obligatoire, sauf tunnel local sur adresse de bouclage')
    return value.rstrip('/')


def make_request(image_path, manifest, models, engines):
    data = Path(image_path).read_bytes()
    versions = {model['id']: model['version'] for model in models if model.get('version')}
    for name in engines:
        model = next((m for m in models if m['id'] == name), {})
        if not model.get('functional_inference_verified') or name not in versions:
            raise ValueError(f'Inférence de démarrage non vérifiée : {name}')
    request = {
        'project_id': manifest['project_id'], 'page': manifest['page'],
        'source_sha256': manifest['source_sha256'], 'image_sha256': manifest['image_sha256'],
        'image_base64': base64.b64encode(data).decode(),
        'width': manifest['width'], 'height': manifest['height'],
        'regions': manifest.get('regions', []), 'engines': engines,
        'model_versions': {name: versions[name] for name in engines},
        'parameters': {'diagnostic_only': 'rtmdet' in engines},
    }
    return validate_request(request)[0]


def validate_result(result, request, job_id, worker_identity):
    expected = {key: request[key] for key in (
        'source_sha256', 'image_sha256', 'page', 'width', 'height', 'model_versions')}
    expected.update(schema='doemo.ai.evidence/1', job_id=job_id,
                    coordinate_space='input_image_pixels', status='pending')
    if any(result.get(key) != value for key, value in expected.items()):
        raise ValueError('Provenance du résultat différente de la requête')
    execution = result.get('executed_on', {})
    # A migration/restart during this test must be reconciled explicitly, not silently accepted.
    if any(execution.get(key) != worker_identity[key] for key in ('pod_id', 'worker_instance_id')):
        raise ValueError('Identité du worker modifiée pendant le test')
    if set(result.get('engines', {})) != set(request['engines']):
        raise ValueError('Réponses de moteurs manquantes')
    for name, output in result['engines'].items():
        if output.get('engine') != name or output.get('model_version') != request['model_versions'][name]:
            raise ValueError('Version ou identité de moteur incohérente')


def signed_call(client, private_key, method, path, **kwargs):
    response = client.request(method, path, headers={
        'Authorization': 'Bearer ' + issue(private_key, 'doemo-runpod', 'worker', ttl=120)}, **kwargs)
    response.raise_for_status()
    return response.json()


def run_probe(client, private_key, image_path, manifest, output_dir, engines,
              *, ready_timeout=3000, poll_interval=5):
    deadline = time.monotonic() + ready_timeout
    while True:
        health = signed_call(client, private_key, 'GET', '/health')
        if health.get('warmup_error') or health.get('unsaved') or health.get('draining'):
            raise RuntimeError('Worker indisponible ; consulter /health et les journaux privés RunPod')
        if health.get('ready') and not health.get('active'):
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('Démarrage ou disponibilité GPU non confirmé dans le délai')
        time.sleep(poll_interval)
    if not health.get('pod_id') or not health.get('worker_instance_id'):
        raise ValueError('Identité du Pod courant absente')
    models = signed_call(client, private_key, 'GET', '/models')
    request = make_request(image_path, manifest, models, engines)
    digest = hashlib.sha256(canonical(request).encode()).hexdigest()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / 'request-receipt.json'
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt['request_sha256'] != digest:
            raise ValueError('Ce dossier correspond à une autre requête ; choisir un nouveau dossier')
        job_id = receipt['job_id']
        identity = receipt['worker_identity']
    else:
        job_id = str(uuid.uuid4())
        identity = {key: health[key] for key in ('pod_id', 'worker_instance_id')}
        # Keep this receipt before sending, so a timeout cannot cause a new expensive job.
        with receipt_path.open('x') as stream:
            json.dump({'job_id': job_id, 'request_sha256': digest, 'worker_identity': identity,
                       'source_manifest': manifest}, stream, ensure_ascii=False, indent=2)
    result = signed_call(client, private_key, 'POST', '/infer/' + job_id, json=request)
    validate_result(result, request, job_id, identity)
    (output_dir / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    report = {'job_id': job_id, 'real_inference_returned': True, 'worker_identity': identity,
              'engines': engines, 'wall_segmentation_verified': False,
              'architectural_accuracy_verified': False, 'human_review_required': True}
    (output_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--private-key', required=True, help='OVH signing key PEM, never uploaded')
    parser.add_argument('--image', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True, help='Dedicated local directory; reuse after an uncertain timeout')
    parser.add_argument('--engines', nargs='+', choices=['qwen', 'paddleocr', 'rtmdet'],
                        default=['paddleocr', 'qwen', 'rtmdet'])
    args = parser.parse_args()
    try:
        url = validate_url(args.url)
        private_key = Path(args.private_key).read_bytes()
        manifest = json.loads(Path(args.manifest).read_text())
        # No redirects or insecure TLS option. Each engine may take up to 900 seconds.
        with httpx.Client(base_url=url, timeout=httpx.Timeout(2800, connect=15), follow_redirects=False) as client:
            report = run_probe(client, private_key, args.image, manifest, args.output, args.engines)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (httpx.HTTPError, OSError, ValueError, RuntimeError, KeyError) as error:
        print('Test non validé : ' + type(error).__name__ + '. Consulter les journaux privés ; '
              'après un délai réseau, relancer avec le même dossier --output.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
