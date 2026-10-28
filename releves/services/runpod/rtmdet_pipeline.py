"""RTMDet supervised training driver for an audited MMDetection 3.3 environment.

This is an operator CLI, not a remotely executable arbitrary config endpoint.
Requires explicit --authorize-gpu-training. Its GPU acceptance test has not been
performed by the cloud CPU session. The web capability stays disabled until the
operator acceptance validates training, checkpoint/resume and compute handoff.
"""
import argparse
import json
import re
import math
import shutil
import os
import tempfile
import time
import uuid
from pathlib import Path
from artifacts import preserve,verify,sha256
from training_data import unpack,detection_splits
from compute import exclusive,require_idle_gpu

class Paused(Exception):pass
class Cancelled(Exception):pass


def validate_parameters(epochs,batch_size,learning_rate):
 if not 1<=epochs<=100 or not 1<=batch_size<=4 or not 0<learning_rate<=.001:raise ValueError('Paramètres hors limites conservatrices')


def run(args):
 validate_parameters(args.epochs,args.batch_size,args.learning_rate)
 if not args.authorize_gpu_training:raise ValueError('Autorisation explicite requise : --authorize-gpu-training')
 if getattr(args,'managed_job',None):
  if os.environ.get('DOEMO_TRAINING_CHILD')!='1' or not re.fullmatch('[a-f0-9]{32}',args.managed_job):raise ValueError('Admission gateway requise')
  if not str(Path(args.control).resolve()).startswith('/tmp/doemo-training-control-'):raise ValueError('Contrôle local requis')
  with exclusive():
   require_idle_gpu()
   return _run(args)
 # The operator acceptance CLI also excludes the gateway.
 # Never let it compete with a gateway/inference or another training process.
 import fcntl
 with open('/tmp/doemo-gateway.lock','a') as guard:
  try:fcntl.flock(guard.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise ValueError('Gateway actif : essai GPU uniquement dans une fenêtre de maintenance autorisée')
  with exclusive():
   require_idle_gpu()
   return _run(args)


def _run(args):
 validate_parameters(args.epochs,args.batch_size,args.learning_rate)
 if not args.authorize_gpu_training:raise ValueError('Autorisation explicite requise : --authorize-gpu-training')
 root=Path(args.output).resolve()
 if not root.is_relative_to('/workspace/doemo-studio') or not os.path.ismount('/workspace'):raise ValueError('Volume persistant /workspace monté requis')
 config=Path(args.config).resolve();weights=Path(args.weights).resolve()
 if not config.is_file() or not weights.is_file():raise ValueError('Configuration et poids préentraînés locaux requis')
 # Framework imports happen only after consent and path checks.
 import torch
 import mmdet
 from mmengine.config import Config
 from mmengine.runner import Runner
 from mmengine.hooks import Hook
 from mmdet.utils import register_all_modules
 if mmdet.__version__!='3.3.0' or not torch.cuda.is_available():raise ValueError('MMDetection 3.3.0 et CUDA requis')
 free,total=torch.cuda.mem_get_info()
 if free<12*1024**3:raise ValueError('Au moins 12 Gio de VRAM libre requis ; aucune inférence ne doit être active')
 register_all_modules(init_default_scope=True)
 job=root/'training/jobs'/(getattr(args,'managed_job',None) or uuid.uuid4().hex);job.mkdir(parents=True,exist_ok=bool(getattr(args,'managed_job',None)))
 record={'schema':'doemo.training-job/1','id':job.name,'engine':'rtmdet','status':'running','started_at':time.time(),
         'runtime':{'torch':torch.__version__,'mmdet':mmdet.__version__,'gpu':torch.cuda.get_device_name()},
         'parameters':{'epochs':args.epochs,'batch_size':args.batch_size,'learning_rate':args.learning_rate},
         'dataset_sha256':getattr(args,'dataset_sha256',None) or sha256(args.dataset),'archive_sha256':sha256(args.dataset),
         'profile_id':getattr(args,'profile_id',None),'base_weights_sha256':sha256(weights),'events':[]}
 def event(kind,**data):
  item=dict(event=kind,at=time.time(),**data)
  with (job/(str(time.time_ns())+'-'+uuid.uuid4().hex+'.json')).open('x') as f:json.dump(item,f)
  print('DOEMO_EVENT='+json.dumps(item),flush=True)
 event('started',**record)
 try:
  archive_manifest=preserve({'dataset.zip':Path(args.dataset)},root/'datasets/rtmdet',{'sha256':record['dataset_sha256']})
  verify(archive_manifest);event('dataset_saved',manifest=str(archive_manifest.relative_to(root)))
  with tempfile.TemporaryDirectory(prefix='doemo-rtmdet-',dir='/tmp') as tmp:
   tmp=Path(tmp);dataset=unpack(args.dataset,tmp/'dataset');splits,classes=detection_splits(dataset)
   cfg=Config.fromfile(str(config))
   if 'RTMDet' not in cfg.model.bbox_head.type:raise ValueError('Configuration RTMDet attendue')
   cfg.model.bbox_head.num_classes=len(classes)
   cfg.work_dir=str(tmp/'work');cfg.load_from=str(weights);cfg.resume=False
   if getattr(args,'resume_manifest',None):
    resume=verify(args.resume_manifest);meta=resume['metadata']
    if any(meta.get(k)!=record.get(k) for k in ('id','engine','dataset_sha256','profile_id','parameters')):raise ValueError('Checkpoint d’une autre demande')
    filename=meta.get('resume_file','')
    if filename not in {f['name'] for f in resume['files']} or not filename.endswith('.pth'):raise ValueError('Checkpoint reprenable absent')
    restored=tmp/'resume.pth';shutil.copyfile(Path(args.resume_manifest).parent/filename,restored)
    cfg.load_from=str(restored);cfg.resume=True
   pipeline=cfg.get('train_pipeline_stage2',cfg.get('train_pipeline'))
   if not pipeline or not cfg.get('test_pipeline'):raise ValueError('Pipelines de données explicites requis dans le profil audité')
   for split,field in [('train','train_dataloader'),('validation','val_dataloader'),('test','test_dataloader')]:
    cfg[field]={'batch_size':args.batch_size if split=='train' else 1,'num_workers':0,'persistent_workers':False,
      'sampler':{'type':'DefaultSampler','shuffle':split=='train'},
      'dataset':{'type':'CocoDataset','data_root':str(dataset),'ann_file':splits[split],
                 'data_prefix':{'img':''},'metainfo':{'classes':tuple(classes)},'test_mode':split!='train',
                 'pipeline':pipeline if split=='train' else cfg.test_pipeline}}
   cfg.train_cfg={'type':'EpochBasedTrainLoop','max_epochs':args.epochs,'val_interval':1}
   cfg.val_cfg={'type':'ValLoop'};cfg.test_cfg={'type':'TestLoop'}
   cfg.val_evaluator={'type':'CocoMetric','ann_file':splits['validation'],'metric':'bbox'}
   cfg.test_evaluator={'type':'CocoMetric','ann_file':splits['test'],'metric':'bbox'}
   cfg.optim_wrapper.optimizer.lr=args.learning_rate
   cfg.param_scheduler=[];cfg.auto_scale_lr={'enable':False}
   # Do not inherit a pipeline switch tuned for the old COCO schedule/classes.
   cfg.custom_hooks=[]
   cfg.default_hooks.checkpoint={'type':'CheckpointHook','interval':1,'save_last':True,'max_keep_ckpts':2}
   cfg.visualizer={'type':'DetLocalVisualizer','vis_backends':[{'type':'LocalVisBackend'}],'name':'visualizer'}
   cfg.launcher='none';cfg.randomness={'seed':17}
   configuration=tmp/'model_config.py';cfg.dump(str(configuration))
   classes_file=tmp/'classes.json';classes_file.write_text(json.dumps(classes,ensure_ascii=False))
   runner=Runner.from_cfg(cfg)
   def control():
    path=getattr(args,'control',None)
    return Path(path).read_text().strip() if path else 'run'
   class Persist(Hook):
    priority='LOWEST'
    def after_train_iter(self,runner,batch_idx,data_batch=None,outputs=None):
     if control()=='cancel':raise Cancelled()
     if runner.iter%10==0 or runner.iter+1==runner.max_iters:
      try:loss=float(runner.message_hub.get_scalar('train/loss').current())
      except (KeyError,ValueError):loss=None
      if loss is not None and not math.isfinite(loss):raise ValueError('Perte non finie')
      event('progress',iteration=runner.iter+1,total_iterations=runner.max_iters,epoch=runner.epoch+1,loss=loss)
    def after_train_epoch(self,runner):
     files={p.name:p for p in Path(runner.work_dir).glob('*.pth')}
     if not files:raise ValueError('Checkpoint non écrit par le framework')
     files.update({'model_config.py':configuration,'classes.json':classes_file})
     manifest=preserve(files,job/'checkpoints',dict(record,epoch=runner.epoch+1,resume_file=f'epoch_{runner.epoch+1}.pth'))
     verify(manifest);event('checkpoint',epoch=runner.epoch+1,manifest=str(manifest.relative_to(root)))
     if control()=='cancel':raise Cancelled()
     if control()=='pause':raise Paused()
   runner.register_hook(Persist())
   if control()=='cancel':raise Cancelled()
   runner.train()
   if control()=='cancel':raise Cancelled()
   # Evaluate once on the untouched test split, using final model weights in memory.
   metrics=runner.test();metrics={k:float(v) for k,v in metrics.items()}
   if not metrics or not all(math.isfinite(v) for v in metrics.values()):raise ValueError('Métriques invalides')
   if control()=='cancel':raise Cancelled()
   metric_file=tmp/'metrics.json';metric_file.write_text(json.dumps(metrics))
   checkpoint=Path(runner.work_dir)/f'epoch_{args.epochs}.pth'
   if not checkpoint.is_file() and getattr(args,'resume_manifest',None) and meta.get('epoch')==args.epochs:checkpoint=restored
   if not checkpoint.is_file():raise ValueError('Checkpoint final attendu absent')
   manifest=preserve({'weights.pth':checkpoint,'model_config.py':configuration,'classes.json':classes_file,'metrics.json':metric_file},job/'results',
      dict(record,status='completed',completed_at=time.time(),metrics=metrics,production_approved=False))
   verify(manifest);event('completed',manifest=str(manifest.relative_to(root)),metrics=metrics)
   return manifest
 except Paused:
  event('paused');return None
 except Cancelled:
  event('cancelled');return None
 except BaseException as exc:
  event('interrupted' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'failed',error_type=type(exc).__name__)
  raise


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--dataset',required=True);p.add_argument('--config',required=True);p.add_argument('--weights',required=True)
 p.add_argument('--output',default='/workspace/doemo-studio');p.add_argument('--epochs',type=int,default=1)
 p.add_argument('--batch-size',type=int,default=1);p.add_argument('--learning-rate',type=float,default=.0001)
 p.add_argument('--authorize-gpu-training',action='store_true')
 p.add_argument('--managed-job');p.add_argument('--control');p.add_argument('--dataset-sha256');p.add_argument('--profile-id');p.add_argument('--resume-manifest')
 args=p.parse_args();print(run(args))
