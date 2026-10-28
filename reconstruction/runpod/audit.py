#!/usr/bin/env python3
"""Read-only RunPod diagnostics; no dependency installation or secret output."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

CHECKS={
 'gpu':['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader'],
 'qwen':['/opt/doemo-qwen-venv/bin/python','-c','import torch,transformers; print(torch.__version__,transformers.__version__,torch.cuda.is_available()); assert torch.cuda.is_available()'],
 'paddleocr':['/opt/doemo-ocr-venv/bin/python','-c','import paddle,paddleocr; print(paddle.__version__,paddleocr.__version__)'],
 'rtmdet':['/opt/doemo-rtmdet-venv/bin/python','-c','import torch,torchvision,mmcv,mmengine,mmdet; print(torch.__version__,torchvision.__version__,mmcv.__version__,mmengine.__version__,mmdet.__version__,torch.cuda.is_available()); assert torch.cuda.is_available()']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--functional',action='store_true');p.add_argument('--config');p.add_argument('--runner',default=str(Path(__file__).with_name('engine_runner.py')));p.add_argument('--image');args=p.parse_args()
    from inventory import collect
    inventory=collect()
    results={}
    for name,command in CHECKS.items():
        try:
            run=subprocess.run(command,capture_output=True,text=True,timeout=60)
            results[name]={'imports_ok':run.returncode==0,'details':run.stdout[-2000:],'functional_model_verified':False}
        except Exception as error:results[name]={'imports_ok':False,'error':type(error).__name__,'functional_model_verified':False}
    if args.functional:
        if not args.config or not args.image:p.error('--functional requires --config and --image')
        from PIL import Image
        from doemo_reconstruction.ai_service.engines import Engines
        engines=Engines(args.config,args.runner)
        with Image.open(args.image) as image:width,height=image.size
        for name in ('paddleocr','qwen','rtmdet'):
            try:
                result=engines.run(name,{'image_path':str(Path(args.image).resolve()),'regions':[{'id':'test','bbox':[0,0,width,height]}]})
                results[name]['functional_model_verified']=True;results[name]['model_version']=result['model_version']
            except Exception as error:results[name]['functional_error']=type(error).__name__
    print(json.dumps({'inventory':inventory,'checks':results,'architecture_segmentation':'not_qualified'},indent=2))
    return 0 if all(v['imports_ok'] and (not args.functional or k=='gpu' or v['functional_model_verified']) for k,v in results.items()) else 1

if __name__=='__main__':sys.exit(main())
