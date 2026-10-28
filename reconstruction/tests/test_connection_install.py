import importlib.util
from pathlib import Path

import pytest

from doemo_reconstruction.ai_service.auth import issue, verify

path = Path(__file__).parents[1]/'ovh/configure-runpod.py'
spec = importlib.util.spec_from_file_location('configure_runpod', path)
configure_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure_module)


def test_prepare_connection_creates_reusable_keys_and_preserves_other_settings(tmp_path):
    directory, backup = tmp_path/'etc', tmp_path/'backups'
    directory.mkdir()
    env = directory/'service.env'
    env.write_text('# Existing configuration\nOTHER_SETTING=keep\nDOEMO_RUNPOD_URL=\nDOEMO_OVH_PRIVATE_KEY=\n')
    before = env.read_text()
    result = configure_module.configure(directory, 'http://127.0.0.1:8009', backup_dir=backup, generate_key=True)
    assert result['configured'] and not result['real_inference_verified'] and not result['service_restarted']
    private = (directory/'worker-signing-private.pem').read_bytes()
    public = (directory/'worker-signing-public.pem').read_bytes()
    verify(public, issue(private, 'doemo-runpod', 'worker'), 'doemo-runpod', 'worker')
    assert (directory/'worker-signing-private.pem').stat().st_mode & 0o077 == 0
    assert 'OTHER_SETTING=keep' in env.read_text()
    assert next(backup.iterdir()).read_text() == before
    again = configure_module.configure(directory, 'http://127.0.0.1:8009', backup_dir=backup, generate_key=True)
    assert not again['configuration_changed']
    assert (directory/'worker-signing-private.pem').read_bytes() == private
    assert len(list(backup.iterdir())) == 1


def test_existing_public_key_without_private_key_is_not_rotated(tmp_path):
    public = tmp_path/'worker-signing-public.pem'
    public.write_text('existing key to recover')
    with pytest.raises(ValueError):
        configure_module.configure(tmp_path, 'https://private.example', backup_dir=tmp_path/'backup', generate_key=True)
    assert not (tmp_path/'worker-signing-private.pem').exists()
    assert public.read_text() == 'existing key to recover'


@pytest.mark.parametrize('url', ['http://gpu.example', 'https://user:secret@gpu.example',
                                 'https://gpu.example?token=secret', 'http://127.0.0.1:PORT_REEL',
                                 'https://gpu.example\nOTHER_SETTING=bad'])
def test_unsafe_or_placeholder_connection_urls_are_rejected_without_files(tmp_path, url):
    with pytest.raises(ValueError):
        configure_module.configure(tmp_path/'etc', url, backup_dir=tmp_path/'backup', generate_key=True)
    assert not (tmp_path/'etc').exists()


def test_deployment_sources_preserve_current_embedded_app_and_backup_location():
    root = Path(__file__).parents[2]
    assert '<header>' not in (root/'redessin/index.php').read_text()
    assert '<header>' not in (root/'redessin/editor.js').read_text()
    script = (root/'reconstruction/ovh/install-release.sh').read_text()
    assert '/var/backups/doemo-studio/redessin/' in script
    assert '"$web_root/app' not in script and '"$web_root/releves' not in script
