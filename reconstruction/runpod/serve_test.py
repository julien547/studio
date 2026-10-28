#!/usr/bin/env python3
"""Launch only the inference worker. Never restore/install models or control a Pod."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from doemo_reconstruction.ai_service.engines import PYTHONS


MODEL_PATHS = {
    'qwen': {'model': 'directory'},
    'paddleocr': {'detection_model': 'directory', 'recognition_model': 'directory'},
    'rtmdet': {'config': 'file', 'checkpoint': 'file'},
}


def check_configuration(config_path, public_key_path, pythons=PYTHONS):
    """Read-only preflight; success is not proof of GPU inference."""
    config = json.loads(Path(config_path).read_text())
    errors = []
    for engine, fields in MODEL_PATHS.items():
        settings = config.get(engine, {})
        version = settings.get('version', '')
        if not isinstance(version, str) or not version.strip() or any(
                marker in version.lower() for marker in ('replace', 'to-verify', 'placeholder')):
            errors.append(f'{engine}: renseigner la version locale vérifiée')
        if not Path(pythons[engine]).is_file():
            errors.append(f'{engine}: interpréteur inaccessible à ce processus')
        for field, kind in fields.items():
            value = settings.get(field)
            if not isinstance(value, str) or not value or 'REPLACE_' in value:
                errors.append(f'{engine}.{field}: chemin local à renseigner')
                continue
            path = Path(value)
            present = path.is_dir() if kind == 'directory' else path.is_file()
            if not path.is_absolute() or not present:
                errors.append(f'{engine}.{field}: chemin local absolu introuvable')
    key = load_pem_public_key(Path(public_key_path).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        errors.append('La clé de vérification doit être une clé publique Ed25519 PEM')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8009)
    parser.add_argument('--behind-tls-proxy', action='store_true',
                        help='Required for non-loopback bind; operator provides TLS and network restrictions')
    args = parser.parse_args()
    if args.host not in ('127.0.0.1', '::1') and not args.behind_tls_proxy:
        parser.error('Écoute réseau réservée à un transport TLS privé configuré')
    if not 1 <= args.port <= 65535:
        parser.error('Port invalide')
    for variable in ('DOEMO_MODELS_CONFIG', 'DOEMO_OVH_PUBLIC_KEY', 'RUNPOD_POD_ID'):
        if not os.environ.get(variable):
            parser.error(f'{variable} absent ; RUNPOD_POD_ID doit venir du Pod courant')
    os.environ.setdefault('DOEMO_ENGINE_RUNNER', str(Path(__file__).with_name('engine_runner.py').resolve()))
    try:
        errors = check_configuration(os.environ['DOEMO_MODELS_CONFIG'], os.environ['DOEMO_OVH_PUBLIC_KEY'])
        if not Path(os.environ['DOEMO_ENGINE_RUNNER']).is_file():
            errors.append('Runner introuvable')
    except (OSError, ValueError, TypeError) as error:
        parser.error('Configuration illisible ou invalide : ' + type(error).__name__)
    if errors:
        print(json.dumps({'configuration_valid': False, 'errors': errors}, ensure_ascii=False, indent=2))
        return 2
    if args.check:
        print(json.dumps({'configuration_valid': True, 'functional_inference_verified': False}))
        return 0
    import uvicorn
    from doemo_reconstruction.ai_service.worker import app_factory
    # Exactly one process: multiple workers would defeat the GPU admission lock.
    uvicorn.run(app_factory(), host=args.host, port=args.port, workers=1,
                proxy_headers=False, access_log=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())
