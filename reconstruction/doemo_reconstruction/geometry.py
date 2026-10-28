"""Geometry in source page coordinates, x right, y down. No inferred metric scale."""
import math
import copy
import uuid


def distance(a, b):
    return math.hypot(b[0]-a[0], b[1]-a[1])


def wall(a, b, thickness, *, method="manual", confidence=0.0, evidence=None):
    if distance(a, b) < 1e-6 or (thickness is not None and (not math.isfinite(thickness) or thickness <= 0)):
        raise ValueError("Mur dégénéré ou épaisseur invalide")
    return {"id": uuid.uuid4().hex, "kind": "wall", "a": list(a), "b": list(b),
            "thickness": thickness, "status": "pending", "confidence": confidence,
            "method": method, "evidence": evidence or [], "openings": []}


def polygon(w, start=0., end=1.):
    a, b = w['a'], w['b']
    length = distance(a, b)
    nx, ny = -(b[1]-a[1])/length*w['thickness']/2, (b[0]-a[0])/length*w['thickness']/2
    p = [a[i]+(b[i]-a[i])*start for i in (0, 1)]
    q = [a[i]+(b[i]-a[i])*end for i in (0, 1)]
    return [[p[0]+nx,p[1]+ny], [q[0]+nx,q[1]+ny], [q[0]-nx,q[1]-ny], [p[0]-nx,p[1]-ny]]


def solid_intervals(w):
    """Subtract explicit door/window intervals. Never bridge an undocumented gap."""
    intervals, cursor = [], 0.
    for opening in sorted(w['openings'], key=lambda o: o['start']):
        start, end = opening['start'], opening['end']
        if not 0 <= start < end <= 1 or start < cursor:
            raise ValueError("Ouvertures invalides ou superposées")
        if cursor < start:
            intervals.append((cursor, start))
        cursor = end
    if cursor < 1:
        intervals.append((cursor, 1.))
    return intervals


def axis_points(w, start=0., end=1.):
    """One open centerline, in document coordinates. Thickness never offsets it."""
    return [[w['a'][i]+(w['b'][i]-w['a'][i])*t for i in (0,1)] for t in (start,end)]


def split_wall(w, fraction):
    if not math.isfinite(fraction) or not 0 < fraction < 1:
        raise ValueError('Position de coupe invalide')
    pieces=[]
    for lo,hi in ((0.,fraction),(fraction,1.)):
        part=copy.deepcopy(w)
        part['a'],part['b']=axis_points(w,lo,hi)
        part['openings']=[]
        for o in w['openings']:
            start,end=max(lo,o['start']),min(hi,o['end'])
            if start<end:
                part['openings'].append({**o,'start':(start-lo)/(hi-lo),'end':(end-lo)/(hi-lo)})
        part['status']='pending'
        part['evidence'].append({'split_from':w['id'],'interval':[lo,hi]})
        pieces.append(part)
    pieces[1]['id']=uuid.uuid4().hex
    return pieces


def pair_boundaries(lines, min_thickness=1., max_thickness=24., min_length=12.):
    """Pair observed parallel sides; retain only their common extent, at any angle.

    Furniture/frames can be paired too. These are candidates, never semantic truth.
    """
    candidates, used = [], set()
    lines = sorted(lines, key=lambda l: -distance(l[0], l[1]))[:4000]
    for i, (a, b) in enumerate(lines):
        if i in used:
            continue
        length = distance(a, b)
        if length < min_length:
            continue
        ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
        best = None
        for j in range(i+1, len(lines)):
            if j in used:
                continue
            c, d = lines[j]
            other = distance(c, d)
            if other < min_length:
                continue
            if abs(ux*(d[1]-c[1])-uy*(d[0]-c[0]))/other > math.sin(math.radians(1)):
                continue
            off = ux*(c[1]-a[1])-uy*(c[0]-a[0])
            off2 = ux*(d[1]-a[1])-uy*(d[0]-a[0])
            if abs(off-off2) > .5 or not min_thickness <= abs(off) <= max_thickness:
                continue
            c0, c1 = sorted(((c[0]-a[0])*ux+(c[1]-a[1])*uy, (d[0]-a[0])*ux+(d[1]-a[1])*uy))
            lo, hi = max(0, c0), min(length, c1)
            if hi-lo < min_length or (hi-lo)/min(length, other) < .8:
                continue
            score = abs(off)
            if best is None or score < best[0]:
                best = (score, j, lo, hi, off)
        if best:
            thickness, j, lo, hi, off = best
            p = [a[0]+ux*lo-uy*off/2, a[1]+uy*lo+ux*off/2]
            q = [a[0]+ux*hi-uy*off/2, a[1]+uy*hi+ux*off/2]
            candidates.append(wall(p,q,thickness,method="parallel_boundaries",confidence=.45,
                                   evidence=[{"lines": [i,j], "sides": [lines[i],lines[j]]}]))
            used.update((i,j))
    return candidates


def connect(w1, end1, w2, end2, max_distance):
    """Explicit human operation. Extend to line intersection; never automatic snapping."""
    a,b,c,d = w1['a'],w1['b'],w2['a'],w2['b']
    dx,dy,ex,ey = b[0]-a[0],b[1]-a[1],d[0]-c[0],d[1]-c[1]
    cross = dx*ey-dy*ex
    if abs(cross) < 1e-9:
        raise ValueError("Raccord parallèle ambigu")
    t=((c[0]-a[0])*ey-(c[1]-a[1])*ex)/cross
    point=[a[0]+t*dx,a[1]+t*dy]
    if max(distance(w1[end1],point),distance(w2[end2],point)) > max_distance:
        raise ValueError("Raccord hors tolérance")
    if w1['openings'] or w2['openings']:
        raise ValueError("Revalider les ouvertures avant de modifier la longueur")
    w1[end1],w2[end2]=point[:],point[:]
    for w in (w1,w2):
        if distance(w['a'],w['b']) < 1e-6:
            raise ValueError("Raccord dégénéré")
        w['status']='pending'


def validate(doc):
    if doc.get('schema') != 'doemo.architecture/1':
        raise ValueError("Schéma inconnu")
    if not doc['levels'] or type(doc['revision']) is not int or doc['revision']<0:
        raise ValueError('Projet vide ou révision invalide')
    if len({l['id'] for l in doc['levels']})!=len(doc['levels']):
        raise ValueError('Identifiant de niveau dupliqué')
    ids=set()
    for level in doc['levels']:
        graphic=level.get('stroke_width',1.)
        if not math.isfinite(graphic) or not 0 < graphic <= 50:
            raise ValueError('Épaisseur graphique invalide')
        for key in ('width','height'):
            if not math.isfinite(level[key]) or level[key] <= 0:
                raise ValueError("Dimensions invalides")
        for w in level['walls']:
            if w['id'] in ids:
                raise ValueError("Identifiant dupliqué")
            ids.add(w['id'])
            for p in (w['a'],w['b']):
                if len(p)!=2 or any(not math.isfinite(v) for v in p):
                    raise ValueError("Coordonnées invalides")
                if not 0<=p[0]<=level['width'] or not 0<=p[1]<=level['height']:
                    raise ValueError("Mur hors du document")
            if distance(w['a'],w['b'])<1e-6 or (w['thickness'] is not None and (not math.isfinite(w['thickness']) or w['thickness']<=0)):
                raise ValueError("Mur invalide")
            if w['status'] not in ('pending','approved','rejected'):
                raise ValueError("État invalide")
            solid_intervals(w)
            for o in w['openings']:
                if o['kind'] not in ('door','window','passage') or o['status'] not in ('pending','approved'):
                    raise ValueError("Ouverture invalide")
                if w['status']=='approved' and o['status']!='approved':
                    raise ValueError('Mur validé avec une ouverture non validée')
        scale=level.get('scale')
        if scale is not None:
            if not scale.get('validated_by') or not scale.get('evidence') or not math.isfinite(scale['mm_per_unit']) or scale['mm_per_unit']<=0:
                raise ValueError("Échelle sans cote validée")
    return doc


def journal_level(level):
    # Keep source pixels once in the project, not twice for every correction.
    return copy.deepcopy({k:level.get(k) for k in ('id','source_page','walls','scale','floor_validated','stroke_width') if k in level})


def edit(doc, level_id, operation, actor):
    if not actor.strip():
        raise ValueError("Auteur requis")
    result=copy.deepcopy(doc)
    level=next(l for l in result['levels'] if l['id']==level_id)
    before=journal_level(level)
    op=operation['op']
    if op=='identify_floor':
        level['floor_validated']=bool(operation['validated'])
    elif op=='style':
        level['stroke_width']=operation['stroke_width']
    elif op=='add':
        level['walls'].append(wall(operation['a'],operation['b'],operation['thickness']))
    elif op=='calibrate':
        n=distance(operation['a'],operation['b'])
        if n <= 0 or operation['length_mm']<=0 or not operation.get('evidence'):
            raise ValueError("Cote et preuve requises")
        level['scale']={'mm_per_unit':operation['length_mm']/n, 'validated_by':actor,
                        'evidence':operation['evidence'], 'points':[operation['a'],operation['b']]}
    else:
        w=next(w for w in level['walls'] if w['id']==operation['id'])
        if op=='delete':
            level['walls'].remove(w)
        elif op=='approve':
            if any(o['status']!='approved' for o in w['openings']):
                raise ValueError("Valider d’abord les ouvertures")
            w['status']='approved'
        elif op=='opening':
            w['openings'].append({k:operation[k] for k in ('start','end','kind','status')})
            w['status']='pending'
        elif op in ('update_opening','delete_opening'):
            idx=operation['index']
            if type(idx) is not int or not 0<=idx<len(w['openings']):
                raise ValueError('Ouverture introuvable')
            if op=='delete_opening':
                w['openings'].pop(idx)
            else:
                w['openings'][idx]={k:operation[k] for k in ('start','end','kind','status')}
            w['status']='pending'
        elif op=='split':
            parts=split_wall(w,operation['fraction'])
            level['walls'][level['walls'].index(w):level['walls'].index(w)+1]=parts
        elif op=='update':
            if w['openings'] and any(k in operation for k in ('a','b')):
                da=[operation.get('a',w['a'])[i]-w['a'][i] for i in (0,1)]
                db=[operation.get('b',w['b'])[i]-w['b'][i] for i in (0,1)]
                if distance(da,db)>1e-9:
                    raise ValueError("Revalider les ouvertures avant de modifier la longueur")
            for k in ('a','b','thickness'):
                if k in operation:
                    w[k]=operation[k]
            w['status']='pending'
        elif op=='connect':
            other=next(x for x in level['walls'] if x['id']==operation['other_id'])
            if other is w or operation['end'] not in ('a','b') or operation['other_end'] not in ('a','b'):
                raise ValueError("Raccord invalide")
            connect(w,operation['end'],other,operation['other_end'],operation['max_distance'])
        else:
            raise ValueError("Opération inconnue")
    result['revision']+=1
    result['history'].append({'revision':result['revision'],'actor':actor,'level_id':level_id,
                              'operation':operation,'before':before,'after':journal_level(level)})
    return validate(result)


def joined_polygon(w, walls, start=0., end=1.):
    """Miter exact two-way junctions, including diagonal walls and unequal thicknesses.

    Unmatched ends stay open. Acute or multiway junctions remain review items.
    """
    out=polygon(w,start,end)
    for key, indices, signs, active in [('a',(0,3),(1,-1),start==0),('b',(1,2),(-1,1),end==1)]:
        if not active: continue
        p=w[key]; other_end='b' if key=='a' else 'a'
        neighbors=[(v,k) for v in walls if v['id']!=w['id'] and v['status']!='rejected'
                   for k in ('a','b') if distance(p,v[k])<1e-6 and not v['openings']]
        if len(neighbors)!=1: continue
        v,vkey=neighbors[0]; vother='b' if vkey=='a' else 'a'
        length=distance(p,w[other_end]); vlen=distance(p,v[vother])
        u=[(w[other_end][i]-p[i])/length for i in (0,1)]
        q=[(v[vother][i]-p[i])/vlen for i in (0,1)]
        cross=u[0]*q[1]-u[1]*q[0]
        if abs(cross)<1e-8: continue
        for idx,k in zip(indices,signs):
            a=[p[0]-k*u[1]*w['thickness']/2,p[1]+k*u[0]*w['thickness']/2]
            b=[p[0]+k*q[1]*v['thickness']/2,p[1]-k*q[0]*v['thickness']/2]
            t=((b[0]-a[0])*q[1]-(b[1]-a[1])*q[0])/cross
            point=[a[0]+t*u[0],a[1]+t*u[1]]
            if distance(point,p)<=4*max(w['thickness'],v['thickness']):
                out[idx]=point
    return out
