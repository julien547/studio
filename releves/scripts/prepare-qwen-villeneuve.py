"""Prepare the held-out Villeneuve draft group from plans already in GitHub."""
import hashlib
import html
import json
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

REPO=Path(__file__).resolve().parents[2]
ROOT=REPO/'releves/datasets/qwen-villeneuve-v1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def main():
    spec=json.loads((ROOT/'propositions.json').read_text())
    images=ROOT/'images';images.mkdir(exist_ok=True)
    for item in spec['sources'].values():
        if sha(REPO/item['git_path'])!=item['sha256']:
            raise ValueError('Source modifiée ; revoir les correspondances avant régénération')
    source_pages={}
    for index,name in enumerate(['MAIRIE DE VLB GAUCHE.pdf','MAIRIE DE VLB PLAN DROITE.pdf','villeneuve.pdf']):
        with pdfium.PdfDocument(REPO/spec['sources'][name]['git_path']) as doc:
            for i in range(len(doc)):
                page=doc[i];bitmap=page.render(scale=1800/page.get_width())
                path=images/f'source-{index+1}-page-{i+1}.png'
                bitmap.to_pil().save(path);bitmap.close();page.close()
                source_pages[name,i+1]=path
    examples=[];cards=[]
    for row in spec['examples']:
        with Image.open(source_pages[row['file'],row['page']]) as source:
            cx,cy=row['center'][0]*source.width,row['center'][1]*source.height
            size=240
            left,top=max(0,min(source.width-size,int(cx-size/2))),max(0,min(source.height-size,int(cy-size/2)))
            box=[left,top,left+size,top+size];crop=images/(row['id']+'.png')
            source.crop(box).save(crop,'PNG');source_size=list(source.size)
        prompt=(f"Mairie de Villeneuve-lès-Béziers, niveau {row['floor']}. Interpréter {row['hint']}. "
                'JSON : equipment_type, decision, quantity, anchor. Désignation seulement ; anchor=null et quantity=null.')
        if len(prompt)>400:raise ValueError('Convention trop longue')
        answer=dict(equipment_type=row['equipment_type'],decision='classify',quantity=None,anchor=None)
        conversation=dict(image=str(crop.relative_to(ROOT)),split='test',messages=[dict(role='user',content=prompt),dict(role='assistant',content=encoded(answer))])
        examples.append(dict(id=row['id'],engine='qwen',status='draft',split='test',building_key=spec['building_key'],
            source_git_path=spec['sources'][row['file']]['git_path'],source_commit=spec['source_commit'],
            original_document_sha256=spec['sources'][row['file']]['sha256'],source_page=row['page'],
            source_render=str(source_pages[row['file'],row['page']].relative_to(ROOT)),crop_pixels=box,crop_source_size=source_size,
            image=conversation['image'],image_sha256=sha(crop),image_size=[size,size],
            reference_pdf_sha256=spec['sources']['villeneuve.pdf']['sha256'],reference_evidence=row['reference_evidence'],
            interpretation_origin='assistant_reading_of_survey_and_reference',human_review_required=True,geometry_reviewed=False,
            example_fields=dict(engine='qwen',page=1,labels=[],observed=row['observed'],convention=prompt,interpretation=encoded(answer),
                                notes=f"Source {row['file']} page {row['page']} ; {row['id']} ; désignation à relire."),conversation=conversation))
        cards.append('<article><h2>'+html.escape(row['id'])+'</h2><img width="240" src="'+html.escape(conversation['image'])+'" alt="Détail du relevé">'
                     '<p>'+html.escape(prompt)+'</p><p><b>Référence proposée :</b> '+html.escape(row['reference_evidence'])+'</p><pre>'
                     +html.escape(json.dumps(answer,ensure_ascii=False,indent=2))+'</pre><p>À relire. Aucun point de pose validé.</p></article>')
    payload=dict(schema='doemo.qwen-draft-pack/1',engine='qwen',ready_for_training=False,building_groups=1,
        split_counts={'train':0,'validation':0,'test':len(examples)},reference_validated_by_user=spec['reference_validated_by_user'],examples=examples,
        blockers=([] if spec['reference_validated_by_user'] else ['Confirmer villeneuve.pdf comme référence.'])+
                 ['Relire et valider les réponses dans DOEMO.','Enregistrer les autorisations des projets et figer le dataset via DOEMO.'])
    (ROOT/'draft-examples.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'qwen-draft.jsonl').write_text('\n'.join(encoded(e['conversation']) for e in examples)+'\n')
    status='Référence confirmée ; réponses à relire.' if spec['reference_validated_by_user'] else 'Plan de référence marqué SPÉCIMEN : confirmation requise.'
    (ROOT/'revue.html').write_text('<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>Qwen — Villeneuve — revue</title><style>body{font:16px system-ui;max-width:1050px;margin:30px auto;padding:16px;background:#f5f6f8}'
        'article{background:white;border:1px solid #ccd;margin:20px 0;padding:24px;overflow:auto}img{float:left;margin:0 24px 20px 0}pre{white-space:pre-wrap}</style>'
        '<h1>Villeneuve — 12 propositions pour le test</h1><p>'+status+' Un seul groupe : tous les niveaux, relevés et doublons de la mairie.</p>'
        '<p><a href="images/source-3-page-1.png">Aperçu du plan mis au propre</a></p>'+''.join(cards)+'</html>')
    files=[p for p in ROOT.rglob('*') if p.is_file() and p.name!='manifest.json']
    (ROOT/'manifest.json').write_text(json.dumps(dict(schema='doemo.qwen-draft-manifest/1',ready_for_training=False,
        files=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p),size=p.stat().st_size) for p in sorted(files)]),indent=2)+'\n')
    print(encoded(dict(examples=len(examples),groups=1,split='test',ready_for_training=False)))


if __name__=='__main__':
    main()
