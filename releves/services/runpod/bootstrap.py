"""Container start command, copied onto persistent storage before enabling lifecycle.

python3 /workspace/doemo-studio/services/runpod/bootstrap.py
Requires only the base container Python until the gateway environment is restored.
"""
import fcntl
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from environments import DEFAULT,restore


def main():
    root=Path(os.environ.get('DOEMO_PERSISTENT_ROOT','/workspace/doemo-studio'))
    logs=root/'logs';logs.mkdir(parents=True,exist_ok=True)
    report=logs/('bootstrap-'+uuid.uuid4().hex+'.json')
    manifest=Path(os.environ.get('DOEMO_RESTORE_MANIFEST',root/'restore/current/manifest.json'))
    with open('/tmp/doemo-bootstrap.lock','a') as guard:
        fcntl.flock(guard.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            missing=[name for name,path in DEFAULT.items() if not (Path(path)/'bin/python').is_file()]
            if missing:
                if not manifest.is_file():raise ValueError('Sauvegarde des environnements absente du volume persistant')
                restored=restore(manifest)
            else:restored={name:'preserved' for name in DEFAULT}
            report.write_text(json.dumps({'at':time.time(),'environments':restored,'ok':True}))
        except Exception as exc:
            report.write_text(json.dumps({'at':time.time(),'ok':False,'error':type(exc).__name__}))
            print('Restauration interrompue ; vérifier le manifeste et les journaux persistants.',file=sys.stderr)
            return 1
    env={k:v for k,v in os.environ.items() if k!='RUNPOD_API_KEY'}
    env.update(UV_CACHE_DIR='/tmp/doemo-uv-cache',PIP_CACHE_DIR='/tmp/doemo-pip-cache')
    gateway=Path(DEFAULT['gateway'])/'bin/python'
    os.chdir(Path(__file__).parent)
    os.execve(gateway,[str(gateway),'-m','uvicorn','gateway:app','--host','0.0.0.0','--port',os.environ.get('DOEMO_RUNPOD_GATEWAY_PORT','8000'),'--workers','1','--no-access-log'],env)

if __name__=='__main__':sys.exit(main())
