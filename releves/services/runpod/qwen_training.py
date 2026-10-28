"""Offline, operator-accepted multimodal Qwen3.5 LoRA. Never promotes a model."""
import argparse
import contextlib
import importlib.metadata
import json
import math
import os
import random
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from artifacts import preserve,verify,sha256
from compute import exclusive,require_idle_gpu
from training_data import unpack
from qwen_training_data import configuration,dataset,model_hash,messages,assistant_labels,digest,PROMPT_VERSION

class Paused(Exception):pass
class Cancelled(Exception):pass


def command(args):
    value=Path(args.control).read_text().strip() if args.control else 'run'
    if value=='cancel':raise Cancelled()
    if value not in ('run','pause'):raise ValueError('Commande invalide')
    return value


class Session:
    def __init__(self,base,cfg,rate,root):
        # No framework imports until authorization, offline mode and compute lock.
        for package,version in cfg['runtime_versions'].items():
            if importlib.metadata.version(package)!=version:raise ValueError('Version runtime différente du profil : '+package)
        import torch
        from transformers import AutoModelForImageTextToText,AutoProcessor
        from peft import LoraConfig,get_peft_model
        if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():raise ValueError('GPU BF16 requis')
        torch.manual_seed(17);torch.cuda.manual_seed_all(17)
        self.torch=torch;self.cfg=cfg;self.root=root
        self.processor=AutoProcessor.from_pretrained(base,local_files_only=True,trust_remote_code=False,min_pixels=4096,max_pixels=cfg['max_pixels'])
        model=AutoModelForImageTextToText.from_pretrained(base,local_files_only=True,trust_remote_code=False,torch_dtype=torch.bfloat16,device_map={'':'cuda:0'},attn_implementation='eager')
        if model.config.model_type!='qwen3_5':raise ValueError('Qwen3.5 dense attendu')
        count=sum(p.numel() for p in model.parameters())
        if not 8_000_000_000<=count<=11_000_000_000:raise ValueError('Profil réservé au modèle dense 9B')
        targets=[name for name,module in model.named_modules() if 'language_model' in name and not any(v in name for v in ('visual','vision')) and name.rsplit('.',1)[-1] in ('q_proj','k_proj','v_proj','o_proj') and isinstance(module,torch.nn.Linear)]
        if not targets:raise ValueError('Projections langage compatibles introuvables')
        self.model=get_peft_model(model,LoraConfig(r=cfg['rank'],lora_alpha=cfg['alpha'],target_modules=targets,lora_dropout=0,bias='none',task_type='CAUSAL_LM'))
        self.model.config.use_cache=False
        self.model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        self.model.enable_input_require_grads()
        trainable=[p for name,p in self.model.named_parameters() if p.requires_grad]
        if not trainable or any('lora_' not in name for name,p in self.model.named_parameters() if p.requires_grad):raise ValueError('Seuls les adaptateurs LoRA peuvent être entraînés')
        self.optimizer=torch.optim.AdamW(trainable,lr=rate,weight_decay=0)
        self.runtime={'versions':cfg['runtime_versions'],'base_parameters':count,'trainable_parameters':sum(p.numel() for p in trainable),'targets':targets,'dtype':'bfloat16'}
    def inputs(self,row):
        from PIL import Image
        with Image.open(self.root/row['image']) as original:
            image=original.convert('RGB');scale=min(1,(self.cfg['max_pixels']/(image.width*image.height))**.5)
            if scale<1:image=image.resize((max(1,int(image.width*scale)),max(1,int(image.height*scale))))
            prompt=messages(row,image)
            prefix=self.processor.apply_chat_template(prompt,tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=True,return_tensors='pt')
            full=self.processor.apply_chat_template(prompt+[{'role':'assistant','content':[{'type':'text','text':row['messages'][1]['content']}]}],tokenize=True,add_generation_prompt=False,enable_thinking=False,return_dict=True,return_tensors='pt')
        labels=assistant_labels(full['input_ids'][0].tolist(),prefix['input_ids'][0].tolist(),self.cfg['max_tokens'])
        full['labels']=self.torch.tensor([labels],dtype=self.torch.long)
        return {k:v.to('cuda:0') if hasattr(v,'to') else v for k,v in full.items()},sum(x!=-100 for x in labels)
    def step(self,row,seed):
        self.torch.manual_seed(seed);self.torch.cuda.manual_seed_all(seed);random.seed(seed)
        self.model.train();inputs,_=self.inputs(row);self.optimizer.zero_grad(set_to_none=True)
        loss=self.model(**inputs,use_cache=False).loss
        if not self.torch.isfinite(loss).item():raise ValueError('Perte non finie')
        loss.backward();self.torch.nn.utils.clip_grad_norm_([p for p in self.model.parameters() if p.requires_grad],1.,error_if_nonfinite=True)
        self.optimizer.step();return float(loss.detach().item())
    def save(self,folder):
        self.model.save_pretrained(folder,safe_serialization=True,save_embedding_layers=False)
        self.torch.save(self.optimizer.state_dict(),folder/'optimizer.pt')
    def restore(self,folder):
        from safetensors.torch import load_file
        from peft import set_peft_model_state_dict,get_peft_model_state_dict
        weights=load_file(str(folder/'adapter_model.safetensors'),device='cpu')
        expected=get_peft_model_state_dict(self.model)
        if set(weights)!=set(expected) or any(weights[k].shape!=expected[k].shape for k in expected):raise ValueError('Adaptateur incompatible')
        set_peft_model_state_dict(self.model,weights)
        self.optimizer.load_state_dict(self.torch.load(folder/'optimizer.pt',map_location='cpu',weights_only=True))
    def evaluate(self,rows,check):
        self.model.eval();losses=0.;tokens=0
        with self.torch.no_grad():
            for row in rows:
                check();inputs,n=self.inputs(row);loss=float(self.model(**inputs,use_cache=False).loss.item())
                if not math.isfinite(loss):raise ValueError('Évaluation non finie')
                losses+=loss*n;tokens+=n
        if not tokens:raise ValueError('Évaluation vide')
        return {'assistant_loss':losses/tokens,'assistant_tokens':tokens,'samples':len(rows)}


def train(session,args,record,rows,job,root,tmp,emit):
    count=len(rows);cursor=0;last=None
    if args.resume_manifest:
        last=Path(args.resume_manifest);manifest=verify(last)
        if any(manifest['metadata'].get(k)!=record.get(k) for k in ('id','engine','dataset_sha256','profile_id','parameters')):raise ValueError('Checkpoint d’une autre tâche')
        local=tmp/'resume';local.mkdir()
        for f in manifest['files']:
            shutil.copyfile(last.parent/f['name'],local/f['name'])
            if sha256(local/f['name'])!=f['sha256']:raise ValueError('Copie de reprise corrompue')
        saved=json.loads((local/'checkpoint.json').read_text());cursor=saved['cursor']
        if type(cursor) is not int or not 0<=cursor<=count*args.epochs or saved['rows']!=count:raise ValueError('Curseur de reprise invalide')
        session.restore(local)
    def checkpoint():
        session.save(tmp)
        (tmp/'checkpoint.json').write_text(json.dumps({'cursor':cursor,'rows':count}))
        files={name:tmp/name for name in ('adapter_model.safetensors','adapter_config.json','optimizer.pt','checkpoint.json','training_config.json')}
        result=preserve(files,job/'checkpoints',dict(record,epoch=max(1,math.ceil(cursor/count)),cursor=cursor));verify(result)
        emit('checkpoint',manifest=str(result.relative_to(root)),epoch=max(1,math.ceil(cursor/count)))
        return result
    # Pause even during model initialization retains cursor=0; no batch is invented.
    if command(args)=='pause':checkpoint();raise Paused()
    while cursor<count*args.epochs:
        epoch=cursor//count;order=list(range(count));random.Random(17+epoch).shuffle(order)
        loss=session.step(rows[order[cursor%count]],17+cursor);cursor+=1
        emit('progress',iteration=cursor,total_iterations=count*args.epochs,epoch=math.ceil(cursor/count),loss=loss)
        action=command(args)
        if cursor%count==0 or action=='pause':last=checkpoint()
        if action=='pause':raise Paused()
    return last


def execute(args,root):
    base=Path(args.weights).resolve();config=Path(args.config).resolve()
    if any(not p.is_relative_to('/workspace/doemo-studio') for p in (base,config)):raise ValueError('Poids et configuration persistants requis')
    cfg=configuration(config);base_hash=model_hash(base)
    base_config=json.loads((base/'config.json').read_text())
    if base_config.get('model_type')!='qwen3_5' or base_config.get('quantization_config'):raise ValueError('Qwen3.5 dense non quantifié requis pour ce pilote BF16')
    job=root/'training/jobs'/args.managed_job;job.mkdir(parents=True,exist_ok=True)
    record={'id':job.name,'engine':'qwen','driver':'qwen.lora/1','profile_id':args.profile_id,'dataset_sha256':args.dataset_sha256,
            'parameters':{'epochs':args.epochs,'batch_size':args.batch_size,'learning_rate':args.learning_rate},'base_weights_sha256':base_hash,'prompt_version':PROMPT_VERSION,'production_approved':False}
    def emit(event,**fields):
        value=dict(event=event,at=time.time(),**fields);(job/(uuid.uuid4().hex+'.json')).write_text(json.dumps(value))
        print('DOEMO_EVENT='+json.dumps(value),flush=True)
    try:
        with tempfile.TemporaryDirectory(prefix='doemo-qwen-lora-',dir='/tmp') as directory:
            tmp=Path(directory);data=unpack(args.dataset,tmp/'dataset');splits,snapshot=dataset(data)
            if digest(snapshot)!=args.dataset_sha256:raise ValueError('Snapshot Qwen incompatible')
            (tmp/'training_config.json').write_text(json.dumps(cfg))
            command(args);session=Session(str(base),cfg,args.learning_rate,data);record['runtime']=session.runtime
            checkpoint=train(session,args,record,splits['train'],job,root,tmp,emit)
            def check():
                if command(args)=='pause':raise Paused()
            metrics={}
            for split in ('validation','test'):
                for key,value in session.evaluate(splits[split],check).items():metrics[split+'_'+key]=value
            check();(tmp/'metrics.json').write_text(json.dumps(metrics))
            files={name:checkpoint.parent/name for name in ('adapter_model.safetensors','adapter_config.json')}
            files.update({'training_config.json':tmp/'training_config.json','metrics.json':tmp/'metrics.json'})
            manifest=preserve(files,job/'results',dict(record,status='completed',metrics=metrics,evaluation_scope='teacher_forced_assistant_loss_only'))
            verify(manifest);emit('completed',manifest=str(manifest.relative_to(root)))
    except Paused:emit('paused')
    except Cancelled:emit('cancelled')
    except BaseException:emit('failed');raise


def run(args):
    if not args.authorize_gpu_training:raise ValueError('Autorisation GPU explicite requise')
    if not 1<=args.epochs<=100 or args.batch_size!=1 or not 0<args.learning_rate<=.0002:raise ValueError('Limites LoRA : batch=1 et taux ≤0,0002')
    root=Path(args.output).resolve()
    if not root.is_relative_to('/workspace/doemo-studio') or not os.path.ismount('/workspace'):raise ValueError('Volume persistant requis')
    if os.environ.get('DOEMO_TRAINING_CHILD')!='1' or not re.fullmatch('[a-f0-9]{32}',args.managed_job or '') or not args.control or not str(Path(args.control).resolve()).startswith('/tmp/doemo-training-control-'):raise ValueError('Admission par le gateway ou sa recette obligatoire')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1')
    with exclusive():require_idle_gpu();execute(args,root)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('dataset','config','weights','managed-job','control','dataset-sha256','profile-id'):p.add_argument('--'+field,required=True)
    p.add_argument('--output',default='/workspace/doemo-studio');p.add_argument('--epochs',type=int,default=1);p.add_argument('--batch-size',type=int,default=1);p.add_argument('--learning-rate',type=float,default=.0001);p.add_argument('--resume-manifest');p.add_argument('--authorize-gpu-training',action='store_true')
    run(p.parse_args())
