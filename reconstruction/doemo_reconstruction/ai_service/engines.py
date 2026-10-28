"""Isolated processes preserve all three existing model environments."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import signal
import uuid
from .outputs import validate_output

PYTHONS={'qwen':'/opt/doemo-qwen-venv/bin/python','paddleocr':'/opt/doemo-ocr-venv/bin/python',
         'rtmdet':'/opt/doemo-rtmdet-venv/bin/python'}


class Engines:
    def __init__(self,config_path,runner_path):
        self.config_path=Path(config_path).resolve();self.config=json.loads(self.config_path.read_text())
        self.runner=Path(runner_path).resolve();self.last_success={}

    def models(self):
        return [{ 'id':name,'version':self.config.get(name,{}).get('version'),
                  'environment_present':Path(python).is_file(),
                  'configured':name in self.config,
                  'functional_inference_verified':name in self.last_success,
                  'last_success':self.last_success.get(name),
                  'wall_segmentation':False}
                for name,python in PYTHONS.items()] + [
                  {'id':'doemo-walls','version':'0.2.0','role':'specialized_reconstruction',
                   'segmentation_model':'not_qualified','functional_inference_verified':False}]

    def run(self,name,request):
        if name not in PYTHONS or name not in self.config:raise ValueError('Moteur non configuré')
        if not Path(PYTHONS[name]).is_file():raise RuntimeError('Environnement absent : restauration nécessaire')
        with tempfile.TemporaryDirectory(prefix='doemo-engine-',dir='/tmp') as tmp:
            root=Path(tmp);(root/'request.json').write_text(json.dumps(request))
            # Use the startup snapshot throughout this worker's lifetime. Editing the
            # persistent config during a job cannot silently switch model versions.
            (root/'config.json').write_text(json.dumps(self.config))
            # Logs remain local and bounded by the operator, never leak environment/secrets via API.
            with (root/'engine.log').open('wb') as log:
                command=[PYTHONS[name],str(self.runner),'--engine',name,'--request',str(root/'request.json'),
                    '--config',str(root/'config.json'),'--output',str(root/'output.json')]
                process=subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True,
                    env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1',
                         'PIP_CACHE_DIR':'/tmp/doemo-pip-cache','UV_CACHE_DIR':'/tmp/doemo-uv-cache'})
                try:
                    code=process.wait(timeout=900)
                    if code:raise subprocess.CalledProcessError(code,command)
                except BaseException:
                    if process.poll() is None:
                        os.killpg(process.pid,signal.SIGKILL);process.wait()
                    log.flush()
                    logs=Path(self.config.get('_logs_dir','/workspace/doemo-studio/exports/engine-logs'))
                    logs.mkdir(parents=True,exist_ok=True)
                    with (root/'engine.log').open('rb') as stream:
                        stream.seek(max(0,stream.seek(0,2)-65536))
                        (logs/(name+'-'+uuid.uuid4().hex+'.log')).write_bytes(stream.read())
                    raise
            if (root/'output.json').stat().st_size>8*1024**2:raise ValueError('Réponse IA trop volumineuse')
            result=json.loads((root/'output.json').read_text())
            from PIL import Image
            with Image.open(request['image_path']) as image:
                width,height=image.size
            validate_output(name,result,version=self.config[name]['version'],
                            regions=request['regions'],width=width,height=height)
        import time
        self.last_success[name]=time.time()
        return result
