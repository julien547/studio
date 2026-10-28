"""Interoperate with the existing Studio Plans analysis v3; do not replace its editor.

The caller supplies an already loaded source reference and source page dimensions.
The engine's image canvas and the PDF's document points are different coordinate spaces.
"""
import copy
import math
from .geometry import wall, distance, validate


def import_analysis(document, level_id, analysis, *, include_unknown_thickness=False):
    out=copy.deepcopy(document)
    level=next(l for l in out['levels'] if l['id']==level_id)
    if analysis.get('schemaVersion')!=3 or analysis.get('coordinateSpace')!='source':
        raise ValueError('Contrat Studio Plans incompatible')
    source=analysis['source']
    if source['page']!=level['source_page'] or source.get('rotation',0)!=0:
        raise ValueError('Source ou rotation incompatible')
    sx,sy=level['width']/source['width'],level['height']/source['height']
    if not all(math.isfinite(v) and v>0 for v in (sx,sy)):
        raise ValueError('Transformation de source invalide')
    converted=[];ids={};skipped=[]
    for old in analysis['walls']:
        thickness=old.get('thickness')
        if thickness is None and not include_unknown_thickness:
            skipped.append(old['id']);continue
        a=[old['a']['x'],old['a']['y']];b=[old['b']['x'],old['b']['y']]
        p=[a[0]*sx,a[1]*sy];q=[b[0]*sx,b[1]*sy]
        # Perpendicular separation after anisotropic affine scaling.
        new_thickness=None if thickness is None else thickness*sx*sy*distance(a,b)/distance(p,q)
        w=wall(p,q,new_thickness,method='studio_plans_existing_engine',
               confidence=old.get('confidence') or 0,evidence=[{'engine':analysis['engineVersion'],
               'original_id':old['id'],'warnings':old.get('warnings',[]),'original_evidence':old.get('evidence')}])
        w['id']=level_id+'-'+old['id'];converted.append(w);ids[old['id']]=w
    for old in analysis.get('openings',[]):
        w=ids.get(old['wallId'])
        if w is None:continue
        parent=next(p for p in analysis['walls'] if p['id']==old['wallId'])
        length=math.hypot(parent['b']['x']-parent['a']['x'],parent['b']['y']-parent['a']['y'])
        w['openings'].append({'kind':{'Door':'door','Window':'window','Opening':'passage'}[old['type']],
             'start':old['offset']/length,'end':(old['offset']+old['width'])/length,'status':'pending'})
    if level.get('walls'):
        raise ValueError('Importer dans un niveau vide pour préserver les corrections existantes')
    level['walls']=converted
    level['engine_import']={'version':analysis['engineVersion'],'source_canvas':source,
        'source_canvas_to_document':[sx,0,0,sy,0,0],'unknown_thickness_omitted':skipped,
        'metrics':analysis.get('metrics'),'warnings':analysis.get('warnings')}
    level['floor_validated']=False
    level['scale']=None
    return validate(out)
