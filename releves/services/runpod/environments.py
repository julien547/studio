"""Snapshot/restore exact validated /opt environments, using only the stdlib.

Archives and manifest live on persistent /workspace. Existing environments and
models are never overwritten. Work, hashing and extraction use /tmp; the final
installation is under /opt (no chmod/rename on the FUSE volume).
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path,PurePosixPath

DEFAULT={'gateway':'/opt/doemo-gateway-venv','qwen':'/opt/doemo-qwen-venv','paddleocr':'/opt/doemo-ocr-venv','rtmdet':'/opt/doemo-rtmdet-venv'}


def checksum(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):h.update(block)
    return h.hexdigest()


def relative(value):
    p=PurePosixPath(value)
    if not value or p.is_absolute() or any(x in ('.','..','') for x in p.parts):raise ValueError('Chemin de restauration refusé')
    return p


def snapshot(directory,envs=None):
    root=Path(directory);root.mkdir(parents=True,exist_ok=False)
    manifest={'version':1,'machine':platform.machine(),'image_tag':os.environ.get('DOEMO_RUNTIME_IMAGE_TAG'),
              'environments':{}}
    for name,folder in (envs or DEFAULT).items():
        folder=Path(folder)
        if not folder.is_relative_to('/opt') or not (folder/'bin/python').is_file():raise ValueError('Environnement /opt absent : '+name)
        probe=subprocess.run([str(folder/'bin/python'),'-c','import sys,json;print(json.dumps({"base":sys.base_prefix,"version":sys.version}))'],capture_output=True,timeout=30,check=True)
        info=json.loads(probe.stdout);roots=[folder.relative_to('/opt').as_posix()]
        base=Path(info['base'])
        if not base.is_relative_to('/opt') and not base.is_relative_to('/usr'):
            raise ValueError('Interpréteur de base éphémère hors /opt : le rendre persistant dans l’image avant capture ('+name+')')
        if base.is_relative_to('/opt') and base!=folder and not base.is_relative_to(folder):roots.append(base.relative_to('/opt').as_posix())
        # Dereference venv symlinks so restoration contains no executable link tricks.
        archive=root/(name+'.tar.gz')
        with tarfile.open(archive,'w:gz',dereference=True) as tar:
            for member in roots:tar.add(Path('/opt')/member,arcname=member)
        manifest['environments'][name]={'root':roots[0],'roots':roots,'archive':archive.name,
            'sha256':checksum(archive),'python_version':info['version'],'base_prefix':info['base']}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest


def restore(manifest_path,opt_root=Path('/opt')):
    manifest_path=Path(manifest_path);manifest=json.loads(manifest_path.read_text());opt_root=Path(opt_root)
    if manifest.get('version')!=1 or manifest.get('machine')!=platform.machine():raise ValueError('Archive incompatible avec cette architecture')
    if manifest.get('image_tag') and manifest['image_tag']!=os.environ.get('DOEMO_RUNTIME_IMAGE_TAG'):
        raise ValueError('Utiliser la même image de conteneur que la sauvegarde')
    result={}
    for name,env in manifest['environments'].items():
        root=str(relative(env['root']));target=opt_root/root
        if target.exists():
            if not (target/'bin/python').is_file():raise ValueError('Environnement existant incomplet, contrôle manuel requis : '+name)
            result[name]='preserved';continue
        roots=[str(relative(r)) for r in env['roots']]
        if root not in roots:raise ValueError('Racine absente du manifeste')
        archive_name=str(relative(env['archive']))
        archive=manifest_path.parent/archive_name
        if checksum(archive)!=env['sha256']:raise ValueError('Empreinte de l’archive invalide : '+name)
        with tempfile.TemporaryDirectory(prefix='doemo-restore-',dir='/tmp') as tmp:
            with tarfile.open(archive,'r:gz') as tar:
                members=tar.getmembers()
                if len(members)>200000 or sum(m.size for m in members)>100*1024**3:raise ValueError('Archive excessive')
                for m in members:
                    p=relative(m.name)
                    if not (m.isfile() or m.isdir()) or not any(p==PurePosixPath(r) or p.is_relative_to(r) for r in roots):raise ValueError('Membre de restauration refusé')
                # All members are regular files/directories under allowlisted roots.
                tar.extractall(tmp,members=members,filter='data')
            for r in sorted(roots,key=lambda x:x==root):
                destination=opt_root/r
                if destination.exists():continue
                for parent in destination.parents:
                    if parent==opt_root.parent:break
                    if parent.is_symlink():raise ValueError('Parent symbolique refusé')
                destination.parent.mkdir(parents=True,exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='.doemo-install-',dir=destination.parent) as staging:
                    prepared=Path(staging)/'environment';shutil.copytree(Path(tmp)/r,prepared)
                    if destination.exists():raise ValueError('Installation concurrente détectée')
                    os.rename(prepared,destination) # /opt only; never FUSE
        result[name]='restored'
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['snapshot','restore']);p.add_argument('path');args=p.parse_args()
    print(json.dumps(snapshot(args.path) if args.action=='snapshot' else restore(args.path),indent=2))
if __name__=='__main__':main()
