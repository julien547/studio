"""Validate uploads and evidence without trusting coordinates or claims from a model."""
import base64
import hashlib
import io
import math
import re
from PIL import Image
from pydantic import BaseModel,ConfigDict,Field


class AnalysisRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    project_id:str=Field(min_length=1,max_length=128,pattern=r'^[a-zA-Z0-9_-]+$')
    page:int=Field(ge=1,le=10000)
    source_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    image_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    image_base64:str=Field(max_length=12*1024**2)
    width:int=Field(ge=1,le=10000)
    height:int=Field(ge=1,le=10000)
    regions:list[dict]=Field(default_factory=list,max_length=80)
    engines:list[str]=Field(default_factory=lambda:['paddleocr','qwen'],min_length=1,max_length=3)
    model_versions:dict[str,str]
    parameters:dict=Field(default_factory=dict)


def validate_request(request):
    r=AnalysisRequest.model_validate(request).model_dump()
    if r['width']*r['height']>20_000_000:raise ValueError('Image trop grande')
    if len(set(r['engines']))!=len(r['engines']) or any(e not in ('qwen','paddleocr','rtmdet') for e in r['engines']):raise ValueError('Moteur invalide')
    if set(r['model_versions'])!=set(r['engines']):raise ValueError('Versions explicites requises')
    if 'rtmdet' in r['engines'] and r['parameters'].get('diagnostic_only') is not True:raise ValueError('RTMDet COCO réservé au diagnostic, jamais aux murs')
    data=base64.b64decode(r['image_base64'],validate=True)
    if hashlib.sha256(data).hexdigest()!=r['image_sha256']:raise ValueError('Image corrompue')
    with Image.open(io.BytesIO(data)) as image:
        if image.format!='PNG' or image.size!=(r['width'],r['height']):raise ValueError('PNG ou dimensions invalides')
        image.verify()
    seen=set()
    for region in r['regions']:
        if set(region)!={'id','bbox'} or not re.fullmatch('[a-zA-Z0-9_-]{1,80}',region['id']) or region['id'] in seen:raise ValueError('Zone invalide')
        seen.add(region['id']);b=region['bbox']
        if len(b)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in b) or not (0<=b[0]<b[2]<=r['width'] and 0<=b[1]<b[3]<=r['height']):raise ValueError('Zone hors image')
    if not r['regions']:r['regions']=[{'id':'page','bbox':[0,0,r['width'],r['height']]}]
    return r,data
