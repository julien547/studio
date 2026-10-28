"""Verified immutable artifact bundles. No chmod/rename/SQLite on network FUSE."""
import hashlib
import json
import shutil
import uuid
from pathlib import Path


def sha256(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
 return h.hexdigest()


def preserve(files,destination,metadata):
 destination=Path(destination)/uuid.uuid4().hex
 destination.mkdir(parents=True,exist_ok=False)
 entries=[]
 for name,source in files.items():
  if Path(name).name!=name or name in ('','.', '..','manifest.json'):raise ValueError('Nom d’artefact invalide')
  source=Path(source)
  if source.is_symlink() or not source.is_file():raise ValueError('Artefact régulier requis')
  before=sha256(source);shutil.copyfile(source,destination/name)
  if before!=sha256(destination/name) or before!=sha256(source):raise ValueError('Copie incomplète ou artefact encore en écriture')
  entries.append({'name':name,'sha256':before,'bytes':source.stat().st_size})
 manifest={'schema':'doemo.artifacts/1','id':destination.name,'files':entries,'metadata':metadata}
 # The final manifest is the commit marker; interrupted copies are not versions.
 with (destination/'manifest.json').open('x') as f:json.dump(manifest,f,ensure_ascii=False,sort_keys=True)
 return destination/'manifest.json'


def verify(path):
 path=Path(path);value=json.loads(path.read_text())
 if value.get('schema')!='doemo.artifacts/1' or not value.get('files'):raise ValueError('Manifeste invalide')
 for f in value['files']:
  if Path(f['name']).name!=f['name'] or f['name'] in ('.','..'):raise ValueError('Chemin refusé')
  target=path.parent/f['name']
  if target.is_symlink() or target.stat().st_size!=f['bytes'] or sha256(target)!=f['sha256']:raise ValueError('Artefact corrompu')
 return value
