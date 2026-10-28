"""Real, serial model smoke tests, once per gateway boot. No input from clients."""
import json
import os
import sys
import tempfile
from pathlib import Path
from PIL import Image

engine=sys.argv[1]
with tempfile.TemporaryDirectory(prefix='doemo-ready-',dir='/tmp') as tmp:
    source=Path(tmp)/'probe.png';Image.new('RGB',(256,256),'white').save(source)
    if engine=='qwen':
        import torch
        from transformers import AutoProcessor,AutoModelForImageTextToText
        if not torch.cuda.is_available():raise RuntimeError('CUDA absent')
        path=os.environ.get('DOEMO_QWEN_MODEL','/workspace/doemo-studio/models/qwen/Qwen3.5-9B')
        processor=AutoProcessor.from_pretrained(path,local_files_only=True)
        model=AutoModelForImageTextToText.from_pretrained(path,local_files_only=True,torch_dtype='auto',device_map='auto')
        messages=[{'role':'user','content':[{'type':'image','image':Image.open(source)},{'type':'text','text':'Reply OK.'}]}]
        inputs=processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors='pt').to(model.device)
        with torch.inference_mode():model.generate(**inputs,max_new_tokens=8,do_sample=False)
        torch.cuda.synchronize()
    elif engine in ('paddleocr','rtmdet'):
        if engine=='rtmdet':
            import torch
            if not torch.cuda.is_available():raise RuntimeError('CUDA absent')
            import mmcv.ops
        # Exercise the exact production adapter in its own environment.
        import runpy
        sys.argv=['infer.py',engine,str(source),str(Path(tmp)/'result.json')]
        runpy.run_path(str(Path(__file__).with_name('infer.py')),run_name='__main__')
        json.loads((Path(tmp)/'result.json').read_text())
    else:raise ValueError('Unknown engine')
print(json.dumps({'engine':engine,'model_inference_verified':True}))
