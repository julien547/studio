"""Archive d'entraînement des murs : images PNG + walls.jsonl (segments dans le repère de l'image).

Format volontairement voisin des exports de training_data.py (.json/.jsonl/.png seulement, pas de chemin absolu).
    images/<ref>.png
    walls.jsonl : {"ref","image","width","height","split","document_sha256","segments":[[x1,y1,x2,y2],...]}
"""
import json
import math
import zipfile
from pathlib import Path, PurePosixPath

SPLITS = ('train', 'validation', 'test')


def build(coco_zip, murs_jsonl, destination):
    """Croise l'export de détection (images + splits par document) avec les murs vérifiés."""
    with zipfile.ZipFile(coco_zip) as z:
        coco = json.loads(z.read('coco.json'))
        images = {i['ref']: i for i in coco['images']}
        murs = {}
        for line in Path(murs_jsonl).read_text().splitlines():
            row = json.loads(line)
            if row.get('verifie') and row['segments']:
                murs[Path(row['image']).parent.name] = row['segments']
        keep = [r for r in images if r in murs]
        if not keep:
            raise ValueError('Aucun plan commun entre les boîtes et les murs vérifiés')
        with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as out:
            rows = []
            for ref in sorted(keep):
                im = images[ref]
                out.writestr(f'images/{ref}.png', z.read(im['file_name']))
                rows.append({'ref': ref, 'image': f'images/{ref}.png', 'width': im['width'], 'height': im['height'],
                             'split': im['split'], 'document_sha256': im['document_sha256'], 'segments': murs[ref]})
            out.writestr('walls.jsonl', '\n'.join(json.dumps(r) for r in rows) + '\n')
    return len(keep)


def unpack(bundle, destination):
    """Extraction protégée (mêmes règles que training_data.unpack) puis validation."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(bundle) as z:
        infos = z.infolist()
        if len(infos) > 5000 or sum(i.file_size for i in infos) > 2 * 1024 ** 3:
            raise ValueError('Archive excessive')
        for info in infos:
            p = PurePosixPath(info.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in info.filename or ((info.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError('Chemin ZIP dangereux')
            if info.is_dir():
                continue
            if p.suffix not in ('.json', '.jsonl', '.png'):
                raise ValueError('Format inattendu')
            target = destination.joinpath(*p.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, target.open('xb') as dst:
                dst.write(src.read())
    return validate(destination)


def validate(root):
    """Retourne {split: [enregistrements]} ; refuse un split vide ou un document réparti sur plusieurs splits."""
    root = Path(root)
    rows = [json.loads(line) for line in (root / 'walls.jsonl').read_text().splitlines() if line.strip()]
    groups, out, refs = {}, {s: [] for s in SPLITS}, set()
    for r in rows:
        if r['split'] not in SPLITS or r['ref'] in refs:
            raise ValueError('Split invalide ou plan dupliqué')
        refs.add(r['ref'])
        path = (root / r['image']).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError('Image absente')
        if groups.setdefault(r['document_sha256'], r['split']) != r['split']:
            raise ValueError('Même document dans plusieurs splits')
        if not r['segments']:
            raise ValueError('Plan sans mur')
        for s in r['segments']:
            if len(s) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in s):
                raise ValueError('Segment invalide')
        r['path'] = str(path)
        out[r['split']].append(r)
    if not all(out.values()):
        raise ValueError('Chaque split doit contenir au moins un plan')
    return out
