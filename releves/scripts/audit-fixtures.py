"""Audit supplied files without committing client documents or calling external APIs."""
import argparse
import hashlib
import json
from pathlib import Path
from doemo_releves.ai_contracts import normalise
from doemo_releves.documents import prepare_document
import tempfile
p=argparse.ArgumentParser();p.add_argument('--pdf',required=True);p.add_argument('--qwen',required=True);p.add_argument('--paddleocr',required=True);p.add_argument('--rtmdet',required=True);p.add_argument('--width',type=int,required=True);p.add_argument('--height',type=int,required=True);p.add_argument('--output',required=True);args=p.parse_args()
with tempfile.TemporaryDirectory(prefix='doemo-fixture-') as tmp:
    metadata=prepare_document(args.pdf,tmp,Path(args.pdf).name,'survey')
report={'pdf':metadata,'declared_inference_dimensions':[args.width,args.height],'engines':{},'external_inference_executed':False,'human_validation_required':True}
for engine in ('qwen','paddleocr','rtmdet'):
    path=Path(getattr(args,engine));result=normalise(engine,json.loads(path.read_text()),'fixture',1,args.width,args.height)
    report['engines'][engine]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'localized_observations':len(result['annotations']),'unlocated_observations':len(result['observations']),'warnings':result['warnings']}
    if engine=='rtmdet':report['engines'][engine]['diagnostic']=result['observations']
Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report['engines'].items()},ensure_ascii=False,indent=2))
