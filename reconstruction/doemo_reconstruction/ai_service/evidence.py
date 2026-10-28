"""Attach AI observations without overwriting geometry or human validation."""
import copy
import math
from ..geometry import validate


def attach_evidence(document,level_id,evidence,request):
    out=copy.deepcopy(document);level=next(l for l in out['levels'] if l['id']==level_id)
    if evidence.get('schema')!='doemo.ai.evidence/1' or evidence['source_sha256']!=out['source']['sha256'] or evidence['page']!=level['source_page']:
        raise ValueError('Résultat IA pour une autre source')
    if evidence['image_sha256']!=request['image_sha256'] or evidence['coordinate_space']!='input_image_pixels':
        raise ValueError('Référentiel IA incompatible')
    if evidence['width']!=request['width'] or evidence['height']!=request['height']:raise ValueError('Dimensions IA incompatibles')
    sx,sy=level['width']/evidence['width'],level['height']/evidence['height']
    def point(p):
        if len(p)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in p):raise ValueError('Coordonnée IA invalide')
        if not 0<=p[0]<=evidence['width'] or not 0<=p[1]<=evidence['height']:raise ValueError('Observation hors page')
        return [p[0]*sx,p[1]*sy]
    ocr=[]
    for text in evidence.get('engines',{}).get('paddleocr',{}).get('texts',[]):
        polygon=[point(p) for p in text['polygon']]
        if len(polygon)<3 or not isinstance(text['text'],str) or not 0<=text['confidence']<=1:raise ValueError('Texte OCR invalide')
        ocr.append({**text,'polygon':polygon,'status':'pending','method':'paddleocr',
                    'bbox':[min(p[0] for p in polygon),min(p[1] for p in polygon),max(p[0] for p in polygon),max(p[1] for p in polygon)]})
    known={r['id']:r['bbox'] for r in request['regions']};zones=[]
    for zone in evidence.get('engines',{}).get('qwen',{}).get('zones',[]):
        if zone['id'] not in known:raise ValueError('Zone inventée par Qwen')
        b=known[zone['id']];a,c=point(b[:2]),point(b[2:])
        zones.append({'bbox':a+c,'reason':zone['note'],'label':zone['label'],'status':'pending','method':'qwen'})
    # Idempotent evidence attachment; reviewed walls and prior user history are untouched.
    level.setdefault('ai_evidence',{})[evidence['job_id']]={'texts':ocr,'zones':zones,
        'model_versions':evidence['model_versions'],'image_to_document':[sx,0,0,sy,0,0],
        'execution':{'job_id':evidence['job_id'],'worker':evidence.get('executed_on'),
                     'engines_returned':sorted(evidence.get('engines',{})),
                     'source_sha256':evidence['source_sha256'],'image_sha256':evidence['image_sha256']},
        'rtmdet_diagnostic_count':len(evidence.get('engines',{}).get('rtmdet',{}).get('detections',[])),
        'rtmdet_usage':'diagnostic_only_never_walls'}
    return validate(out)
