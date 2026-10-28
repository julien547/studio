#!/usr/bin/env python3
"""Read-only identity/storage inventory, independent of the three model venvs.

Environment presence, imports and model inference are deliberately separate facts.
Never infer the contents of RunPod from an OVH checkout or from this dev workspace.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess

BASE=Path('/workspace/doemo-studio')
ENVIRONMENTS={name:Path('/opt')/('doemo-'+folder+'-venv')
              for name,folder in [('qwen','qwen'),('paddleocr','ocr'),('rtmdet','rtmdet')]}


def interpreter_state(folder):
    python=folder/'bin/python'
    info={'path':str(folder),'directory_present':folder.is_dir(),
          'python_entry_present':os.path.lexists(python),
          'python_executable':python.is_file() and os.access(python,os.X_OK),
          'inference_verified':False}
    if python.is_symlink():info['python_link']=os.readlink(python)
    if not info['directory_present']:info['state']='environment_missing'
    elif not info['python_entry_present']:info['state']='interpreter_missing'
    elif not python.exists():info['state']='interpreter_target_missing'
    elif not info['python_executable']:info['state']='interpreter_not_executable'
    else:info['state']='present_requires_functional_test'
    return info


def collect(base=BASE,environments=None):
    result={'at':datetime.now(timezone.utc).isoformat(),
            'identity':{'hostname':socket.gethostname(),'runpod_pod_id':os.environ.get('RUNPOD_POD_ID')},
            'gpu':{'query_ok':False},'storage':{},
            'environments':{k:interpreter_state(v) for k,v in (environments or ENVIRONMENTS).items()}}
    try:
        query=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,driver_version',
                              '--format=csv,noheader'],capture_output=True,text=True,timeout=20,check=True)
        result['gpu']={'query_ok':True,'devices':query.stdout.strip().splitlines()}
    except (OSError,subprocess.SubprocessError) as error:
        result['gpu']['error']=type(error).__name__
    for name in ('backups','models','exports'):
        path=base/name
        info={'path':str(path),'present':path.is_dir()}
        if path.is_dir():
            try:
                entries=sorted(path.iterdir())
                info['entries']=[p.name for p in entries[:30]]
                info['entry_count']=len(entries)
            except OSError as error:info['error']=type(error).__name__
        result['storage'][name]=info
    try:
        mount=subprocess.run(['findmnt','-n','-T',str(base),'-o','TARGET,FSTYPE'],
                             capture_output=True,text=True,timeout=10,check=True)
        result['storage']['mount']=mount.stdout.strip()
    except (OSError,subprocess.SubprocessError):result['storage']['mount']=None
    result['local_free_bytes']=shutil.disk_usage('/opt').free
    return result


def require_restore_host(report):
    """Fail closed before automatic mutation if this is not the intended GPU layout."""
    if not report['identity'].get('runpod_pod_id'):
        raise ValueError('Identité RunPod absente : contrôler le Pod actif avant restauration')
    if not report['gpu'].get('query_ok') or not any('RTX A6000' in s for s in report['gpu'].get('devices',[])):
        raise ValueError('GPU RunPod RTX A6000 non vérifié ; restauration automatique refusée')
    for name in ('models','backups'):
        directory=report['storage'][name]
        if not directory.get('present') or directory.get('error') or not directory.get('entry_count'):
            raise ValueError('Stockage persistant manquant ou non vérifié : '+name)
    mount=report['storage'].get('mount')
    # An ordinary container root does not establish that the network volume is mounted.
    if not mount or mount.split()[0] not in ('/workspace','/workspace/doemo-studio'):
        raise ValueError('Montage persistant /workspace non confirmé ; contrôler le volume RunPod')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--require-runpod',action='store_true')
    args=parser.parse_args();report=collect();print(json.dumps(report,ensure_ascii=False,indent=2))
    if args.require_runpod:
        try:require_restore_host(report)
        except ValueError as error:raise SystemExit(str(error))


if __name__=='__main__':main()
