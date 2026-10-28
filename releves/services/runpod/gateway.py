"""Authenticated GPU gateway. Run behind HTTPS; never expose Jupyter.

The gateway has its own light environment. Each engine runs in its existing /opt
venv, serially, to avoid loading incompatible Torch builds or exhausting VRAM.
"""
import asyncio
import hmac
import json
import os
import sys
import tempfile
from pathlib import Path
from fastapi import FastAPI,Header,HTTPException,UploadFile,Depends
from PIL import Image

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
lock=asyncio.Lock()
ENGINES={'qwen':'/opt/doemo-qwen-venv/bin/python','paddleocr':'/opt/doemo-ocr-venv/bin/python','rtmdet':'/opt/doemo-rtmdet-venv/bin/python'}
ADAPTER=Path(__file__).with_name('infer.py')


def authorize(authorization:str=Header(default='')):
    token=os.environ.get('DOEMO_RUNPOD_TOKEN','')
    if len(token)<32 or not hmac.compare_digest(authorization,'Bearer '+token):
        raise HTTPException(401,'Authentification requise')


@app.get('/health',dependencies=[Depends(authorize)])
async def health():
    # Installation presence is separate from an actual successful inference.
    return {'engines':{k:Path(v).is_file() for k,v in ENGINES.items()},'model_inference_verified':False,'automatic_start':False}


@app.post('/infer/{engine}',dependencies=[Depends(authorize)])
async def infer(engine:str,file:UploadFile):
    if engine not in ENGINES:raise HTTPException(404,'Moteur inconnu')
    if not Path(ENGINES[engine]).is_file():raise HTTPException(503,'Environnement moteur absent')
    if lock.locked():raise HTTPException(503,'GPU occupé ; réessayer')
    async with lock:
        with tempfile.TemporaryDirectory(prefix='doemo-infer-',dir='/tmp') as tmp:
            source=Path(tmp)/'source.png';count=0
            with source.open('wb') as out:
                while chunk:=await file.read(1024**2):
                    count+=len(chunk)
                    if count>64*1024**2:raise HTTPException(413,'Image trop volumineuse')
                    out.write(chunk)
            try:
                with Image.open(source) as im:
                    if im.format!='PNG' or im.width*im.height>40_000_000:raise ValueError()
                    width,height=im.size;im.verify()
            except Exception:raise HTTPException(422,'PNG invalide')
            result=Path(tmp)/'result.json'
            env=dict(os.environ,UV_CACHE_DIR='/tmp/doemo-uv-cache',PIP_CACHE_DIR='/tmp/doemo-pip-cache',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
            # Keep model stdout/stderr away from public errors and bounded in /tmp.
            with (Path(tmp)/'engine.log').open('wb') as log:
                proc=await asyncio.create_subprocess_exec(ENGINES[engine],str(ADAPTER),engine,str(source),str(result),stdout=log,stderr=log,env=env,start_new_session=True)
                try:await asyncio.wait_for(proc.wait(),timeout=480)
                except (asyncio.TimeoutError,asyncio.CancelledError):
                    import signal
                    os.killpg(proc.pid,signal.SIGKILL);await proc.wait()
                    raise HTTPException(504,'Temps de traitement dépassé')
            if proc.returncode or not result.exists() or result.stat().st_size>8*1024**2:
                raise HTTPException(502,'Le moteur n’a pas fourni de résultat exploitable')
            return {'width':width,'height':height,'engine':engine,'data':json.loads(result.read_text())}
