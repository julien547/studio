"""Read-only batch preparation: every label occurrence, automatic template match.

Labels are not yet verified VEI objects. This module never generates a plan or
claims the list is exhaustive when labels are outlined or cannot be extracted.
"""

from collections import defaultdict
import os
from pathlib import Path
import re

import pikepdf

from .pdf import file_hash, inspect_pdf, open_pdf, selected_page
from .settings import templates_dir

TEMPLATE_NAME = re.compile(r"^(PE|PI)-(A[0-4])-([HV])\.pdf$", re.I)
PAPER_MM = {'A0': (841, 1189), 'A1': (594, 841), 'A2': (420, 594),
            'A3': (297, 420), 'A4': (210, 297)}


def template_index(directory):
    index = defaultdict(list)
    for root, dirs, files in os.walk(directory, followlinks=False):
        parent = Path(root)
        dirs[:] = sorted(name for name in dirs if not name.startswith('.')
                         and not (parent/name).is_symlink())
        # Match the administration's maximum depth of four path components
        # including the collection (collection / subdir / subdir / file).
        if len(parent.relative_to(directory).parts) >= 2:
            dirs[:] = []
        for name in sorted(files):
            path = parent/name
            match = TEMPLATE_NAME.fullmatch(name)
            if match and not path.is_symlink() and path.is_file():
                index[tuple(value.upper() for value in match.groups())].append(path)
    return index


def check_template(path, key):
    """Check page format, not template content, placement zone or business approval."""
    initial = file_hash(path)
    with open_pdf(path) as pdf:
        if len(pdf.pages) != 1:
            raise ValueError('La trame doit contenir une seule page.')
        page = selected_page(pdf, 0)
        x0, y0, x1, y1 = map(float, page.cropbox)
        actual = (x1-x0, y1-y0)
        expected = tuple(mm*72/25.4 for mm in PAPER_MM[key[1]])
        if key[2] == 'H':
            expected = expected[::-1]
        if any(abs(a-b) > 2 for a, b in zip(actual, expected)):
            raise ValueError('Dimensions ou orientation incompatibles avec le nom de la trame.')
    if file_hash(path) != initial:
        raise ValueError('La trame a changé pendant son inspection.')
    return initial


def plan_batch(source, client='doemo'):
    directory = templates_dir(client)
    inspection = inspect_pdf(source)
    index = template_index(directory)
    matches = {}
    variants = []
    for page in inspection['pages']:
        for occurrence, candidate in enumerate(page['label_candidates'], 1):
            key = (candidate['type'], candidate['paper'], candidate['orientation'])
            if key not in matches:
                paths = index.get(key, [])
                match = {'key': '-'.join(key), 'reference': None,
                         'status': 'missing' if not paths else 'ambiguous',
                         'candidates': [f'{client}/{p.relative_to(directory).as_posix()}' for p in paths]}
                if len(paths) == 1:
                    try:
                        checksum = check_template(paths[0], key)
                    except (ValueError, OSError, pikepdf.PdfError):
                        match['status'] = 'invalid'
                    else:
                        match.update(status='matched', reference=match['candidates'][0],
                                     sha256=checksum, validation='page_format_only')
                matches[key] = match
            template = matches[key]
            blockers = ['VEI_ASSOCIATION_UNVERIFIED', 'OBJECT_TRANSFORMATIONS_NOT_IMPLEMENTED',
                        'TEMPLATE_LAYOUT_NOT_VALIDATED']
            if template['status'] != 'matched':
                blockers.append('TEMPLATE_' + template['status'].upper())
            identifier = f'p{page["page"]:03d}-vei{occurrence:03d}'
            variants.append({'id': identifier, 'page': page['page'], 'label': candidate['label'],
                             'type': key[0], 'paper': key[1], 'orientation': key[2],
                             'template': template, 'direction': None, 'status': 'blocked',
                             'blockers': blockers,
                             'proposed_filename': f'{identifier}-{"-".join(key)}.pdf'})
    if file_hash(source) != inspection['sha256']:
        raise ValueError('Le BAT a changé pendant la préparation du lot.')
    return {'schema_version': 1, 'status': 'planning_only', 'requested_scope': 'all_vei',
            'source_sha256': inspection['sha256'], 'source_unchanged': inspection['source_unchanged'],
            'client': client, 'page_count': inspection['page_count'], 'default_paper': 'A3',
            'detection_complete': False, 'candidate_count': len(variants),
            'verified_vei_count': 0, 'expected_output_count': None,
            'production_ready': False, 'generation_available': False,
            'variants': variants,
            'blockers': ['VEI_DETECTION_AND_ASSOCIATION_UNVERIFIED',
                         'PRODUCTION_RENDERER_NOT_IMPLEMENTED'] +
                        ([] if variants else ['NO_READABLE_VEI_LABELS'])}
