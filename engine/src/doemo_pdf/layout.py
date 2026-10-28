"""Place publication blocks without changing the architectural paint streams."""
import math
import re

from .scene import union
from .template_zones import contains, overlap, area


def level_title(text):
    return bool(re.fullmatch(r'\s*(?:NIVEAU\s+.+|R\s*D\s*C|REZ[- ]DE[- ]CHAUSS[ÉE]E|R\s*[+-]\s*\d+|SOUS[- ]SOL(?:\s*\d+)?|(?:[ÉE]TAGE\s*\d+|\d+\s*(?:ER|[EÈ]ME)?\s*[ÉE]TAGE))\s*',text,re.I))


def distance(a,b):
    return math.hypot(max(a[0]-b[2],b[0]-a[2],0),max(a[1]-b[3],b[1]-a[3],0))


def level_regions(scene, titles, plan, symbol_ids):
    """Use separated architectural clusters only to anchor titles, never to clip.

    A source contour may include an entire wall chain. Joining nearby bounds
    is conservative: an uncertain separation stays one composition.
    """
    paths=[scene.items[i] for i in plan if i not in symbol_ids and scene.items[i].kind=='path'
           and re.match(r'^(relev[ée]|architecture|plan)(?:$|[ _-])',scene.items[i].layer or '',re.I)]
    if not paths:paths=[scene.items[i] for i in plan if i not in symbol_ids and scene.items[i].kind=='path']
    clusters=[]
    for item in paths:
        box=item.bounds
        while True:
            close=[b for b in clusters if distance(b,box)<=8]
            if not close:break
            clusters=[b for b in clusters if b not in close];box=union([box,*close])
        clusters.append(box)
    whole=union(scene.items[i].bounds for i in plan)
    large=[b for b in clusters if area(b)>=max((area(c) for c in clusters),default=0)*.015]
    regions=[]
    for ids in titles:
        title=union(scene.items[i].bounds for i in ids)
        nearest=min(large,key=lambda b:distance(title,b)) if large else whole
        regions.append({'items':ids,'name':' '.join(scene.items[i].text for i in ids),'source_bounds':nearest})
    return regions


def title_position(box, region, available, obstacles):
    """Try below the relevant level first, then beside it. Never clip a title."""
    w,h=box[2]-box[0],box[3]-box[1]
    cx=(region[0]+region[2])/2;cy=(region[1]+region[3])/2
    below=[region[1]-8-h,*(b[1]-8-h for b in obstacles if b[1]<region[1])]
    for y in sorted(set(below),reverse=True):
        candidate=(cx-w/2,y,cx+w/2,y+h)
        if contains(available,candidate) and not any(overlap(candidate,b) for b in obstacles):return candidate,'below'
    for x in (region[2]+8,region[0]-8-w):
        candidate=(x,cy-h/2,x+w,cy+h/2)
        if contains(available,candidate) and not any(overlap(candidate,b) for b in obstacles):return candidate,'side'
    raise ValueError('Pas de place libre pour le nom du niveau sous le plan ou sur le côté.')


def logo_slot(scene, indices, page, kind, orientation):
    """PE logo follows the prevention column: left in landscape, right in portrait."""
    x0,y0,x1,y1=page;mid=(x0+x1)/2
    default=(x1-12-(x1-x0)*.30,y0+22,x1-12,y0+12+(y1-y0)*.12)
    if kind!='PE':return default
    bands=[scene.items[i].bounds for i in indices if scene.items[i].fill is not None
           and len(scene.items[i].fill)==4 and scene.items[i].fill[0]<.4 and scene.items[i].fill[1]<.4
           and scene.items[i].fill[2]>.5 and scene.items[i].fill[3]<.4
           and scene.items[i].bounds[3]<(y0+y1)/2
           and scene.items[i].bounds[2]-scene.items[i].bounds[0]>(x1-x0)*.1
           and scene.items[i].bounds[3]-scene.items[i].bounds[1]<(y1-y0)*.05
           and (scene.items[i].bounds[2]<mid if orientation=='H' else scene.items[i].bounds[0]>mid)]
    if len(bands)!=1:
        if orientation=='H':raise ValueError('Colonne PRÉVENTION gauche non identifiée dans la trame PE horizontale pour placer le logo.')
        return default
    band=bands[0]
    obstacles=[scene.items[i].bounds for i in indices if scene.items[i].bounds[2]>band[0] and scene.items[i].bounds[0]<band[2]
               and scene.items[i].bounds[3]<band[1] and scene.items[i].bounds[1]>y0+12]
    slot=(band[0],y0+22,band[2],min((b[1] for b in obstacles),default=band[1])-8)
    if slot[3]<=slot[1]:raise ValueError('Espace blanc insuffisant sous PRÉVENTION pour le logo client.')
    return slot
