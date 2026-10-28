"""CPU validation/conversion of OVH exports. No model imports or GPU operations."""
import json
import math
import zipfile
from pathlib import Path,PurePosixPath


def unpack(bundle,destination):
 if Path(bundle).stat().st_size>256*1024**2:raise ValueError('Archive compressée excessive')
 destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
 with zipfile.ZipFile(bundle) as z:
  infos=z.infolist()
  if len(infos)>20000 or sum(i.file_size for i in infos)>1024**3:raise ValueError('Archive excessive')
  names=set()
  for info in infos:
   p=PurePosixPath(info.filename)
   if p.is_absolute() or '..' in p.parts or '\\' in info.filename or info.filename in names or ((info.external_attr>>16)&0o170000)==0o120000:raise ValueError('Chemin ZIP refusé')
   names.add(info.filename)
   if info.is_dir():continue
   if p.suffix not in ('.json','.jsonl','.png'):raise ValueError('Format inattendu')
   target=destination.joinpath(*p.parts);target.parent.mkdir(parents=True,exist_ok=True)
   with z.open(info) as source,target.open('xb') as out:
    import shutil
    shutil.copyfileobj(source,out)
 return destination


def detection_splits(directory):
 root=Path(directory);data=json.loads((root/'coco.json').read_text());categories=data['categories']
 if not categories or len({c['id'] for c in categories})!=len(categories):raise ValueError('Classes absentes ou dupliquées')
 result={};groups={};ids=set();category_ids={c['id'] for c in categories}
 for im in data['images']:
  path=(root/im['file_name']).resolve()
  if not path.is_relative_to(root.resolve()) or not path.is_file() or im['id'] in ids:raise ValueError('Image absente ou identifiant dupliqué')
  from PIL import Image
  with Image.open(path) as picture:
   if picture.format!='PNG' or picture.size!=(im['width'],im['height']) or picture.width*picture.height>40_000_000:raise ValueError('Image incompatible avec le repère COCO')
   picture.verify()
  if im['split'] not in ('train','validation','test'):raise ValueError('Split invalide')
  ids.add(im['id']);key=im['document_sha256']
  if key in groups and groups[key]!=im['split']:raise ValueError('Même document dans plusieurs splits')
  groups[key]=im['split']
 for a in data['annotations']:
  if a['image_id'] not in ids or a['category_id'] not in category_ids:raise ValueError('Référence COCO invalide')
  b=a['bbox'];im=next(i for i in data['images'] if i['id']==a['image_id'])
  if len(b)!=4 or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in b) or min(b[:2])<0 or min(b[2:])<=0 or b[0]+b[2]>im['width']+1e-6 or b[1]+b[3]>im['height']+1e-6:raise ValueError('Boîte COCO hors image')
 for split in ('train','validation','test'):
  images=[i for i in data['images'] if i['split']==split];selected={i['id'] for i in images}
  annotations=[a for a in data['annotations'] if a['image_id'] in selected]
  if not images or not annotations:raise ValueError('Images et annotations requises dans chaque split')
  value={'images':images,'annotations':annotations,'categories':categories}
  path=root/(split+'.json');path.write_text(json.dumps(value));result[split]=str(path)
 trained={a['category_id'] for a in data['annotations'] if a['image_id'] in {i['id'] for i in data['images'] if i['split']=='train'}}
 if trained!=category_ids:raise ValueError('Chaque catégorie doit être représentée en entraînement')
 return result,[c['name'] for c in sorted(categories,key=lambda c:c['id'])]


def ocr_splits(directory):
 root=Path(directory);data=[json.loads(line) for line in (root/'ocr.jsonl').read_text().splitlines() if line.strip()]
 result={}
 for split in ('train','validation','test'):
  rows=[r for r in data if r['split']==split]
  if not rows:raise ValueError('Chaque split OCR doit contenir des images distinctes')
  lines=[]
  for row in rows:
   text=row['text'];p=(root/row['image']).resolve()
   if not p.is_relative_to(root.resolve()) or not p.is_file():raise ValueError('Image OCR inaccessible')
   if not text or '\n' in text or '\r' in text or '\t' in text:raise ValueError('Une seule ligne de transcription par image pour cet adaptateur PaddleOCR')
   lines.append(row['image']+'\t'+text)
  out=root/(split+'-ocr.txt');out.write_text('\n'.join(lines)+'\n');result[split]=str(out)
 return result


def edit_distance(a,b):
 row=list(range(len(b)+1))
 for i,x in enumerate(a,1):
  new=[i]
  for j,y in enumerate(b,1):new.append(min(new[-1]+1,row[j]+1,row[j-1]+(x!=y)))
  row=new
 return row[-1]


def ocr_metrics(pairs):
 pairs=list(pairs)
 if not pairs or any(not isinstance(a,str) or not isinstance(b,str) for a,b in pairs):raise ValueError('Paires texte réel/prédit requises')
 chars=sum(len(a) for a,b in pairs);words=sum(len(a.split()) for a,b in pairs)
 if not chars or not words:raise ValueError('Référence OCR vide')
 return {'cer':sum(edit_distance(a,b) for a,b in pairs)/chars,'wer':sum(edit_distance(a.split(),b.split()) for a,b in pairs)/words,'samples':len(pairs),'normalization':'none'}
