"""Reassemble the supplied Git parts in order, outside the public root/checkouts."""
import argparse
from pathlib import Path
import hashlib
import shutil
import zipfile

parser=argparse.ArgumentParser()
parser.add_argument('parts',nargs='+',type=Path)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
if args.parts!=sorted(args.parts):
    parser.error('Indiquer les parties dans l’ordre lexical (part-aa, part-ab…)')
args.output.parent.mkdir(parents=True,exist_ok=True)
try:
    with args.output.open('xb') as dest:
        for part in args.parts:
            with part.open('rb') as source:shutil.copyfileobj(source,dest)
    if args.output.stat().st_size>512*1024**2:raise ValueError('Archive supérieure à 512 Mio')
    with zipfile.ZipFile(args.output) as archive:
        infos=archive.infolist()
        if len(infos)>5000 or sum(x.file_size for x in infos)>1024**3 or any(x.file_size>64*1024**2 or x.file_size/max(1,x.compress_size)>200 for x in infos):raise ValueError('Limites de décompression dépassées')
        if archive.testzip() is not None:raise ValueError('CRC de l’archive incorrect')
    with args.output.open('rb') as source:print(hashlib.file_digest(source,'sha256').hexdigest())
except Exception:
    # Preserve the failed output for diagnosis; never overwrite a pre-existing file.
    raise
