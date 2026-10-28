"""Several floors on one page, without translating source coordinates."""
import copy
from .geometry import validate


def separate_levels(doc, regions):
    result=copy.deepcopy(doc);levels=[];ids=set()
    for region in regions:
        source=next(l for l in doc['levels'] if l['source_page']==region['source_page'])
        x0,y0,x1,y1=region['bbox']
        if not 0<=x0<x1<=source['width'] or not 0<=y0<y1<=source['height']:
            raise ValueError('Région hors de la page')
        if region['id'] in ids: raise ValueError('Niveau dupliqué')
        ids.add(region['id'])
        level=copy.deepcopy(source);level.update(id=region['id'],name=region['name'],
            region=region['bbox'],floor_validated=False)
        level['walls']=[w for w in level['walls'] if all(x0<=p[0]<=x1 and y0<=p[1]<=y1 for p in (w['a'],w['b']))]
        level['texts']=[t for t in level.get('texts',[]) if x0<=t['bbox'][0]<=t['bbox'][2]<=x1 and y0<=t['bbox'][1]<=t['bbox'][3]<=y1]
        for w in level['walls']:w['id']=level['id']+'-'+w['id']
        levels.append(level)
    result['levels']=levels
    return validate(result)
