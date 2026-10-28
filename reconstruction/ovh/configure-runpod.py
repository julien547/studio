#!/usr/bin/env python3
"""Configure the OVH connection without exposing a private key or restarting services."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import sqlite3
import subprocess
import sys
from urllib.parse import urlsplit
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat, load_pem_private_key)


def validate_url(value):
    parsed = urlsplit(value)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('', '/') or any(c.isspace() or c in '"\\' for c in value)
            or not (parsed.scheme == 'https' or
                    (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', '::1')))):
        raise ValueError('URL HTTPS privée ou tunnel HTTP en boucle locale requis')
    if 'PORT_' in value or 'REPLACE' in value:
        raise ValueError('Renseigner le port et l’hôte réels')
    # Accessing .port validates its syntax and range.
    parsed.port
    return value.rstrip('/')


def exclusive_file(path, data, mode, uid=None, gid=None):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, 'wb') as stream:
        if uid is not None:
            os.fchown(stream.fileno(), uid, gid)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def configure(directory, url, *, backup_dir, generate_key=False, private_key_path=None, uid=None, gid=None):
    """OVH local filesystem only. Existing matching keys and unrelated env settings survive."""
    url = validate_url(url)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    private_path = Path(private_key_path).resolve() if private_key_path else directory/'worker-signing-private.pem'
    public_path = directory/'worker-signing-public.pem'
    if not private_path.exists() and public_path.exists():
        raise ValueError('Clé publique présente sans sa clé privée ; retrouver la paire existante')
    if any(c.isspace() or c in '"\\' for c in str(private_path)):
        raise ValueError('Chemin de clé sans espace requis pour EnvironmentFile')
    if private_path.is_symlink():
        raise ValueError('Utiliser le fichier de clé réel')
    if private_path.exists():
        key = load_pem_private_key(private_path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError('Clé privée Ed25519 PKCS8 PEM requise')
        if private_path.stat().st_mode & 0o077:
            raise ValueError('Clé privée accessible à d’autres comptes ; corriger ses droits')
        if uid is not None and private_path.stat().st_uid != uid:
            raise ValueError('Le fichier privé doit appartenir au compte doemo-redessin')
    else:
        if not generate_key or private_key_path is not None:
            raise ValueError('Clé absente ; utiliser --generate-key pour créer la paire dédiée')
        key = Ed25519PrivateKey.generate()
        private = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        exclusive_file(private_path, private, 0o600, uid, gid)
    public = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    if public_path.is_symlink() or (public_path.exists() and public_path.read_bytes() != public):
        raise ValueError('Une autre clé publique existe ; aucune rotation implicite autorisée')
    if not public_path.exists():
        exclusive_file(public_path, public, 0o644)
    env_path = directory/'service.env'
    if env_path.is_symlink():
        raise ValueError('EnvironmentFile doit être un fichier local réel')
    previous = env_path.read_text() if env_path.exists() else ''
    target = {'DOEMO_RUNPOD_URL': url, 'DOEMO_OVH_PRIVATE_KEY': str(private_path)}
    lines = [line for line in previous.splitlines()
             if line.strip().split('=', 1)[0].strip() not in target]
    content = '\n'.join(lines + [k+'='+v for k, v in target.items()])+'\n'
    changed = content != previous
    if changed:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
        if env_path.exists():
            backups = Path(backup_dir)
            backups.mkdir(parents=True, exist_ok=True, mode=0o700)
            exclusive_file(backups/('service.env.backup-'+stamp), previous.encode(), 0o600)
        temporary = directory/('.service.env-'+uuid.uuid4().hex)
        try:
            exclusive_file(temporary, content.encode(), 0o600)
            os.replace(temporary, env_path)
        finally:
            temporary.unlink(missing_ok=True)
    return {'configured': True, 'configuration_changed': changed,
            'public_key_file': str(public_path), 'public_key_sha256': hashlib.sha256(public).hexdigest(),
            'real_inference_verified': False, 'service_restarted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--generate-key', action='store_true')
    parser.add_argument('--private-key', help='Existing key readable only by doemo-redessin')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Exécuter sur OVH avec sudo ; aucune clé ne sera affichée')
    try:
        account = pwd.getpwnam('doemo-redessin')
        database = Path('/var/lib/doemo-redessin/workbench.sqlite3')
        if database.exists():
            with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as db:
                active = db.execute("SELECT count(*) FROM tasks WHERE status IN ('queued','running','interrupted')").fetchone()[0]
            if active:
                raise ValueError('Terminer ou réconcilier les tâches existantes avant configuration')
        if subprocess.run(['systemctl', 'is-active', '--quiet', 'doemo-redessin.service']).returncode == 0:
            raise ValueError('Arrêter uniquement doemo-redessin.service après vérification des tâches')
        result = configure('/etc/doemo-redessin', args.url, generate_key=args.generate_key,
                           private_key_path=args.private_key, uid=account.pw_uid, gid=account.pw_gid,
                           backup_dir='/var/backups/doemo-studio/redessin-config')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        print('Configuration non terminée : '+(str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
