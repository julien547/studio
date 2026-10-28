"""Operator GPU acceptance, never invoked by the web API or on application boot.

Runs two training epochs with pause/resume and a separate cancellation check.
Writes an accepted profile ONLY after all real subprocess checks pass. Requires
an authorized maintenance window; existing gateway/vLLM processes are not stopped.
"""
import argparse
import asyncio
import contextlib
import fcntl
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from artifacts import sha256,verify
from compute import exclusive,require_idle_gpu
from training_service import Manager,DRIVER,PADDLE_DRIVER,QWEN_DRIVER,runtime_hash,digest,encoded


async def acceptance(args):
    if not args.authorize_gpu_training or not args.maintenance_confirmed:raise ValueError('Autorisation GPU et fenêtre de maintenance explicites requises')
    root=Path(args.output).resolve()
    if not os.path.ismount('/workspace') or not root.is_relative_to('/workspace/doemo-studio'):raise ValueError('Volume persistant requis')
    destination=Path(args.profile_output)
    if destination.exists():raise ValueError('Le profil de sortie existe déjà ; choisir un fichier neuf')
    engine=getattr(args,'engine','rtmdet');paddle=engine=='paddleocr';qwen=engine=='qwen'
    if engine not in ('rtmdet','paddleocr','qwen'):raise ValueError('Moteur non pris en charge')
    from qwen_training_data import model_hash
    # Same canonical profile fingerprint as OVH/gateway, with no secrets.
    public={'engine':engine,'driver':'qwen.lora/1' if qwen else 'paddleocr.recognition/1' if paddle else 'rtmdet.training/1','driver_sha256':sha256(QWEN_DRIVER if qwen else PADDLE_DRIVER if paddle else DRIVER),'runtime_sha256':runtime_hash(),
            'config_sha256':sha256(args.config),'weights_sha256':model_hash(args.weights) if qwen else sha256(args.weights),
            'acceptance':{'training_completed':False,'resume_verified':False,'inference_preemption_verified':False,'cancel_verified':False,'report_sha256':'0'*64}}
    for p in (args.config,args.weights):
        if not Path(p).resolve().is_relative_to('/workspace/doemo-studio'):raise ValueError('Profil et poids persistants requis')
    profile={'public':public,'config':str(Path(args.config).resolve()),'weights':str(Path(args.weights).resolve())}
    if paddle:
        from paddle_training import source_hash
        if not args.repository or not args.dictionary:raise ValueError('Dépôt source et dictionnaire requis pour PaddleOCR')
        for key in ('repository','dictionary'):
            local=Path(getattr(args,key)).resolve()
            if not local.is_relative_to('/workspace/doemo-studio'):raise ValueError('Sources OCR persistantes requises')
            profile[key]=str(local)
        public.update(source_sha256=source_hash(profile['repository']),dictionary_sha256=sha256(profile['dictionary']))
    public['id']=digest(public)
    environment=lambda:dict({k:v for k,v in os.environ.items() if k!='RUNPOD_API_KEY'},HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    manager=Manager(root,asyncio.Lock(),lambda:True,lambda:False,lambda:None,environment,
                    lambda:profile if engine=='rtmdet' else None,lambda:profile if paddle else None,lambda:profile if qwen else None)
    # Validate the snapshot and all files without relying on archive paths.
    from training_data import unpack
    with tempfile.TemporaryDirectory(prefix='doemo-acceptance-data-',dir='/tmp') as tmp:
        data=unpack(args.dataset,Path(tmp)/'data');snapshot=json.loads((data/'examples.json').read_text())
    def spec():return {'id':uuid.uuid4().hex,'engine':engine,'profile_id':public['id'],'parameters':{'epochs':2,'batch_size':1,'learning_rate':.0001},
                       'dataset_id':uuid.uuid4().hex,'dataset_sha256':digest(snapshot),'archive_sha256':sha256(args.dataset)}
    async def controlled_run(ident,action):
        task=asyncio.create_task(manager.run(ident))
        try:
            deadline=time.monotonic()+args.timeout
            while time.monotonic()<deadline:
                if task.done():raise ValueError('Pilote terminé avant le contrôle demandé')
                observed=await asyncio.to_thread(manager.store.state,ident) if qwen and action=='pause' else {}
                progressed=not (qwen and action=='pause') or observed.get('iteration',0)>=1
                if progressed and manager.proc and manager.proc.returncode is None and manager.control_file:
                    await manager.control(ident,action);break
                await asyncio.sleep(.1)
            else:raise ValueError('Délai dépassé avant le contrôle demandé')
            await asyncio.wait_for(task,max(.1,deadline-time.monotonic()))
        finally:
            if not task.done():
                # Manager cancellation reaps its child inside the compute lock.
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):await task
    first=spec();manager.store.admit(first['id'],first,Path(args.dataset),profile)
    await controlled_run(first['id'],'pause')
    state=manager.store.state(first['id'])
    if state['status']!='paused' or not state.get('checkpoint'):raise ValueError('Pause avec checkpoint non vérifiée')
    checkpoint=verify(manager.store.artifact(first['id'],state['checkpoint']))
    if qwen:
        if checkpoint['metadata'].get('cursor',0)<=0 or checkpoint['metadata'].get('cursor',0)>=state.get('total_iterations',0):raise ValueError('Pause Qwen après un vrai batch, avant la fin de l’entraînement requise')
    elif checkpoint['metadata'].get('epoch')!=1:raise ValueError('Pause attendue après la première époque')
    if manager.lock.locked():raise ValueError('GPU non libéré après la pause')
    # Run an actual inference using the same production probe and shared compute guard.
    log=root/'training/logs'/first['id']/'acceptance-paddleocr.log'
    import gateway
    result=await gateway.execute(gateway.ENGINES['paddleocr'],gateway.PROBE,['paddleocr'],log,480)
    if result!=0:raise ValueError('Inférence prioritaire non vérifiée')
    await manager.control(first['id'],'resume')
    await asyncio.wait_for(manager.run(first['id']),args.timeout)
    completed=manager.store.public(first['id'])
    if completed['status']!='completed' or not completed.get('artifacts_verified'):raise ValueError('Reprise et résultats non vérifiés')
    if completed.get('epoch')!=2:raise ValueError('Reprise de la deuxième époque non attestée')
    second=spec();manager.store.admit(second['id'],second,Path(args.dataset),profile)
    await controlled_run(second['id'],'cancel')
    if manager.store.state(second['id'])['status']!='cancelled' or manager.lock.locked():raise ValueError('Annulation non vérifiée')
    with exclusive():require_idle_gpu()
    report={'schema':'doemo.training-acceptance/1','created':time.time(),'engine':engine,'training_job':first['id'],'cancel_job':second['id'],
            'runtime_sha256':public['runtime_sha256'],'driver_sha256':public['driver_sha256'],'config_sha256':public['config_sha256'],'weights_sha256':public['weights_sha256'],
            'checks':{'training_completed':True,'resume_verified':True,'inference_preemption_verified':True,'cancel_verified':True},
            'result_manifest':completed['result_manifest'],'metrics':completed['result']['metadata']['metrics']}
    if paddle:report.update(source_sha256=public['source_sha256'],dictionary_sha256=public['dictionary_sha256'])
    evidence=root/'training/acceptance'/uuid.uuid4().hex;evidence.mkdir(parents=True,exist_ok=False)
    report_file=evidence/'report.json';report_file.write_text(encoded(report))
    accepted={k:public[k] for k in ('engine','driver_sha256','runtime_sha256','config_sha256','weights_sha256')}
    accepted.update(config=profile['config'],weights=profile['weights'],acceptance=dict(report['checks'],report_sha256=sha256(report_file)))
    if paddle:accepted.update(repository=profile['repository'],dictionary=profile['dictionary'],source_sha256=public['source_sha256'],dictionary_sha256=public['dictionary_sha256'])
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('x') as out:out.write(encoded(accepted))
    return {'profile':str(destination),'report':str(report_file)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('dataset','config','weights','profile-output'):p.add_argument('--'+field,required=True)
    p.add_argument('--engine',choices=['rtmdet','paddleocr','qwen'],default='rtmdet');p.add_argument('--repository');p.add_argument('--dictionary')
    p.add_argument('--output',default='/workspace/doemo-studio');p.add_argument('--timeout',type=int,default=3600)
    p.add_argument('--authorize-gpu-training',action='store_true');p.add_argument('--maintenance-confirmed',action='store_true')
    args=p.parse_args()
    if not args.authorize_gpu_training or not args.maintenance_confirmed:p.error('Les deux autorisations explicites sont requises')
    with open('/tmp/doemo-gateway.lock','a') as guard:
        try:fcntl.flock(guard.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:p.error('Gateway actif : organiser la maintenance avec la session de déploiement')
        with exclusive():require_idle_gpu()
        print(json.dumps(asyncio.run(acceptance(args)),ensure_ascii=False))

if __name__=='__main__':main()
