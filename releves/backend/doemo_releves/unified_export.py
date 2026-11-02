"""One source frame, one work PDF: walls, annotations and original SAI resources.

The printed page width is a layout choice, never a building calibration. Native
AI resources are used only when their PDF-compatible component is verified. No
PNG preview is substituted for a vector resource and no annotation-box centre
is invented as an equipment anchor. PDF parsing runs in a bounded child process.
"""
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

from fastapi import Depends, Query
from fastapi.responses import Response

LOCK = threading.Semaphore(1)
MAX_PDF_BYTES = 64 * 1024**2
MAX_RESOURCE_BYTES = 64 * 1024**2
MAX_WALLS = 5000
MAX_ANNOTATIONS = 1000
MAX_ASSETS = 128
PT_PER_MM = 72 / 25.4


def _number(value):
    if not math.isfinite(float(value)):
        raise ValueError('Coordonnée non finie')
    return f'{float(value):.7f}'.rstrip('0').rstrip('.') or '0'


def _text(value):
    # PDF standard font with WinAnsiEncoding: hexadecimal strings cannot inject
    # PDF commands. The full Unicode annotation remains in the attached report.
    return '<' + str(value).replace('₂', '2').encode('cp1252', errors='replace').hex() + '>'


def _line(a, b, width=.5):
    return f'{_number(width)} w {_number(a[0])} {_number(a[1])} m {_number(b[0])} {_number(b[1])} l S\n'


def _label(point, label, size=7):
    return f'BT /F1 {_number(size)} Tf 1 0 0 1 {_number(point[0])} {_number(point[1])} Tm {_text(label)} Tj ET\n'


def _solid_intervals(openings):
    cut = []
    for opening in openings:
        lo, hi = opening['start'], opening['end']
        if not 0 <= lo < hi <= 1:
            raise ValueError('Ouverture hors mur')
        if cut and lo <= cut[-1][1]:
            cut[-1][1] = max(cut[-1][1], hi)
        else:
            cut.append([lo, hi])
    out, cursor = [], 0.
    for lo, hi in cut:
        if lo > cursor:
            out.append((cursor, lo))
        cursor = hi
    if cursor < 1:
        out.append((cursor, 1.))
    return out


def _wall_commands(structure, page_width, page_height, raster_width):
    sw, sh = float(structure['width']), float(structure['height'])
    convert = lambda x, y: [x / sw * page_width, page_height - y / sh * page_height]
    commands, count = [], 0
    for wall in structure.get('walls', []):
        if wall.get('status') == 'rejected':
            continue
        a, b = wall['a'], wall['b']
        length = math.dist(a, b)
        if length <= 1e-8:
            raise ValueError('Mur de longueur nulle')
        ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
        # Unknown thickness: only a two-source-pixel display convention.
        thickness = wall.get('thickness') or 2 * sw / raster_width
        nx, ny = -uy * thickness / 2, ux * thickness / 2
        openings = sorted(wall.get('openings', []), key=lambda o: o['start'])
        for start, end in _solid_intervals(openings):
            p = [a[0] + ux*length*start, a[1] + uy*length*start]
            q = [a[0] + ux*length*end, a[1] + uy*length*end]
            corners = [convert(p[0]+nx, p[1]+ny), convert(q[0]+nx, q[1]+ny),
                       convert(q[0]-nx, q[1]-ny), convert(p[0]-nx, p[1]-ny)]
            commands.append(' '.join(f'{_number(x)} {_number(y)} {"m" if k == 0 else "l"}'
                                     for k, (x, y) in enumerate(corners)) + ' h f\n')
        for opening in openings:
            if opening['kind'] != 'window':
                continue
            for sign in (-1, 1):
                p = convert(a[0] + ux*length*opening['start'] + sign*nx,
                            a[1] + uy*length*opening['start'] + sign*ny)
                q = convert(a[0] + ux*length*opening['end'] + sign*nx,
                            a[1] + uy*length*opening['end'] + sign*ny)
                commands.append(_line(p, q, max(.2, page_width/raster_width)))
        count += 1
    return ''.join(commands), count


def _asset_form(writer, asset, directory):
    """Copy graphics/resources into a Form XObject; never copy PDF page actions."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.errors import PyPdfError
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject, ArrayObject, FloatObject, NumberObject
    from .library import safe_path
    if not asset or not all(asset.get(k) for k in ('verified', 'approved', 'pictogram_candidate')):
        return None, 'pictogramme SAI absent ou non approuvé'
    components = asset.get('components', [])
    component = next((c for c in components if c.get('role') == 'primary'), components[0] if components else None)
    if not component:
        return None, 'composant Illustrator absent'
    path = (directory / str(safe_path(component['archive_path']))).resolve()
    if not path.is_relative_to(directory.resolve()) or not path.is_file():
        return None, 'ressource Illustrator inaccessible'
    if path.stat().st_size > MAX_RESOURCE_BYTES:
        return None, 'ressource Illustrator trop volumineuse'
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != component.get('sha256'):
        return None, 'empreinte de la ressource modifiée'
    if not data.startswith(b'%PDF-'):
        return None, 'ressource AI sans composant PDF compatible'
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted or len(reader.pages) != 1:
            return None, 'ressource PDF chiffrée ou multipage'
        original = reader.pages[0]
        if float(original.get('/UserUnit', 1)) != 1 or original.rotation % 90:
            return None, 'repère PDF non standard à vérifier dans Illustrator'
        if original.rotation:
            # Rotation modifies streams; pypdf requires a writer-owned page.
            # Keep this temporary document separate from the exported page.
            holder = PdfWriter()
            original = holder.add_page(original, excluded_keys=('/Annots', '/AA'))
            original.transfer_rotation_to_content()
        crop, media = list(map(float, original.cropbox)), list(map(float, original.mediabox))
        # PDFium previews the intersection of media/crop boxes. Use that same
        # upright frame, including its blank margins; it is not visibleBounds.
        box = [max(crop[0], media[0]), max(crop[1], media[1]), min(crop[2], media[2]), min(crop[3], media[3])]
        if not all(math.isfinite(v) for v in box) or not 0 < box[2]-box[0] < 100000 or not 0 < box[3]-box[1] < 100000:
            return None, 'dimensions de la ressource invalides'
        content = original.get_contents()
        if content is None:
            return None, 'ressource PDF vide'
        stream = content.get_data()
        if len(stream) > MAX_RESOURCE_BYTES:
            return None, 'contenu PDF excessif'
        form = DecodedStreamObject()
        form.set_data(stream)
        form.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Form'),
                     NameObject('/FormType'): NumberObject(1),
                     NameObject('/BBox'): ArrayObject([FloatObject(v) for v in box]),
                     NameObject('/Resources'): original.get('/Resources', DictionaryObject()).clone(writer)})
        if '/Group' in original:
            form[NameObject('/Group')] = original['/Group'].clone(writer)
        return (writer._add_object(form), box, component['sha256']), None
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, PyPdfError):
        return None, 'ressource PDF incompatible'


def make_pdf(data, output):
    """Pure renderer over an already-authorized source snapshot (also unit tested)."""
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, TextStringObject, ArrayObject, DecodedStreamObject
    page_data = data['page_data']
    rw, rh = float(page_data['width']), float(page_data['height'])
    paper_width = float(data['paper_width_mm'])
    if not 50 <= paper_width <= 2000 or not 0 < rw <= 50000 or not 0 < rh <= 50000:
        raise ValueError('Format de page invalide')
    pw, ph = paper_width * PT_PER_MM, paper_width * PT_PER_MM * rh/rw
    if ph > 20000:
        raise ValueError('Page imprimée excessivement longue')
    structures, annotations = data['structures'], data['annotations']
    if sum(len(s.get('walls', [])) for s in structures) > MAX_WALLS or len(annotations) > MAX_ANNOTATIONS:
        raise ValueError('Export trop volumineux : réduire le nombre d’éléments de la page')
    writer = PdfWriter()
    page = writer.add_blank_page(width=pw, height=ph)
    groups = {}
    for name, title in [('Walls', 'MURS'), ('Annotations', 'ANNOTATIONS À VÉRIFIER'), ('Equipment', 'PICTOGRAMMES INCENDIE')]:
        groups[name] = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/OCG'),
                                                           NameObject('/Name'): TextStringObject(title)}))
    refs = ArrayObject(list(groups.values()))
    writer.root_object[NameObject('/OCProperties')] = DictionaryObject({NameObject('/OCGs'): refs,
        NameObject('/D'): DictionaryObject({NameObject('/Order'): refs, NameObject('/ON'): refs})})
    font = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica'), NameObject('/Encoding'): NameObject('/WinAnsiEncoding')}))
    xobjects = DictionaryObject()
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font}),
        NameObject('/Properties'): DictionaryObject({NameObject('/'+k): v for k, v in groups.items()}),
        NameObject('/XObject'): xobjects})
    report = {'schema_version': 'doemo.unified-work/1', 'project_id': data['project_id'], 'revision': data['revision'],
              'source_document_id': data['document_id'], 'source_page': data['page'], 'source_sha256': data['source_sha256'],
              'source_frame': {'width': rw, 'height': rh, 'origin': 'upright_source_page_top_left'},
              'paper_width_mm': paper_width, 'page_size_pt': [pw, ph], 'building_scale': 'unknown',
              'native_ai_created': False, 'validated': False,
              'equipment_size_rule': 'longest_resource_pdf_cropbox_edge_mm_before_rotation',
              'unknown_wall_thickness': 'two_source_pixels_display_only',
              'walls': 0, 'placements': [], 'unresolved': []}
    commands = ['q /OC /Walls BDC 0 g 0 G\n']
    for structure in structures:
        if structure['source_sha256'] != data['source_sha256']:
            raise ValueError('La structure appartient à une autre source')
        part, count = _wall_commands(structure, pw, ph, rw)
        commands.append(part); report['walls'] += count
    commands.append('EMC Q\nq /OC /Equipment BDC\n')
    library = data.get('library') or {}
    assets = {a['id']: a for a in library.get('assets', [])} if library.get('archive_verified') else {}
    directory = Path(data.get('library_directory') or '.')
    cache, annotation_commands = {}, ['q /OC /Annotations BDC 0.72 0.35 0.05 RG 0.55 0.26 0.04 rg\n']
    for annotation in annotations:
        ident, anchor = annotation['id'], annotation.get('anchor')
        label = annotation.get('text') or annotation.get('equipment_type') or 'Annotation'
        b = annotation['bbox']
        annotation_commands.append(f'.35 w {_number(b["x"]*pw)} {_number(ph-(b["y"]+b["h"])*ph)} {_number(b["w"]*pw)} {_number(b["h"]*ph)} re S\n')
        annotation_commands.append(_label([b['x']*pw, ph-b['y']*ph+3], label[:160]))
        item = {'id': ident, 'floor_id': annotation.get('floor_id'), 'text': label,
                'source_anchor': anchor, 'target_override_used': False, 'validated': False}
        if anchor is None:
            reason = 'ancrage à pointer — aucun pictogramme positionné'
            report['unresolved'].append({'id': ident, 'reason': reason})
            item.update(status='missing_anchor', position_pt=None)
            annotation_commands.append(_label([b['x']*pw, ph-(b['y']+b['h'])*ph-9], 'ANCRAGE À POINTER', 6))
            report['placements'].append(item)
            continue
        x, y = anchor['x']*pw, ph-anchor['y']*ph
        asset_id = annotation.get('asset_id')
        if asset_id not in cache:
            if len(cache) >= MAX_ASSETS:
                raise ValueError('Trop de ressources différentes pour cet export')
            cache[asset_id] = _asset_form(writer, assets.get(asset_id), directory)
        loaded, reason = cache[asset_id]
        item.update(position_pt=[x, y], rotation_deg=annotation.get('rotation_deg', 0), size_mm=annotation['size_mm'])
        if loaded:
            form, bounds, sha = loaded
            name = '/Asset'+str(list(cache).index(asset_id))
            xobjects[NameObject(name)] = form
            aw, ah = bounds[2]-bounds[0], bounds[3]-bounds[1]
            scale = annotation['size_mm'] * PT_PER_MM / max(aw, ah)
            theta = -math.radians(annotation.get('rotation_deg', 0))
            cs, sn = math.cos(theta)*scale, math.sin(theta)*scale
            cx, cy = (bounds[0]+bounds[2])/2, (bounds[1]+bounds[3])/2
            tx, ty = x-cs*cx+sn*cy, y-sn*cx-cs*cy
            matrix = [cs, sn, -sn, cs, tx, ty]
            commands.append('q '+' '.join(_number(v) for v in matrix)+f' cm {name} Do Q\n')
            item.update(status='original_resource', asset_id=asset_id, asset_sha256=sha,
                        resource_bounds_pt=bounds, resource_to_page_matrix=matrix)
        else:
            report['unresolved'].append({'id': ident, 'reason': reason})
            item.update(status='reference_marker', reason=reason)
            commands.extend(['q 0.72 0.35 0.05 RG 0.55 0.26 0.04 rg\n', _line([x-3, y], [x+3, y]),
                             _line([x, y-3], [x, y+3]), _label([x+5, y+3], 'REPÈRE — SAI À COMPLÉTER', 6), 'Q\n'])
        report['placements'].append(item)
    commands.append('EMC Q\n')
    annotation_commands.append('EMC Q\n')
    stream = DecodedStreamObject(); stream.set_data((''.join(commands+annotation_commands)).encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    writer.add_metadata({'/Title': 'DOEMO — Plan unifié de travail, non validé', '/Creator': 'DOEMO Studio',
                         '/Subject': 'Même page source ; largeur imprimée conventionnelle ; échelle bâtiment inconnue.',
                         '/DOEMORevision': str(data['revision']), '/DOEMOSourceSHA256': data['source_sha256'],
                         '/DOEMOUnresolved': str(len(report['unresolved']))})
    writer.add_attachment('doemo-plan-unifie.json', json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
    writer.write(output)
    if Path(output).stat().st_size > MAX_PDF_BYTES:
        raise ValueError('PDF généré trop volumineux')
    return report


def isolated_pdf(data):
    with LOCK, tempfile.TemporaryDirectory(prefix='doemo-unified-') as tmp:
        source, output = Path(tmp)/'input.json', Path(tmp)/'plan.pdf'
        encoded = json.dumps(data)
        if len(encoded.encode()) > 16*1024**2:
            raise ValueError('Export trop volumineux')
        source.write_text(encoded)
        try:
            process = subprocess.run([sys.executable, '-m', 'doemo_releves.unified_export', str(source), str(output)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90,
                env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1'))
        except subprocess.TimeoutExpired as error:
            raise ValueError('Export interrompu : délai dépassé') from error
        if process.returncode or not output.is_file() or output.stat().st_size > MAX_PDF_BYTES:
            raise ValueError('Export interrompu : ressource incompatible ou limite de traitement')
        report = json.loads(process.stdout)
        return output.read_bytes(), report


def attach_unified_export(app, store, actor, get, doc):
    @app.get('/projects/{ident}/unified-export')
    def export(ident: str, document_id: str, page: int = Query(ge=1),
               paper_width_mm: float = Query(default=297, ge=50, le=2000), who=Depends(actor)):
        project = get(ident, who)
        source, _ = doc(ident, document_id, who, page)
        if source['role'] != 'survey':
            raise ValueError('Choisir une page du relevé source')
        from .exchange import validate_state
        from .models import ProjectState
        state = validate_state(ProjectState.model_validate(project['state']), project['documents']).model_dump()
        library = store.library(state['library_id']) if state.get('library_id') else None
        data = {'project_id': ident, 'revision': state['revision'], 'document_id': document_id, 'page': page,
                'source_sha256': source['sha256'], 'page_data': source['pages'][page-1], 'paper_width_mm': paper_width_mm,
                'structures': [s for s in state.get('structure_pages', []) if s['source_document_id'] == document_id and s['source_page'] == page],
                'annotations': [a for a in state['annotations'] if a['source_document_id'] == document_id and a['source_page'] == page and a['status'] != 'rejected'],
                'library': library,
                'library_directory': str(store.root/'libraries'/library['id']) if library else None}
        pdf, report = isolated_pdf(data)
        with store.connect() as c:
            c.execute('INSERT INTO events(project_id,actor,action,data) VALUES(?,?,?,?)',
                (ident, who.login, 'unified-work-export', json.dumps({'revision': state['revision'], 'document_id': document_id,
                    'page': page, 'unresolved': len(report['unresolved'])})))
        return Response(pdf, media_type='application/pdf', headers={'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff', 'Content-Disposition': 'attachment; filename="DOEMO-plan-unifie-travail.pdf"',
            'X-Doemo-Unresolved': str(len(report['unresolved'])), 'X-Doemo-Revision': str(state['revision'])})


def main():
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (3*1024**3, 3*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (75, 80))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_PDF_BYTES+1024, MAX_PDF_BYTES+1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    source, output = map(Path, sys.argv[1:])
    report = make_pdf(json.loads(source.read_text()), output)
    # Bounded status only; coordinates and resource paths stay in the PDF report.
    print(json.dumps({'unresolved': [{'id': x['id']} for x in report['unresolved']]}))


if __name__ == '__main__':
    main()
