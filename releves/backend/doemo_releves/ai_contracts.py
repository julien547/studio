"""Import observations, never validated equipment. Source dimensions are mandatory.

The raw response is archived by the caller; positional results retain their engine,
frame and score semantics. A COCO model cannot create DOEMO equipment categories.
"""
import math
import uuid
from .models import Annotation, Box


def normalise(engine, data, document_id, page, width, height):
    if not (0 < width <= 50000 and 0 < height <= 50000):
        raise ValueError('Dimensions de l’image analysée requises')
    if not isinstance(data, dict):
        raise ValueError('Objet JSON attendu')
    res = data.get('res', data)
    if not isinstance(res, dict):
        raise ValueError('Format res non reconnu')
    annotations, observations, warnings = [], [], []
    def box(points):
        if not isinstance(points, list) or len(points)<2:
            raise ValueError('Polygone absent')
        coords = [(float(p[0])/width,float(p[1])/height) for p in points]
        x,y=min(p[0] for p in coords),min(p[1] for p in coords)
        right,bottom=max(p[0] for p in coords),max(p[1] for p in coords)
        return Box(x=x,y=y,w=right-x,h=bottom-y)
    def add(text, b, score, method):
        if not isinstance(text,str) or type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=1:
            raise ValueError('Texte ou score OCR invalide')
        annotations.append(Annotation(id=uuid.uuid4().hex, source_document_id=document_id,
            source_page=page,bbox=b,text=str(text)[:2000],confidence=float(score),method=method,
            anchor=None,evidence='Observation importée ; position de l’équipement à pointer séparément.').model_dump())
    if engine=='paddleocr':
        texts=res.get('rec_texts',[]);polys=res.get('rec_polys',res.get('dt_polys',[]));scores=res.get('rec_scores',[])
        if not all(isinstance(v,list) for v in (texts,polys,scores)) or not(len(texts)==len(polys)==len(scores)) or len(texts)>10000:
            raise ValueError('Textes, polygones et scores OCR non alignés')
        for text, poly, score in zip(texts,polys,scores):
            add(text,box(poly),score,'paddleocr:import')
        warnings.append('Score de reconnaissance du texte, pas probabilité de présence d’un équipement.')
    elif engine=='qwen':
        zones=res.get('zones',[])
        if not isinstance(zones,list) or len(zones)>100:
            raise ValueError('Zones Qwen invalides')
        for zone in zones:
            if not isinstance(zone,dict) or not isinstance(zone.get('elements'),list) or len(zone['elements'])>1000:
                raise ValueError('Éléments Qwen invalides')
            seen=set()
            for element in zone['elements']:
                if not isinstance(element,dict) or not isinstance(element.get('texte',''),str):
                    raise ValueError('Observation Qwen invalide')
                text=str(element.get('texte',''))[:2000]
                if text in seen: continue
                seen.add(text)
                observations.append({'text':text,'zone':str(zone.get('zone',''))[:100], 'uncertain':True,
                    'source':'qwen','location':None})
        warnings.append('Qwen ne fournit pas de coordonnées : observations textuelles uniquement, répétitions regroupées par zone.')
    elif engine=='rtmdet':
        scores=res.get('scores',[]);labels=res.get('labels',[]);boxes=res.get('bboxes',[])
        if not all(isinstance(v,list) for v in (scores,labels,boxes)) or not(len(scores)==len(labels)==len(boxes)) or len(scores)>10000:
            raise ValueError('Sortie RTMDet invalide')
        outside=0
        for score,coords in zip(scores,boxes):
            if not isinstance(score,(int,float)) or not math.isfinite(score) or not 0<=score<=1 or len(coords)!=4:
                raise ValueError('Détection RTMDet invalide')
            if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in coords) or coords[2]<=coords[0] or coords[3]<=coords[1]:
                raise ValueError('Boîte RTMDet invalide')
            if coords[0]<0 or coords[1]<0 or coords[2]>width or coords[3]>height:outside+=1
        observations=[{'source':'rtmdet-coco','proposals':len(scores),'max_score':max(scores,default=0),
                       'above_40_percent':sum(s>=.4 for s in scores),'equipment_created':0,
                       'boxes_outside_declared_frame':outside}]
        if outside:
            warnings.append('Des boîtes dépassent les dimensions déclarées : vérifier l’image de référence du moteur. Aucune superposition autorisée.')
        warnings.append('Modèle COCO générique : aucune proposition convertie en équipement DOEMO.')
    else:
        raise ValueError('Moteur inconnu')
    return {'annotations':annotations,'observations':observations,'warnings':warnings,
            'source_frame':{'width':width,'height':height,'origin':'top_left','unit':'px'},
            'score_semantics':'uncalibrated_model_score','human_validation_required':True}
