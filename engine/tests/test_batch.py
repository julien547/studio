import json

import pikepdf
import pytest

from doemo_pdf.batch import plan_batch
from doemo_pdf.cli import main


def bat(path, pages):
    pdf = pikepdf.Pdf.new()
    for labels in pages:
        page = pdf.add_blank_page(page_size=(842, 1191))
        page.Resources.Font = pikepdf.Dictionary(F1=pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)))
        content = '0 0 100 100 re S\nBT /F1 12 Tf 20 1000 Td 20 TL\n'
        content += '\n'.join(f'({label}) Tj T*' for label in labels) + '\nET'
        page.Contents = pdf.make_stream(content.encode('ascii'))
    pdf.save(path)
    return path


def template(path, size=(841.89, 1190.55)):
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=size)
    pdf.save(path)
    return path


@pytest.fixture
def collection(tmp_path, monkeypatch):
    directory = tmp_path/'templates'/'doemo'
    monkeypatch.setenv('DOEMO_TEMPLATES_ROOT', str(directory.parent))
    template(directory/'PE-A3-V.pdf')
    template(directory/'PI-A3-V.pdf')
    return directory


def test_all_occurrences_in_all_pages_keep_individual_outputs(tmp_path, collection):
    source = bat(tmp_path/'bat.pdf', [['PEV', 'PEV', 'PIV'], ['PE1-H-A4']])
    template(collection/'PE-A4-H.pdf', (841.89, 595.28))
    before = source.read_bytes()
    result = plan_batch(source)
    assert result['candidate_count'] == 4
    assert result['page_count'] == 2
    assert [x['template']['reference'] for x in result['variants']] == [
        'doemo/PE-A3-V.pdf', 'doemo/PE-A3-V.pdf', 'doemo/PI-A3-V.pdf', 'doemo/PE-A4-H.pdf']
    assert len({x['proposed_filename'] for x in result['variants']}) == 4
    assert all(x['template']['status'] == 'matched' for x in result['variants'])
    assert result['requested_scope'] == 'all_vei'
    assert result['production_ready'] is False
    assert result['detection_complete'] is False
    assert result['expected_output_count'] is None
    assert all(x['direction'] is None and x['status'] == 'blocked' for x in result['variants'])
    assert source.read_bytes() == before
    assert list(tmp_path.glob('p*-vei*.pdf')) == []


def test_missing_or_duplicate_template_never_drops_a_variant(tmp_path, collection):
    source = bat(tmp_path/'bat.pdf', [['PEV', 'PIH', 'PEV']])
    template(collection/'custom'/'PE-A3-V.pdf')
    result = plan_batch(source)
    assert len(result['variants']) == 3
    assert [x['template']['status'] for x in result['variants']] == ['ambiguous', 'missing', 'ambiguous']
    assert all(x['template']['reference'] is None for x in result['variants'])


def test_client_selection_never_falls_back_to_doemo(tmp_path, collection):
    source = bat(tmp_path/'bat.pdf', [['PEV', 'PIV']])
    template(collection.parent/'client-a'/'plans'/'PE-A3-V.pdf')
    result = plan_batch(source, 'client-a')
    assert result['variants'][0]['template']['reference'] == 'client-a/plans/PE-A3-V.pdf'
    assert result['variants'][1]['template']['status'] == 'missing'


@pytest.mark.parametrize('case', ['wrong_orientation', 'wrong_paper', 'invalid_pdf'])
def test_incompatible_template_not_selected(tmp_path, collection, case):
    source = bat(tmp_path/'bat.pdf', [['PEV']])
    path = collection/'PE-A3-V.pdf'
    if case == 'invalid_pdf':
        path.write_text('not PDF')
    else:
        template(path, (1190.55, 841.89) if case == 'wrong_orientation' else (595.28, 841.89))
    variant = plan_batch(source)['variants'][0]
    assert variant['template']['status'] == 'invalid'
    assert variant['template']['reference'] is None


def test_archives_and_symlinks_do_not_override_templates(tmp_path, collection):
    source = bat(tmp_path/'bat.pdf', [['PEV', 'PIH']])
    template(collection/'.corbeille'/'PE-A3-V.pdf')
    other = template(collection.parent/'client-b'/'PI-A3-H.pdf', (1190.55, 841.89))
    (collection/'PI-A3-H.pdf').symlink_to(other)
    (collection/'alias').symlink_to(other.parent, target_is_directory=True)
    result = plan_batch(source)
    assert result['variants'][0]['template']['status'] == 'matched'
    assert result['variants'][1]['template']['status'] == 'missing'


def test_empty_extraction_is_not_a_successful_empty_batch(tmp_path, collection):
    result = plan_batch(bat(tmp_path/'bat.pdf', [[]]))
    assert result['candidate_count'] == 0
    assert 'NO_READABLE_VEI_LABELS' in result['blockers']
    assert result['generation_available'] is False


def test_batch_cli_returns_planning_only(tmp_path, collection, capsys):
    source = bat(tmp_path/'bat.pdf', [['PEV', 'PEV', 'PIV']])
    assert main(['plan-batch', str(source)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'planning_only'
    assert result['candidate_count'] == 3
    assert result['production_ready'] is False
