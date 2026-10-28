"""Build reviewable Qwen drafts from the supplied Animalis scan; CPU only.

No database, network, model, consent flag or human validation is modified.
All crops share their original building/document group, never separate splits.
"""
import hashlib
import html
import json
import math
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / 'datasets/qwen-animalis-v1'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    corrections = json.loads((ROOT / 'corrections.json').read_text())
    source = ROOT / 'releve-source.png'
    images = ROOT / 'images'
    images.mkdir(exist_ok=True)
    examples, conversations, cards = [], [], []
    with Image.open(source) as image:
        for row in corrections['examples']:
            b = row['source_region']
            # Keep enough surrounding plan for the reviewer. Never redraw a glyph.
            cx, cy = (b['x'] + b['w'] / 2) * image.width, (b['y'] + b['h'] / 2) * image.height
            width, height = max(256, math.ceil(b['w'] * image.width + 96)), max(256, math.ceil(b['h'] * image.height + 96))
            left = max(0, min(image.width - width, math.floor(cx - width / 2)))
            top = max(0, min(image.height - height, math.floor(cy - height / 2)))
            box = [left, top, min(image.width, left + width), min(image.height, top + height)]
            path = images / (row['id'] + '.png')
            image.crop(box).save(path, 'PNG')
            prompt = (f"Animalis {row['floor_context']}, {row['id']}, repère central. "
                      'JSON : equipment_type, decision, quantity, anchor. Désignation seulement ; '
                      'anchor=null ; quantity=null sauf nombre confirmé. ' + row['convention_context'])
            if len(prompt) > 400:
                raise ValueError('Convention trop longue pour le contrat DOEMO')
            answer = dict(equipment_type=row['equipment_type'], decision=row['decision'], quantity=row['quantity'], anchor=None)
            messages = [{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': encoded(answer)}]
            conversation = dict(image=str(path.relative_to(ROOT)), split='train', messages=messages)
            conversations.append(conversation)
            example = dict(
                id=row['id'], engine='qwen', status='draft', split='train',
                building_key=corrections['building_key'],
                original_document_sha256=corrections['source_pdf_sha256'],
                image=conversation['image'], image_sha256=sha(path), image_size=[box[2]-box[0], box[3]-box[1]],
                original_region=b, crop_pixels=box, crop_source_size=list(image.size),
                user_evidence=row['user_evidence'], interpretation_scope='designation_only',
                human_review_required=True, geometry_reviewed=False,
                # For the existing Example API, project/document are resolved after importing the crop.
                example_fields=dict(engine='qwen', page=1, labels=[], interpretation=encoded(answer),
                                    convention=prompt, observed='', notes='Source RELEVEDEUX.pdf ; '
                                    + row['id'] + ' ; désignation uniquement ; revue humaine requise.'),
                conversation=conversation,
            )
            examples.append(example)
            cards.append('<article><h2>' + html.escape(row['id']) + ' — ' + html.escape(row['floor_context']) + '</h2>'
                         '<img width="256" src="' + html.escape(conversation['image']) + '" alt="Détail du relevé">'
                         '<p><b>Correction donnée :</b> ' + html.escape(row['user_evidence']) + '</p>'
                         '<p>' + html.escape(prompt) + '</p><pre>' + html.escape(json.dumps(answer, ensure_ascii=False, indent=2)) + '</pre>'
                         '<p class="pending">À vérifier : détail cadré et réponse. Aucune position de pose validée.</p></article>')
    payload = dict(schema='doemo.qwen-draft-pack/1', engine='qwen', ready_for_training=False,
                   building_groups=1, split_counts={'train':len(examples),'validation':0,'test':0},
                   original_document_sha256=corrections['source_pdf_sha256'],
                   source_image_sha256=sha(source), examples=examples,
                   blockers=['Relecture des détails et réponses avant validation dans DOEMO.',
                             'Réunir les groupes indépendants et vérifier les lots du dataset final.',
                             'Autorisation du projet enregistrée dans DOEMO avant export.'])
    (ROOT / 'draft-examples.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    (ROOT / 'qwen-draft.jsonl').write_text('\n'.join(encoded(c) for c in conversations) + '\n')
    (ROOT / 'revue.html').write_text(
        '<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>Dataset Qwen — Animalis — revue</title><style>body{font:16px system-ui;max-width:1000px;margin:30px auto;padding:16px;background:#f4f5f8;color:#182230}'
        'article{background:white;border:1px solid #ccd3df;border-radius:8px;padding:20px;margin:20px 0;overflow:auto}'
        'img{float:left;margin:0 24px 20px 0;border:1px solid #aaa}pre{white-space:pre-wrap}.pending{color:#8a4700}a{color:#2747a7}</style>'
        '<h1>Qwen — premier lot Animalis</h1><p>11 propositions fondées sur les corrections du dessinateur. '
        'Un bâtiment, réservé à l’entraînement. Validation et test encore vides. '
        'Les coordonnées de recadrage ne sont pas des positions de pose.</p>'
        '<p><a href="releve-source.png">Ouvrir le relevé complet</a> · <a href="draft-examples.json">Données et provenance</a></p>'
        + ''.join(cards) + '</html>')
    files = [p for p in ROOT.rglob('*') if p.is_file() and p.name != 'manifest.json']
    (ROOT / 'manifest.json').write_text(json.dumps(dict(schema='doemo.qwen-draft-manifest/1', ready_for_training=False,
        files=[dict(path=str(p.relative_to(ROOT)), sha256=sha(p), size=p.stat().st_size) for p in sorted(files)]), indent=2) + '\n')
    print(json.dumps({'examples':len(examples),'groups':1,'ready_for_training':False,'directory':str(ROOT)}))


if __name__ == '__main__':
    main()
