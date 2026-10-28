"""OVH lifecycle reconciler: durable intent, exclusive actions and real-idle stop.

A POSIX file lock on the CPU host serializes lifecycle actions with queue admission
and claims. Dashboard reads are cached and never wait for the provider. Gateway
quiescence prevents a direct inference racing with an idle stop. Unknown health
fails closed: it cannot authorize stopping the GPU.
"""
import contextlib
import fcntl
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from fastapi import Depends,HTTPException
from typing import Literal
from .models import Model
from .runpod import RunPod,ProviderError

ENGINES=('qwen','paddleocr','rtmdet')
IDLE_SECONDS=1800
ACTIVE=('queued','running','waiting_gpu','retry_gpu','interrupted')


def enabled():return os.environ.get('DOEMO_RUNPOD_MANAGED','0')=='1'
def configured():return enabled() and bool(os.environ.get('RUNPOD_API_KEY') and os.environ.get('DOEMO_RUNPOD_POD_ID') and os.environ.get('DOEMO_RUNPOD_TOKEN'))
def auto_start():return os.environ.get('DOEMO_RUNPOD_AUTOSTART','1')=='1'
def auto_stop():return os.environ.get('DOEMO_RUNPOD_AUTOSTOP','1')=='1'


@contextlib.contextmanager
def lifecycle_lock(store,blocking=True):
    with (store.root/'gpu-lifecycle.lock').open('a') as handle:
        try:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|(0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:yield False;return
        try:yield True
        finally:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def state(store):
    with store.connect() as c:return dict(c.execute('SELECT * FROM gpu_control WHERE id=1').fetchone())


def update(store,**values):
    with store.connect() as c:c.execute('UPDATE gpu_control SET '+','.join(k+'=?' for k in values)+' WHERE id=1',tuple(values.values()))


def log(store,actor,action,outcome,detail=None):
    # Only controlled metadata; never raw HTTP responses or exception strings.
    with store.connect() as c:c.execute('INSERT INTO gpu_events(actor,action,outcome,detail) VALUES(?,?,?,?)',
                                       (actor,action,outcome,json.dumps(detail or {})))


def pending(store,gpu_only=False):
    with store.connect() as c:
        analyses=c.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','waiting_gpu','retry_gpu','interrupted')"+
                         (" AND json_extract(payload,'$.engine') IN ('qwen','paddleocr','rtmdet')" if gpu_only else '')).fetchone()[0]
        training=c.execute("SELECT count(*) FROM training_runs WHERE status NOT IN ('completed','failed','cancelled')").fetchone()[0]
        return analyses+training


def activity(store,now=None):update(store,last_activity=time.time() if now is None else now)


def gateway_url(pod_id):
    # Pod-based HTTP proxy, independent of ephemeral IP. Explicit override supports
    # a private HTTPS gateway/DNS. Never trust arbitrary URLs in provider responses.
    configured_url=os.environ.get('DOEMO_RUNPOD_ENDPOINT','').rstrip('/')
    port=int(os.environ.get('DOEMO_RUNPOD_GATEWAY_PORT','8000'))
    if not 1<=port<=65535:raise ValueError('Port gateway invalide')
    value=configured_url or f'https://{pod_id}-{port}.proxy.runpod.net'
    p=urlsplit(value)
    if p.scheme!='https' or not p.netloc or p.username or p.query or p.fragment:raise ValueError('Gateway HTTPS requis')
    return value


class Gateway:
    def __init__(self,url,client=None):self.url=url;self.client=client or httpx
    def call(self,path,body=None):
        r=self.client.request('GET' if body is None else 'POST',self.url+path,
            headers={'Authorization':'Bearer '+os.environ.get('DOEMO_RUNPOD_TOKEN','')},json=body,timeout=4,follow_redirects=False)
        r.raise_for_status();value=r.json()
        if not isinstance(value,dict):raise ValueError('Statut gateway invalide')
        return value
    def health(self):return self.call('/health')
    def quiesce(self):return self.call('/quiesce',{})
    def resume(self):return self.call('/resume',{})


def ready(health):
    return health.get('ready') is True and bool(health.get('boot_id')) and all(health.get('engines',{}).get(e) is True for e in ENGINES)


def public_status(store):
    s=state(store)
    pod_id=os.environ.get('DOEMO_RUNPOD_POD_ID') or None
    if s['pod_id']!=pod_id:
        # Never display readiness from the previously configured Pod.
        s.update(phase='unavailable',provider_status=None,engines='{}',observed_at=None,request=None,error=None)
    return {'status':s['phase'] if enabled() else 'not_configured','managed':enabled(),'configured':configured(),
            'pod_name':os.environ.get('DOEMO_RUNPOD_POD_NAME','DOEMO-STUDIO-IA'),
            'pod_id':pod_id,
            'provider_status':s['provider_status'],'engines':json.loads(s['engines']),
            'observed_at':s['observed_at'],'last_activity':s['last_activity'],
            'stale':s['observed_at'] is None or time.time()-s['observed_at']>60,
            'automatic_start':enabled() and auto_start(),'automatic_stop':enabled() and auto_stop(),
            'idle_timeout_seconds':IDLE_SECONDS,'pending_tasks':pending(store),'request':s['request'],
            'error':s['error']}


def request_action(store,action,actor):
    if not configured():raise ValueError('Configurer RunPod sur le backend OVH avant cette action')
    if action not in ('start','stop'):raise ValueError('Action interdite')
    with lifecycle_lock(store):
        s=state(store)
        if action=='stop' and pending(store):
            log(store,actor,'stop','refused',{'reason':'pending_tasks'})
            raise ValueError('Arrêt refusé : une analyse ou une tâche est en attente')
        if s['request']==action or s['pending_action']==action:return public_status(store)
        if s['pending_action'] or s['request']:raise ValueError('Une transition GPU est déjà en cours')
        update(store,request=action,requested_by=actor,next_poll=0,error=None)
        log(store,actor,action,'requested')
    return public_status(store)


class Controller:
    def __init__(self,store,provider=None,gateway_factory=None,clock=time.time):
        self.store=store;self.provider=provider or RunPod();self.gateway_factory=gateway_factory or Gateway;self.clock=clock

    def tick(self):
        if not configured():return
        with lifecycle_lock(self.store,blocking=False) as acquired:
            if not acquired:return
            s=state(self.store);now=self.clock()
            pod_id=os.environ['DOEMO_RUNPOD_POD_ID']
            if s['pod_id']!=pod_id:
                if s['pod_id']:
                    # Intents and health belong to one Pod, never transfer them.
                    update(self.store,request=None,requested_by=None)
                update(self.store,pod_id=pod_id,phase='unavailable',provider_status=None,gateway_url=None,
                       boot_id=None,pending_action=None,action_at=None,next_poll=0,last_activity=now,
                       observed_at=None,failures=0,error=None,engines='{}',quiesced=0)
                log(self.store,'controller','configuration','pod_changed',{'pod_id':pod_id})
                s=state(self.store)
            if s['next_poll']>now:return
            update(self.store,next_poll=now+15)
            try:self.reconcile(s,now)
            except ProviderError as exc:
                failures=s['failures']+1;delay=max(exc.retry_after,min(900,15*2**min(failures,6)))
                update(self.store,phase='provider_error',engines='{}',failures=failures,error=f'API RunPod indisponible ({exc.code}). Nouvelle vérification différée.',next_poll=now+delay)
                log(self.store,'controller','provider','error',{'code':exc.code,'retry_seconds':delay})
            except (httpx.HTTPError,ValueError,KeyError,TypeError):
                update(self.store,phase='unavailable',engines='{}',error='Gateway ou configuration indisponible ; aucun arrêt autorisé.',next_poll=now+30)
                log(self.store,'controller','health','unavailable')

    def reconcile(self,s,now):
        pod_id=os.environ['DOEMO_RUNPOD_POD_ID'];pod=self.provider.get(pod_id)
        if pod['name']!=os.environ.get('DOEMO_RUNPOD_POD_NAME','DOEMO-STUDIO-IA'):
            update(self.store,phase='configuration_error',error='Le Pod ne correspond pas au nom autorisé.',next_poll=now+300);return
        url=gateway_url(pod_id)
        update(self.store,pod_id=pod_id,provider_status=pod['status'],gateway_url=url,observed_at=now)
        pstatus=pod['status'];gpu_jobs=pending(self.store,True)
        if pstatus!='RUNNING':update(self.store,engines='{}')
        desired_start=s['request']=='start' or (gpu_jobs>0 and auto_start())
        if s['pending_action']=='stop':
            if pstatus=='EXITED':
                log(self.store,'controller','stop','completed');update(self.store,pending_action=None,request=None,quiesced=0,phase='stopped',failures=0,error=None)
                s=state(self.store)
            elif now-(s['action_at'] or now)<300:
                update(self.store,phase='stopping');return
            else:
                # Re-read remote state before retrying an uncertain transition.
                update(self.store,pending_action=None);s=state(self.store)
        if pstatus in ('EXITED','ERROR'):
            if desired_start:
                if s['pending_action']=='start' and now-(s['action_at'] or now)<300:
                    update(self.store,phase='starting');return
                if 'start' not in (pod.get('actions') or []):raise ProviderError('start_unavailable')
                # Persist intent BEFORE sending: restart/retry must reconcile first.
                self.transition('start',s,now)
            else:update(self.store,phase='stopped' if pstatus=='EXITED' else 'provider_error',error=None,pending_action=None,request=None)
            return
        if pstatus in ('PROVISIONING','STARTING','STOPPING'):
            update(self.store,phase='starting' if pstatus!='STOPPING' else 'stopping',error=None)
            return
        if pstatus!='RUNNING':
            update(self.store,phase='unavailable',error='État RunPod non exploitable ; aucune action destructive.');return
        gateway=self.gateway_factory(url);health=gateway.health()
        if s['request']=='stop' and not pending(self.store) and health.get('boot_id') and not health.get('busy') and not health.get('restoring'):
            quiet=gateway.quiesce()
            if quiet.get('quiesced') is True and quiet.get('boot_id')==health['boot_id'] and 'stop' in (pod.get('actions') or []):
                update(self.store,quiesced=1);self.transition('stop',state(self.store),now);return
        if not ready(health):
            update(self.store,phase='restoring' if health.get('restoring') else 'warming',engines=json.dumps(health.get('engines',{})),error=health.get('public_error') or None)
            return
        if health.get('draining') and (s['pending_action']!='stop'):
            # Recover quiescence abandoned after controller crash or failed stop.
            gateway.resume();health=gateway.health()
        if not ready(health):return
        newly_ready=s['boot_id']!=health['boot_id'] or s['phase'] in ('starting','warming','restoring')
        update(self.store,phase='busy' if health.get('busy') or pending(self.store,True) else 'ready',
               engines=json.dumps({e:True for e in ENGINES}),boot_id=health['boot_id'],pending_action=None,
               request=None if s['request']=='start' else s['request'],failures=0,error=None,quiesced=0)
        if newly_ready:
            activity(self.store,now);log(self.store,'controller','readiness','ready',{'engines':list(ENGINES)})
        if health.get('busy') or health.get('active_jobs',0):activity(self.store,now);return
        if pending(self.store):
            if s['request']=='stop':update(self.store,request=None);log(self.store,'controller','stop','refused',{'reason':'pending_tasks'})
            return
        local_idle=now-max(state(self.store)['last_activity'],0)
        remote_idle=health.get('idle_seconds')
        manual_stop=s['request']=='stop'
        idle_stop=auto_stop() and local_idle>=IDLE_SECONDS and isinstance(remote_idle,(int,float)) and remote_idle>=IDLE_SECONDS
        if not manual_stop and not idle_stop:return
        if 'stop' not in (pod.get('actions') or []):raise ProviderError('stop_unavailable')
        quiet=gateway.quiesce()
        if quiet.get('quiesced') is not True or quiet.get('boot_id')!=health['boot_id']:
            update(self.store,phase='busy',error='Arrêt différé : activité détectée sur le GPU.');return
        update(self.store,quiesced=1)
        # Admission is still locked and the gateway now rejects new inference.
        self.transition('stop',state(self.store),now)

    def transition(self,action,s,now):
        actor=s['requested_by'] if s['request']==action else 'automation'
        update(self.store,pending_action=action,action_at=now,phase='starting' if action=='start' else 'stopping',last_activity=now if action=='start' else s['last_activity'])
        log(self.store,actor or 'controller',action,'sent')
        try:self.provider.action(os.environ['DOEMO_RUNPOD_POD_ID'],action)
        except ProviderError:
            # An unknown outcome is reconciled from GET, never blindly retried.
            log(self.store,actor or 'controller',action,'unconfirmed');raise


class ControlAction(Model):action:Literal['start','stop']


def attach_gpu(app,store,actor,admin):
    @app.get('/projects/gpu')
    def gpu_status(who=Depends(actor)):return public_status(store)
    @app.post('/projects/gpu/action')
    def gpu_action(data:ControlAction,who=Depends(admin)):
        return request_action(store,data.action,who.login)
    @app.get('/projects/gpu/events')
    def gpu_events(who=Depends(admin)):
        with store.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM gpu_events ORDER BY id DESC LIMIT 100')]


def main():
    import argparse
    from .store import Store
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    controller=Controller(Store(os.environ.get('DOEMO_RELEVES_DATA','/var/lib/doemo-studio/releves')))
    while True:
        controller.tick()
        if args.once:return
        time.sleep(5)

if __name__=='__main__':main()
