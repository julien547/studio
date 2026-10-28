"""POSIX-only compute exclusion, shared by the gateway and training subprocesses."""
import contextlib
import fcntl
import subprocess

@contextlib.contextmanager
def exclusive():
    with open('/tmp/doemo-compute.lock','a') as handle:
        try:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('GPU réservé par un autre processus DOEMO')
        try:yield
        finally:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

def require_idle_gpu():
    result=subprocess.run(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10,check=True)
    # This also detects a pre-existing vLLM server: never stop or compete with it.
    if result.stdout.strip():raise ValueError('Processus GPU préexistant ; organiser la disponibilité avec la session de déploiement')
