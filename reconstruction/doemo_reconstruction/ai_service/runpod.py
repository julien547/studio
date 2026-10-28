"""RunPod REST v1, checked against official docs on 2026-10-28.

No delete, migrate, reset or create operation is implemented. Pod identity is
resolved afresh against both persistent volume and controlled service marker.
"""
import re
import time
import httpx


class RunPod:
    def __init__(self,api_key,volume_id,service='DOEMO-STUDIO-IA',client=None):
        if not api_key or not volume_id:raise ValueError('Configuration RunPod manquante')
        self.volume_id,self.service=volume_id,service
        self.http=client or httpx.Client(base_url='https://rest.runpod.io/v1',
            headers={'Authorization':'Bearer '+api_key},timeout=20,follow_redirects=False)

    def discover(self):
        response=self.http.get('/pods');response.raise_for_status();pods=response.json()
        matches=[p for p in pods if p.get('networkVolumeId')==self.volume_id and
                 (p.get('env',{}).get('DOEMO_SERVICE_ID')==self.service or p.get('name')==self.service) and
                 p.get('desiredStatus')!='TERMINATED']
        if len(matches)!=1:raise RuntimeError('Pod absent ou ambigu : réassociation contrôlée nécessaire')
        if not re.fullmatch('[a-zA-Z0-9_-]+',matches[0]['id']):raise ValueError('Pod ID invalide')
        return matches[0]

    def ensure_started(self):
        pod=self.discover()
        if pod['desiredStatus']=='EXITED':
            response=self.http.post('/pods/'+pod['id']+'/start');response.raise_for_status()
        elif pod['desiredStatus']!='RUNNING':
            raise RuntimeError('Pod indisponible : vérifier la capacité GPU ou la migration')
        # RUNNING is desired state, not a readiness signal. Worker probes must pass next.
        return pod

    def stop(self,expected_id):
        pod=self.discover()
        if pod['id']!=expected_id:raise RuntimeError('Migration pendant arrêt : nouvelle vérification requise')
        if pod['desiredStatus']=='RUNNING':
            response=self.http.post('/pods/'+pod['id']+'/stop');response.raise_for_status()

    @staticmethod
    def worker_url(pod,port):
        if type(port) is not int or not 1024<=port<=65535:raise ValueError('Port invalide')
        return f"https://{pod['id']}-{port}.proxy.runpod.net"


class IdleController:
    """Call under the same admission lock as submit; single orchestration owner."""
    def __init__(self,store,runpod,worker,gate):
        self.store,self.runpod,self.worker,self.gate=store,runpod,worker,gate
        self.last_busy=time.time()

    def tick(self,now=None):
        now=time.time() if now is None else now
        with self.gate:
            if not self.store.idle(now,seconds=0):self.last_busy=now;return False
            pod=self.runpod.discover()
            if pod['desiredStatus']!='RUNNING':return False
            health=self.worker.health(pod)
            if health.get('pod_id')!=pod['id']:
                self.last_busy=now;return False
            if not health.get('ready') or health.get('stop_safe') is not True or any(health.get(k)!=0 for k in ('active','queued','unsaved')):
                self.last_busy=now;return False
            # Observe a full 30 minutes of idle in this ownership session as well.
            if not self.store.idle(now) or now-self.last_busy<1800:return False
            if not self.worker.drain(pod):self.last_busy=now;return False
            try:self.runpod.stop(pod['id'])
            except Exception:
                # Keep worker drained if stop response is unknown; operator must reconcile.
                raise
            return True
