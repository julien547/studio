"""Explicit PaddleOCR recognition fine-tuning. GPU acceptance is operator-only.

Uses the audited ppocr factories, a single-process Adam loop, full epoch snapshots
and exact test transcriptions. Never installs packages, exports/promotes a detector,
or replaces the serving recognition model. All completed artifacts are candidates.
"""
import argparse
import contextlib
import copy
import json
import math
import os
import random
import re
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from artifacts import sha256,preserve,verify
from compute import exclusive,require_idle_gpu
from paddle_training import configuration,ExactMetric,source_hash,CheckedLoader
from training_data import unpack

class Paused(Exception):pass
class Cancelled(Exception):pass


def control(args):
    value=Path(args.control).read_text().strip() if args.control else 'run'
    if value=='cancel':raise Cancelled()
    return value


def evaluation_control(args):
    # The final epoch checkpoint is already durable. Release the GPU between
    # evaluation batches if an inference arrives; resume redoes evaluation.
    if control(args)=='pause':raise Paused()


class PaddleSession:
    def __init__(self,cfg,weights,repository,rate,batch_size):
        # These imports only occur after the explicit authorization and lock checks.
        sys.path.insert(0,str(repository))
        import paddle
        import numpy as np
        import ppocr
        if not Path(ppocr.__file__).resolve().is_relative_to(repository):raise ValueError('Mauvais dépôt ppocr importé')
        if not paddle.__version__.startswith('3.') or not paddle.is_compiled_with_cuda():raise ValueError('PaddlePaddle 3 GPU requis')
        self.device=paddle.set_device('gpu:0');paddle.seed(17);np.random.seed(17);random.seed(17)
        from ppocr.modeling.architectures import build_model
        from ppocr.losses import build_loss
        from ppocr.postprocess import build_post_process
        from ppocr.data import build_dataloader
        from ppocr.utils.logging import get_logger
        self.paddle=paddle;self.np=np;self.build_loader=build_dataloader;self.logger=get_logger();self.cfg=cfg
        self.decoder=build_post_process(cfg['PostProcess'],cfg['Global'])
        size=len(self.decoder.character);head=cfg['Architecture']['Head']
        if head['name']=='MultiHead':
            losses=cfg['Loss'].get('loss_config_list',[])
            names=[next(iter(v)) for v in losses if isinstance(v,dict) and len(v)==1]
            if names not in (['CTCLoss','SARLoss'],['CTCLoss','NRTRLoss']):raise ValueError('MultiHead CTC/SAR ou CTC/NRTR attendu')
            head['out_channels_list']={'CTCLabelDecode':size,('SARLabelDecode' if names[1]=='SARLoss' else 'NRTRLabelDecode'):size+(2 if names[1]=='SARLoss' else 3)}
            if names[1]=='SARLoss':losses[1]['SARLoss']=dict(losses[1]['SARLoss'] or {},ignore_index=size+1)
        else:head['out_channels']=size
        self.model=build_model(cfg['Architecture']);self.loss=build_loss(cfg['Loss'])
        self.optimizer=paddle.optimizer.Adam(learning_rate=rate,parameters=self.model.parameters())
        state=paddle.load(str(weights));current=self.model.state_dict()
        if set(state)!=set(current) or any(list(state[k].shape)!=list(current[k].shape) for k in current):raise ValueError('Poids et dictionnaire incompatibles : chargement partiel refusé')
        self.model.set_state_dict(state)
        self.multi=head['name']=='MultiHead';self.batch_size=batch_size
        self.runtime={'paddle':paddle.__version__,'source_sha256':source_hash(repository),'device':paddle.device.get_device()}
    def loader(self,mode,seed=17):
        self.paddle.seed(seed);self.np.random.seed(seed);random.seed(seed)
        loader=self.build_loader(self.cfg,mode,self.device,self.logger,seed)
        labels=Path(self.cfg[mode]['dataset']['label_file_list'][0]).read_text().splitlines()
        return CheckedLoader(loader,[line.split('\t',1)[1] for line in labels],lambda batch:[x[0] for x in self.decoder.decode(batch[1].numpy(),is_remove_duplicate=False)])
    def step(self,batch):
        self.model.train()
        predictions=self.model(batch[0],data=batch[1:]) if self.multi else self.model(batch[0])
        loss=self.loss(predictions,batch)['loss'];value=float(loss.item())
        if not math.isfinite(value):raise ValueError('Perte non finie')
        loss.backward();self.optimizer.step();self.optimizer.clear_grad()
        return value
    def save(self,directory):
        self.paddle.save(self.model.state_dict(),str(directory/'weights.pdparams'))
        self.paddle.save(self.optimizer.state_dict(),str(directory/'optimizer.pdopt'))
    def restore(self,directory):
        self.model.set_state_dict(self.paddle.load(str(directory/'weights.pdparams')))
        self.optimizer.set_state_dict(self.paddle.load(str(directory/'optimizer.pdopt')))
    def evaluate(self,label_file,expected,check):
        cfg=copy.deepcopy(self.cfg);cfg['Eval']['dataset']['label_file_list']=[str(label_file)]
        loader=self.build_loader(cfg,'Eval',self.device,self.logger,17);metric=ExactMetric(expected)
        self.model.eval()
        with self.paddle.no_grad():
            for batch in loader:
                check();metric.add(self.decoder(self.model(batch[0]),batch[1].numpy()))
        return metric.finish(),metric.pairs


def train_epochs(session,args,record,job,root,tmp,emit,restored=None):
    """Framework-independent control loop, tested with a CPU session fixture."""
    start=1;steps=0
    if restored:
        manifest=verify(restored);meta=manifest['metadata']
        if any(meta.get(k)!=record.get(k) for k in ('id','engine','dataset_sha256','profile_id','parameters')):raise ValueError('Checkpoint d’une autre tâche')
        files={v['name'] for v in manifest['files']}
        if not {'weights.pdparams','optimizer.pdopt','checkpoint.json'}<=files:raise ValueError('Checkpoint incomplet')
        state=json.loads((Path(restored).parent/'checkpoint.json').read_text())
        if type(state['epoch']) is not int or not 1<=state['epoch']<=args.epochs or state['epoch']!=meta.get('epoch'):raise ValueError('Époque de reprise invalide')
        if type(state.get('steps_per_epoch')) is not int or state['steps_per_epoch']<=0 or type(state.get('steps')) is not int or state['steps']!=state['epoch']*state['steps_per_epoch']:raise ValueError('Itérations de reprise invalides')
        local=tmp/'resume';local.mkdir(exist_ok=True)
        for name in ('weights.pdparams','optimizer.pdopt'):
            shutil.copyfile(Path(restored).parent/name,local/name)
            expected=next(v['sha256'] for v in manifest['files'] if v['name']==name)
            if sha256(local/name)!=expected:raise ValueError('Checkpoint modifié pendant la copie')
        session.restore(local);start=state['epoch']+1;steps=state['steps']
    last=None
    for epoch in range(start,args.epochs+1):
        control(args);loader=session.loader('Train',17+epoch);count=len(loader)
        if count<=0:raise ValueError('Lot entraînement vide')
        if steps!=(epoch-1)*count:raise ValueError('Nombre d’itérations modifié à la reprise')
        seen=0
        for batch in loader:
            control(args);loss=session.step(batch);seen+=1;steps+=1
            if seen==1 or seen==count or seen%10==0:emit('progress',iteration=steps,total_iterations=count*args.epochs,epoch=epoch,loss=loss)
        if seen!=count:raise ValueError('Lecteur entraînement incomplet')
        session.save(tmp)
        (tmp/'checkpoint.json').write_text(json.dumps({'epoch':epoch,'steps':steps,'steps_per_epoch':count}))
        files={name:tmp/name for name in ('weights.pdparams','optimizer.pdopt','checkpoint.json','training_config.yaml','dictionary.txt')}
        last=preserve(files,job/'checkpoints',dict(record,epoch=epoch));verify(last)
        emit('checkpoint',epoch=epoch,manifest=str(last.relative_to(root)))
        if control(args)=='pause':raise Paused()
    return last or Path(restored)


def run(args):
    if not args.authorize_gpu_training:raise ValueError('Autorisation GPU explicite requise')
    if not 1<=args.epochs<=100 or not 1<=args.batch_size<=4 or not 0<args.learning_rate<=.001:raise ValueError('Paramètres hors limites')
    root=Path(args.output).resolve()
    if not root.is_relative_to('/workspace/doemo-studio') or not os.path.ismount('/workspace'):raise ValueError('Volume persistant monté requis')
    with contextlib.ExitStack() as stack:
        if args.managed_job:
            if os.environ.get('DOEMO_TRAINING_CHILD')!='1' or not re.fullmatch('[a-f0-9]{32}',args.managed_job) or not args.control or not str(Path(args.control).resolve()).startswith('/tmp/doemo-training-control-'):raise ValueError('Admission gateway requise')
        else:
            import fcntl
            guard=stack.enter_context(open('/tmp/doemo-gateway.lock','a'));fcntl.flock(guard.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        stack.enter_context(exclusive())
        require_idle_gpu()
        return execute(args,root)


def execute(args,root):
    import yaml
    repository=Path(args.repository).resolve();weights=Path(args.weights).resolve();config=Path(args.config).resolve();dictionary=Path(args.dictionary).resolve()
    if any(not p.is_relative_to('/workspace/doemo-studio') for p in (repository,weights,config,dictionary)) or weights.suffix!='.pdparams':raise ValueError('Sources, configuration, dictionnaire et poids d’entraînement persistants requis')
    repo_hash=source_hash(repository)
    job=root/'training/jobs'/(args.managed_job or uuid.uuid4().hex);job.mkdir(parents=True,exist_ok=bool(args.managed_job))
    record={'id':job.name,'engine':'paddleocr','driver':'paddleocr.recognition/1','dataset_sha256':args.dataset_sha256 or sha256(args.dataset),
            'profile_id':args.profile_id,'parameters':{'epochs':args.epochs,'batch_size':args.batch_size,'learning_rate':args.learning_rate},
            'base_weights_sha256':sha256(weights),'source_sha256':repo_hash,'dictionary_sha256':sha256(dictionary),'started_at':time.time()}
    def emit(event,**fields):
        item=dict(event=event,at=time.time(),**fields)
        (job/(uuid.uuid4().hex+'.json')).write_text(json.dumps(item,ensure_ascii=False))
        print('DOEMO_EVENT='+json.dumps(item,ensure_ascii=False),flush=True)
    try:
        with tempfile.TemporaryDirectory(prefix='doemo-paddle-',dir='/tmp') as local:
            tmp=Path(local);data=unpack(args.dataset,tmp/'dataset');shutil.copyfile(dictionary,tmp/'dictionary.txt')
            snapshot=json.loads((data/'examples.json').read_text())
            from training_service import digest
            if snapshot.get('engine')!='paddleocr' or (args.dataset_sha256 and digest(snapshot)!=args.dataset_sha256):raise ValueError('Snapshot OCR incompatible')
            record['dataset_sha256']=digest(snapshot)
            cfg,splits,rows=configuration(yaml.safe_load(config.read_text()),data,tmp/'work',tmp/'dictionary.txt',args.epochs,args.batch_size,args.learning_rate)
            session=PaddleSession(cfg,weights,repository,args.learning_rate,args.batch_size)
            record['runtime']=session.runtime
            (tmp/'training_config.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True))
            checkpoint=train_epochs(session,args,record,job,root,tmp,emit,args.resume_manifest)
            evaluation_control(args)
            # Validation and test are distinct. No test images enter the optimizer.
            validation,_=session.evaluate(splits['validation'],[r['text'] for r in rows if r['split']=='validation'],lambda:evaluation_control(args))
            metrics,pairs=session.evaluate(splits['test'],[r['text'] for r in rows if r['split']=='test'],lambda:evaluation_control(args))
            metrics.update({'validation_'+k:v for k,v in validation.items()})
            if not all(type(v) in (int,float) and math.isfinite(v) for v in metrics.values()):raise ValueError('Métriques invalides')
            evaluation_control(args);(tmp/'metrics.json').write_text(json.dumps(metrics))
            (tmp/'predictions.json').write_text(json.dumps([{'expected':a,'predicted':b} for a,b in pairs],ensure_ascii=False))
            source=checkpoint.parent
            files={'weights.pdparams':source/'weights.pdparams','training_config.yaml':tmp/'training_config.yaml','dictionary.txt':tmp/'dictionary.txt','metrics.json':tmp/'metrics.json','predictions.json':tmp/'predictions.json'}
            manifest=preserve(files,job/'results',dict(record,status='completed',metrics=metrics,normalization='none',production_approved=False))
            verify(manifest);emit('completed',manifest=str(manifest.relative_to(root)))
            return manifest
    except Paused:emit('paused')
    except Cancelled:emit('cancelled')
    except BaseException:emit('failed');raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('dataset','config','weights','repository','dictionary'):p.add_argument('--'+key,required=True)
    p.add_argument('--output',default='/workspace/doemo-studio');p.add_argument('--epochs',type=int,default=1);p.add_argument('--batch-size',type=int,default=1);p.add_argument('--learning-rate',type=float,default=.0001)
    p.add_argument('--authorize-gpu-training',action='store_true');p.add_argument('--managed-job');p.add_argument('--control');p.add_argument('--dataset-sha256');p.add_argument('--profile-id');p.add_argument('--resume-manifest')
    print(run(p.parse_args()))
