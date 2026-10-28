#!/usr/bin/env python3
"""Inspect/restore missing components without overwriting existing installations.

Default is dry-run. Execute on RunPod, as root, with --apply after archive-layout
inspection. Each component extracts into local staging next to its destination;
rename publishes only into a missing target. Archives are opened read-only.
"""
import argparse
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import tarfile
import tempfile
import time

BACKUPS=Path('/workspace/doemo-studio/backups')
PYTHON='cpython-3.11.18-linux-x86_64-gnu'
DEFAULT=[
 {'archive':'python311.tar.gz','component':PYTHON,'target':'/root/.local/share/uv/python/'+PYTHON},
 *[{'archive':name+'.tar.gz','component':name,'target':'/opt/'+name} for name in ('doemo-qwen-venv','doemo-ocr-venv','doemo-rtmdet-venv')],
 {'archive':'paddlex.tar.gz','component':'.paddlex','target':'/root/.paddlex'}]
EXTERNAL_LINKS=('/root/.local/share/uv/python/','/usr/bin/python','/usr/local/bin/python')


def inspect(archive,component):
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers()
    if len(members)>1_000_000 or sum(m.size for m in members)>150*1024**3:raise ValueError('Archive hors limites')
    paths=[]
    for member in members:
        name=PurePosixPath(member.name)
        if name.is_absolute() or '..' in name.parts:raise ValueError('Chemin archivé dangereux')
        paths.append(name)
    prefixes={PurePosixPath(*p.parts[:p.parts.index(component)+1]) for p in paths if component in p.parts}
    if len(prefixes)!=1:raise ValueError('Racine absente ou ambiguë : fournir un manifeste après inspection')
    prefix=prefixes.pop();selected=[];names=set();links=set()
    for member,name in zip(members,paths):
        if name==prefix or name in prefix.parents:
            if not member.isdir():raise ValueError('Racine non répertoire')
            continue
        if prefix not in name.parents:raise ValueError('Autre composant présent dans archive')
        relative=name.relative_to(prefix)
        if str(relative) in names:raise ValueError('Entrée archivée dupliquée')
        names.add(str(relative))
        if any(parent in links for parent in relative.parents):raise ValueError('Écriture sous lien symbolique')
        if not (member.isfile() or member.isdir() or member.issym()):raise ValueError('Type archivé non pris en charge')
        if member.issym():
            target=PurePosixPath(member.linkname)
            if target.is_absolute():
                if '..' in target.parts or not any(str(target).startswith(p) for p in EXTERNAL_LINKS):raise ValueError('Lien absolu non autorisé')
            else:
                stack=list(relative.parent.parts)
                for part in target.parts:
                    if part=='..':
                        if not stack:raise ValueError('Lien sortant du composant')
                        stack.pop()
                    elif part!='.':stack.append(part)
            links.add(relative)
        selected.append((member,relative))
    # Archive order cannot bypass symlink-parent checks.
    if any(any(parent in links for parent in rel.parents) for _,rel in selected):raise ValueError('Chemin sous lien symbolique')
    return selected


def restore(spec,backups=BACKUPS,apply=False):
    archive=backups/spec['archive'];target=Path(spec['target'])
    if target.exists() or target.is_symlink():return {'component':spec['component'],'status':'present_unchanged','functional_test_required':True}
    selected=inspect(archive,spec['component'])
    result={'component':spec['component'],'archive':str(archive),'target':str(target),'members':len(selected),'bytes':sum(m.size for m,_ in selected),'status':'dry_run'}
    if not apply:return result
    if str(target).startswith('/workspace/') or str(target).startswith('/tmp/'):
        raise ValueError('Restauration des environnements/caches sur stockage local /opt ou /root uniquement')
    existing_parent=target.parent
    while not existing_parent.exists():existing_parent=existing_parent.parent
    required=sum(m.size for m,_ in selected)+1024**3
    if shutil.disk_usage(existing_parent).free<required:
        raise ValueError('Espace local insuffisant pour restaurer ce composant avec une marge de 1 Gio')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.'+target.name+'-restore-',dir=target.parent) as tmp:
        staging=Path(tmp)/'component';staging.mkdir()
        with tarfile.open(archive,'r:gz') as tar:
            for member,relative in selected:
                path=staging/relative
                if member.isdir():path.mkdir(parents=True,exist_ok=True);continue
                path.parent.mkdir(parents=True,exist_ok=True)
                if member.issym():path.symlink_to(member.linkname)
                else:
                    with tar.extractfile(member) as source,path.open('xb') as dest:shutil.copyfileobj(source,dest)
                    path.chmod(member.mode&0o777)
        if target.exists() or target.is_symlink():raise FileExistsError('Destination apparue pendant restauration')
        # Single root-owned bootstrap process; never run two restorations concurrently.
        staging.rename(target)
    result['status']='restored_requires_functional_test';return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--manifest');parser.add_argument('--inventory',action='store_true')
    parser.add_argument('--include-service',action='store_true',help='Also restore the separately backed-up communication runtime')
    args=parser.parse_args()
    if args.inventory:
        for archive in sorted(BACKUPS.glob('*.tar.gz')):
            with tarfile.open(archive,'r:gz') as tar:
                print(json.dumps({'archive':archive.name,'first_entries':[m.name for _,m in zip(range(12),tar)]}))
        return
    specs=json.loads(Path(args.manifest).read_text()) if args.manifest else DEFAULT
    if args.include_service:
        specs=[*specs,{'archive':'doemo-service-venv.tar.gz','component':'doemo-service-venv','target':'/opt/doemo-service-venv'}]
    if args.apply:
        from inventory import collect,require_restore_host
        require_restore_host(collect())
        import fcntl
        lock=open('/tmp/doemo-restore.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    failed=False
    for spec in specs:
        try:result=restore(spec,apply=args.apply)
        except Exception as error:result={'component':spec['component'],'status':'error','error':str(error)};failed=True
        print(json.dumps({'at':time.time(),**result}),flush=True)
    if args.apply:
        parent=Path('/root/.local/share/uv/python');alias=parent/'cpython-3.11-linux-x86_64-gnu'
        if (parent/PYTHON/'bin/python3.11').is_file() and not os.path.lexists(alias):alias.symlink_to(PYTHON)
    if failed:raise SystemExit(1)

if __name__=='__main__':main()
