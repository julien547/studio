"""Run on the Pod, before any installation. Does not load or modify models."""
import json
import subprocess
from pathlib import Path
engines={'qwen':('/opt/doemo-qwen-venv/bin/python','transformers'),
         'paddleocr':('/opt/doemo-ocr-venv/bin/python','paddleocr'),
         'rtmdet':('/opt/doemo-rtmdet-venv/bin/python','mmdet')}
results={}
for name,(python,module) in engines.items():
    if not Path(python).is_file():results[name]={'environment_exists':False};continue
    probe='import importlib.util,json;print(json.dumps({"module_available":importlib.util.find_spec('+repr(module)+') is not None}))'
    try:
        p=subprocess.run([python,'-c',probe],capture_output=True,timeout=60)
        results[name]={'environment_exists':True,'probe':json.loads(p.stdout) if p.returncode==0 else {'error':'Import non disponible'}}
    except Exception:results[name]={'environment_exists':True,'probe':{'error':'Sonde interrompue'}}
results['qwen_model_present']=Path('/workspace/doemo-studio/models/qwen/Qwen3.5-9B/config.json').is_file()
results['inference_tested']=False
print(json.dumps(results,indent=2))
