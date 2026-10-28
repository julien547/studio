"""Read-only runtime audit; --smoke additionally runs three actual inference probes.
No installation, provider API action or training. Never reads credential values.
"""
import argparse
import datetime
import json
import os
import subprocess
import uuid
from pathlib import Path

ENGINES={'qwen':('/opt/doemo-qwen-venv/bin/python',['torch','transformers','accelerate','peft','bitsandbytes']),
 'paddleocr':('/opt/doemo-ocr-venv/bin/python',['paddlepaddle-gpu','paddleocr','paddlex']),
 'rtmdet':('/opt/doemo-rtmdet-venv/bin/python',['torch','mmcv','mmengine','mmdet'])}
PROBE="""
import json,sys,importlib.metadata as m
result={'python':sys.version,'packages':{}}
for p in json.loads(sys.argv[1]):
 try:result['packages'][p]=m.version(p)
 except m.PackageNotFoundError:result['packages'][p]=None
try:
 if sys.argv[2]=='paddleocr':
  import paddle
  result['gpu']=paddle.is_compiled_with_cuda();result['device']=paddle.device.get_device()
 else:
  import torch
  result['gpu']=torch.cuda.is_available()
  if result['gpu']:
   result['device']=torch.cuda.get_device_name(0);result['vram_bytes']=torch.cuda.get_device_properties(0).total_memory
except Exception as e:result['error']=type(e).__name__
print('DOEMO_AUDIT='+json.dumps(result))
"""


def audit(smoke,output):
 output=Path(output)
 if output.exists():raise ValueError('Choisir un nouveau rapport, aucun écrasement')
 output.parent.mkdir(parents=True,exist_ok=True)
 report={'schema':'doemo.runtime-audit/1','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'workspace_mounted':os.path.ismount('/workspace'),'engines':{},'training_executed':False}
 paths={'qwen':os.environ.get('DOEMO_QWEN_MODEL','/workspace/doemo-studio/models/qwen/Qwen3.5-9B'),
  'paddle_detection':os.environ.get('DOEMO_PADDLE_DETECTION_MODEL',''),
  'paddle_recognition':os.environ.get('DOEMO_PADDLE_RECOGNITION_MODEL',''),
  'rtmdet_config':os.environ.get('DOEMO_RTMDET_CONFIG',''),
  'rtmdet_weights':os.environ.get('DOEMO_RTMDET_WEIGHTS',''),
  'paddle_training_repository':os.environ.get('DOEMO_PADDLE_TRAIN_REPO','')}
 report['models']={k:{'path':v,'exists':bool(v and Path(v).exists())} for k,v in paths.items()}
 for engine,(python,packages) in ENGINES.items():
  item={'interpreter_present':Path(python).is_file(),'inference_verified':False}
  report['engines'][engine]=item
  if not item['interpreter_present']:continue
  env={k:v for k,v in os.environ.items() if k!='RUNPOD_API_KEY'}
  env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
  try:
   r=subprocess.run([python,'-c',PROBE,json.dumps(packages),engine],capture_output=True,text=True,timeout=90,env=env)
   line=next(s for s in r.stdout.splitlines() if s.startswith('DOEMO_AUDIT='))
   item.update(json.loads(line.split('=',1)[1]))
   if smoke:
    log=output.parent/(engine+'-smoke-'+uuid.uuid4().hex+'.log')
    with log.open('xb') as stream:
     run=subprocess.run([python,str(Path(__file__).with_name('readiness.py')),engine],stdout=stream,stderr=stream,timeout=480,env=env)
    item.update(inference_verified=run.returncode==0,smoke_log=log.name)
  except Exception as e:item['audit_error']=type(e).__name__
 with output.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
 return report

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--smoke',action='store_true');p.add_argument('--output',required=True);a=p.parse_args()
 value=audit(a.smoke,a.output)
 print(json.dumps(value,ensure_ascii=False,indent=2))
