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
    """Pair observed sides over unused intervals, preserving gaps and all orientations.

    A long side may support several shorter opposite sides. Consuming one pairing
    never consumes its unused tails. Furniture/frames remain ambiguous candidates;
    neither semantic identity nor a metric scale is inferred here.
    """
    if (not all(math.isfinite(v) for v in (min_thickness, max_thickness, min_length))
            or not 0 < min_thickness <= max_thickness or min_length <= 0):
        raise ValueError('Tolérances géométriques invalides')
    # Canonical endpoints make equal-length and reversed inputs deterministic.
    canonical = set()
    for endpoints in lines:
        if len(endpoints) != 2 or any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in endpoints):
            raise ValueError('Bord invalide')
        a, b = sorted(tuple(p) for p in endpoints)
        if distance(a, b) >= min_length:
            canonical.add((a, b))
    lines = sorted(canonical, key=lambda line: (-distance(*line), line))[:4000]
    lengths = [distance(*line) for line in lines]
    free = [[(0., 1.)] for _ in lines]
    candidates = []

    def consume(intervals, lo, hi):
        out = []
        for start, end in intervals:
            if start < min(end, lo):
                out.append((start, min(end, lo)))
            if max(start, hi) < end:
                out.append((max(start, hi), end))
        return out

    for i, (a, b) in enumerate(lines):
        length = lengths[i]
        if not any((hi-lo)*length >= min_length for lo, hi in free[i]):
            continue
        ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
        partners = []
        for j in range(i+1, len(lines)):
            if not any((hi-lo)*lengths[j] >= min_length for lo, hi in free[j]):
                continue
            c, d = lines[j]
            if abs(ux*(d[1]-c[1])-uy*(d[0]-c[0]))/lengths[j] > math.sin(math.radians(1)):
                continue
            c0, c1 = [(p[0]-a[0])*ux+(p[1]-a[1])*uy for p in (c, d)]
            off0, off1 = [ux*(p[1]-a[1])-uy*(p[0]-a[0]) for p in (c, d)]
            if (abs(off0-off1) > .5 or off0*off1 <= 0
                    or not all(min_thickness <= abs(off) <= max_thickness for off in (off0, off1))):
                continue
            lo, hi = max(0., min(c0, c1)), min(length, max(c0, c1))
            if hi-lo < min_length or (hi-lo)/min(length, lengths[j]) < .8:
                continue
            partners.append((abs((off0+off1)/2), j, c0, c1))
        for _, j, c0, c1 in sorted(partners):
            c, d = lines[j]
            # Intersect the remaining intervals on both observed sides. Endpoints
            # are not extended and distinct intervals are never joined.
            overlaps = []
            for start, end in free[i]:
                for other_start, other_end in free[j]:
                    projected = sorted((c0+(c1-c0)*other_start, c0+(c1-c0)*other_end))
                    lo, hi = max(start*length, projected[0]), min(end*length, projected[1])
                    if hi-lo >= min_length:
                        overlaps.append((lo, hi))
            for lo, hi in overlaps:
                first = [[a[0]+ux*t, a[1]+uy*t] for t in (lo, hi)]
                fractions = [(t-c0)/(c1-c0) for t in (lo, hi)]
                second = [[c[k]+(d[k]-c[k])*t for k in (0, 1)] for t in fractions]
                median = [[(p[k]+q[k])/2 for k in (0, 1)] for p, q in zip(first, second)]
                widths = [distance(p, q) for p, q in zip(first, second)]
                first_range = [max(0., lo/length), min(1., hi/length)]
                second_range = [max(0., min(fractions)), min(1., max(fractions))]
                candidates.append(wall(*median, sum(widths)/2, method='parallel_boundaries', confidence=0.,
                    evidence=[{'lines': [i, j], 'sides': [lines[i], lines[j]],
                               'source_intervals': [first_range, second_range], 'paired_sides': [first, second],
                               'algorithm': 'unused_boundary_intervals/1', 'semantic_status': 'unknown',
                               'review': ['wall_or_symbol', 'junctions', 'openings']}]))
                free[i] = consume(free[i], *first_range)
                free[j] = consume(free[j], *second_range)
            if not any((end-start)*length >= min_length for start, end in free[i]):
                break
    return candidates


def merge_parallel_faces(w1, w2, max_separation=24.):
    """Explicit human interpretation of two traces as faces of the SAME wall.

    Replace only their common observed extent by one median; preserve unmatched
    tails as pending traces. Openings require separate review, never implicit union.
    """
    if w1['id'] == w2['id'] or w1['openings'] or w2['openings']:
        raise ValueError('Choisir deux traces distinctes sans ouverture renseignée')
    if any(w['status'] == 'rejected' for w in (w1, w2)):
        raise ValueError('Trace rejetée')
    if not math.isfinite(max_separation) or max_separation <= 0:
        raise ValueError('Distance maximale invalide')
    a, b, c, d = w1['a'], w1['b'], w2['a'], w2['b']
    length, other = distance(a, b), distance(c, d)
    ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
    if abs(ux*(d[1]-c[1])-uy*(d[0]-c[0]))/other > math.sin(math.radians(1)):
        raise ValueError('Les traces ne sont pas parallèles (tolérance 1 degré)')
    projected = [(p[0]-a[0])*ux+(p[1]-a[1])*uy for p in (c, d)]
    lo, hi = max(0., min(projected)), min(length, max(projected))
    if hi-lo < 1e-6:
        raise ValueError('Aucune portion commune ; le passage reste ouvert')
    ranges = [[lo/length, hi/length], [(t-projected[0])/(projected[1]-projected[0]) for t in (lo, hi)]]
    faces = [axis_points(w1, *ranges[0]), axis_points(w2, *ranges[1])]
    offsets = [ux*(q[1]-p[1])-uy*(q[0]-p[0]) for p, q in zip(*faces)]
    if (offsets[0]*offsets[1] <= 0 or min(map(abs, offsets)) < 1e-6
            or max(map(abs, offsets)) > max_separation or abs(offsets[0]-offsets[1]) > .5):
        raise ValueError('Séparation des traces ambiguë ou supérieure à la tolérance')
    median = [[(p[k]+q[k])/2 for k in (0, 1)] for p, q in zip(*faces)]
    center = wall(*median, sum(map(abs, offsets))/2, method='manual_parallel_faces',
                  evidence=[{'source_walls': [w1['id'], w2['id']], 'paired_sides': faces,
                             'source_intervals': ranges, 'human_interpretation': 'same_wall_faces'}])
    remainders = []
    for w, interval in zip((w1, w2), ranges):
        start, end = sorted(max(0., min(1., t)) for t in interval)
        parts = [(0., start), (end, 1.)]
        for rlo, rhi in parts:
            if (rhi-rlo)*distance(w['a'], w['b']) < 1e-6:
                continue
            piece = copy.deepcopy(w)
            piece['id'] = uuid.uuid4().hex
            piece['a'], piece['b'] = axis_points(w, rlo, rhi)
            piece['status'] = 'pending'
            piece['evidence'].append({'unmerged_remainder_of': w['id'], 'source_interval': [rlo, rhi]})
            remainders.append(piece)
    return [center, *remainders]


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
        elif op=='merge_parallel_faces':
            other=next(x for x in level['walls'] if x['id']==operation['other_id'])
            pieces=merge_parallel_faces(w,other,operation.get('max_separation',24.))
            level['walls']=[x for x in level['walls'] if x['id'] not in (w['id'],other['id'])]+pieces
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
