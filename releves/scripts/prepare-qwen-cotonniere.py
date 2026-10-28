"""Prepare local draft conversations from the two supplied Cotonnière PDFs."""
import hashlib
import html
import json
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / 'datasets/qwen-cotonniere-v1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def main():
    proposals = json.loads((ROOT / 'propositions.json').read_text())
    images = ROOT / 'images'
    images.mkdir(exist_ok=True)
    survey, reference = ROOT / 'sources/333333.pdf', ROOT / 'sources/CO26100349-1.pdf'
    for pdf, prefix in ((survey, 'releve'), (reference, 'reference')):
        with pdfium.PdfDocument(pdf) as doc:
            for i in range(len(doc)):
                page = doc[i]
                bitmap = page.render(scale=2000 / page.get_width())
                bitmap.to_pil().save(images / f'{prefix}-{i+1}.png')
                bitmap.close()
                page.close()
    examples, cards = [], []
    for row in proposals['examples']:
        with Image.open(images / f"releve-{row['page']}.png") as source:
            cx, cy = row['center'][0] * source.width, row['center'][1] * source.height
            size = 320
            left, top = max(0, min(source.width-size, int(cx-size/2))), max(0, min(source.height-size, int(cy-size/2)))
            box = [left, top, left+size, top+size]
            crop = images / (row['id'] + '.png')
            source.crop(box).save(crop, 'PNG')
            source_size = list(source.size)
        target = 'la note manuscrite verte en bas du détail' if row['id']=='cotonniere-pharmacie-rdc' else 'l’annotation au centre du détail'
        prompt = (f"Cotonnière, {'RDC' if row['page']==1 else 'R+1'}. Interpréter {target}. "
                  'JSON : equipment_type, decision, quantity, anchor. Désignation seulement : '
                  'anchor=null, quantity=null. ' + row['context'])
        if len(prompt)>400:
            raise ValueError('Convention trop longue')
        answer = dict(equipment_type=row['equipment_type'], decision='classify', quantity=None, anchor=None)
        conversation = dict(image=str(crop.relative_to(ROOT)), split='validation',
                            messages=[dict(role='user',content=prompt),dict(role='assistant',content=encoded(answer))])
        examples.append(dict(id=row['id'],engine='qwen',status='draft',split='validation',
                             building_key=proposals['building_key'],original_document_sha256=sha(survey),
                             source_page=row['page'],crop_pixels=box,crop_source_size=source_size,
                             image=conversation['image'],image_sha256=sha(crop),image_size=[size,size],
                             reference_pdf_sha256=sha(reference),reference_page=1,
                             reference_evidence=row['reference_evidence'],
                             interpretation_origin='assistant_reading_of_survey_and_reference',
                             geometry_reviewed=False,human_review_required=True,
                             example_fields=dict(engine='qwen',page=1,labels=[],convention=prompt,
                                 observed=row['observed'],interpretation=encoded(answer),
                                 notes=f"Source 333333.pdf page {row['page']} ; {row['id']} ; proposition à relire."),
                             conversation=conversation))
        cards.append('<article><h2>' + html.escape(row['id']) + '</h2><img width="320" src="' + html.escape(conversation['image'])
                     + '" alt="Détail du relevé"><p>Lecture proposée : <b>' + html.escape(row['observed']) + '</b></p><p>'
                     + html.escape(row['reference_evidence']) + '</p><p>' + html.escape(prompt) + '</p><pre>'
                     + html.escape(json.dumps(answer,ensure_ascii=False,indent=2))
                     + '</pre><p>À relire. Aucun point de pose déduit du recadrage.</p></article>')
    payload = dict(schema='doemo.qwen-draft-pack/1',engine='qwen',ready_for_training=False,building_groups=1,
                   split_counts={'train':0,'validation':len(examples),'test':0},
                   reference_validated_by_user=proposals['reference_validated_by_user'],examples=examples,
                   blockers=['Confirmation du plan de référence marqué SPÉCIMEN.',
                             'Relecture et validation des propositions dans DOEMO.',
                             'Autorisation du projet enregistrée et troisième site indépendant pour le test.'])
    (ROOT / 'draft-examples.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    (ROOT / 'qwen-draft.jsonl').write_text('\n'.join(encoded(e['conversation']) for e in examples)+'\n')
    (ROOT / 'revue.html').write_text('<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>Qwen — revue Cotonnière</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:16px;background:#f5f6f8}'
        'article{padding:24px;margin:20px 0;background:white;border:1px solid #ccd;overflow:auto}img{float:left;margin:0 24px 20px 0}pre{white-space:pre-wrap}</style>'
        '<h1>Cotonnière — 12 propositions à relire</h1><p>Un seul groupe : bâtiments A/B et niveaux 0/1. Réservé à la validation, pas à l’entraînement. '
        'Le PDF mis au propre porte SPÉCIMEN : confirmation de la référence requise.</p><p>'
        '<a href="sources/333333.pdf">Relevé original, 2 pages</a> · <a href="sources/CO26100349-1.pdf">Plan mis au propre</a></p>'
        + ''.join(cards) + '</html>')
    files=[p for p in ROOT.rglob('*') if p.is_file() and p.name!='manifest.json']
    (ROOT / 'manifest.json').write_text(json.dumps(dict(schema='doemo.qwen-draft-manifest/1',ready_for_training=False,
        files=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p),size=p.stat().st_size) for p in sorted(files)]),indent=2)+'\n')
    print(encoded(dict(examples=len(examples),groups=1,split='validation',ready_for_training=False)))


if __name__=='__main__':
    main()
