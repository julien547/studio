"""Vector-only template placement: named zone, white guide, then free space."""
import math
import re

from .bindings import geometry_path

def area(b):return (b[2]-b[0])*(b[3]-b[1])


def contains(a,b,tol=.02):
    return a[0]-tol<=b[0] and a[1]-tol<=b[1] and a[2]+tol>=b[2] and a[3]+tol>=b[3]


def overlap(a,b):return min(a[2],b[2])-max(a[0],b[0])>.01 and min(a[3],b[3])-max(a[1],b[1])>.01


def named(layer):return bool(re.match(r'^(?:DOEMO[ _-]*)?ZONE(?:$|[\s_.-]|\d)',layer or '',re.I))


def white(color):return color is not None and len(color)==4 and all(abs(c)<=.001 for c in color)


def rectangle(item):
    if item.kind!='path' or any(row[0] not in ('m','l','h') for row in item.geometry):return None
    if sum(row[0]=='m' for row in item.geometry)!=1:return None
    points=[row[1:] for row in item.geometry if row[0]!='h']
    if len(points)<4:return None
    if item.geometry[-1][0]!='h' and math.dist(points[0],points[-1])>.02 and item.operator not in ('f','f*','F','s','b','b*'):return None
    if math.dist(points[0],points[-1])<.02:points.pop()
    b=(min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points))
    if area(b)<=0:return None
    pairs=list(zip(points,points[1:]+points[:1]))
    if any(abs(a[0]-c[0])>.02 and abs(a[1]-c[1])>.02 for a,c in pairs):return None
    signed=abs(sum(a[0]*c[1]-c[0]*a[1] for a,c in pairs))/2
    return b if abs(signed-area(b))<=.02*(b[2]-b[0]+b[3]-b[1]) else None


def unique(boxes):
    result=[]
    for b in boxes:
        if not any(max(abs(x-y) for x,y in zip(b,a))<=.05 for a in result):result.append(tuple(b))
    return result


def detect_zone(scene,box,layers,role):
    page_area=area(box)
    explicit=unique([geometry_path(it.geometry).bounds if it.kind=='path' else it.bounds for it in scene.items if named(it.layer)]+
                    [g['bounds'] for g in scene.guides if named(g['layer'])])
    if explicit:
        if len(explicit)!=1:raise ValueError('Plusieurs repères ZONE différents sont présents dans la trame.')
        b=explicit[0]
        if not contains(box,b) or min(b[2]-b[0],b[3]-b[1])<=48:raise ValueError('Repère ZONE hors page ou trop petit.')
        return b,{'method':'named-layer','bounds':list(b)}
    candidates=[]
    for it in scene.items:
        b=rectangle(it)
        filled=it.operator in ('f','f*','F','B','B*','b','b*')
        marker_white=white(it.fill) if filled else white(it.stroke)
        if role(it.layer)=='footer' and white(it.stroke):marker_white=True
        if b and contains(box,b) and .2*page_area<=area(b)<.95*page_area and marker_white:
            candidates.append((it,b))
    # Same conservative maximal-empty-rectangle rule as the Illustrator script.
    # Keep printed obstacles, except removable sample fields and SPECIMEN.
    obstacles=[]
    for it in scene.items:
        if not layers.get(it.layer,True) or role(it.layer) in ('header','footer','legend') or named(it.layer):continue
        if re.search(r'(?:^|/)sp[ée]cimen(?:$|[ _/-])',it.layer or '',re.I):continue
        b=rectangle(it)
        filled=it.operator in ('f','f*','F','B','B*','b','b*')
        stroked=it.operator in ('S','s','B','B*','b','b*')
        if b and (not filled or (white(it.fill) and area(b)>=.2*page_area)):
            if stroked and not white(it.stroke):
                # Visible stroke bounds include its thickness. Keep all four
                # edges as obstacles, rather than treating the interior as ink.
                outer=it.bounds;w=max(.02,max(abs(x-y) for x,y in zip(outer,b)))
                obstacles.extend([(outer[0],b[1]-w,outer[2],b[1]+w),(outer[0],b[3]-w,outer[2],b[3]+w),
                                  (b[0]-w,outer[1],b[0]+w,outer[3]),(b[2]-w,outer[1],b[2]+w,outer[3])])
        else:obstacles.append(it.bounds)
    # A large white background behind printed instructions is not a guide.
    # Keep a white candidate only when its inner area is actually available.
    candidates=[(it,b) for it,b in candidates if not any(overlap((b[0]+12,b[1]+12,b[2]-12,b[3]-12),o) for o in obstacles)]
    preferred=unique(b for it,b in candidates if role(it.layer)=='footer')
    available=preferred or unique(b for _,b in candidates)
    if len(available)==1:
        b=available[0]
        return b,{'method':'white-rectangle','bounds':list(b)}
    regions=[tuple(box)]
    # Large obstacles first keeps the search bounded for complex instructions.
    for b in sorted(obstacles,key=area,reverse=True):
        next_regions=[]
        for a in regions:
            if not overlap(a,b):next_regions.append(a);continue
            pieces=[(a[0],a[1],min(a[2],b[0]),a[3]),(max(a[0],b[2]),a[1],a[2],a[3]),
                    (a[0],a[1],a[2],min(a[3],b[1])),(a[0],max(a[1],b[3]),a[2],a[3])]
            next_regions.extend(p for p in pieces if min(p[2]-p[0],p[3]-p[1])>48 and area(p)>=.2*page_area)
        next_regions=unique(next_regions)
        regions=[a for n,a in enumerate(next_regions) if not any(n!=k and contains(other,a,.001) for k,other in enumerate(next_regions))]
        if len(regions)>256:raise ValueError('Trame trop complexe pour déduire sa zone libre ; ajouter un repère ZONE.')
    regions.sort(key=area,reverse=True)
    if not regions:raise ValueError('Aucune zone libre suffisante dans la trame ; ajouter un repère ZONE.')
    if len(regions)>1 and area(regions[1])>area(regions[0])*.95:
        raise ValueError('Plusieurs zones libres équivalentes dans la trame ; ajouter un repère ZONE pour choisir.')
    b=regions[0]
    return b,{'method':'free-space','bounds':list(b),'obstacle_count':len(obstacles)}
