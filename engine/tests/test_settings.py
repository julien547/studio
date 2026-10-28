import pytest

from doemo_pdf.settings import templates_dir


def test_default_doemo_collection(monkeypatch):
    monkeypatch.delenv('DOEMO_TEMPLATES_ROOT', raising=False)
    assert str(templates_dir()) == '/var/lib/doemo-studio/templates/doemo'


def test_client_collections_are_siblings(tmp_path, monkeypatch):
    monkeypatch.setenv('DOEMO_TEMPLATES_ROOT', str(tmp_path))
    assert templates_dir() == tmp_path/'doemo'
    assert templates_dir('client-a') == tmp_path/'client-a'


@pytest.mark.parametrize('client', ['SAI', 'Client École', 'Client_01'])
def test_client_names_match_template_administration(tmp_path, monkeypatch, client):
    monkeypatch.setenv('DOEMO_TEMPLATES_ROOT', str(tmp_path))
    assert templates_dir(client) == tmp_path/client


@pytest.mark.parametrize('client', ['../doemo','/tmp','client/other','','..'])
def test_untrusted_client_path_rejected(client):
    with pytest.raises(ValueError): templates_dir(client)


def test_symlink_collection_cannot_point_at_another_client(tmp_path, monkeypatch):
    (tmp_path/'client-b').mkdir()
    (tmp_path/'client-a').symlink_to(tmp_path/'client-b',target_is_directory=True)
    monkeypatch.setenv('DOEMO_TEMPLATES_ROOT',str(tmp_path))
    with pytest.raises(ValueError): templates_dir('client-a')
