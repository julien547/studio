"""Match native Illustrator identities to original PDF paint records.

Geometry is used only for correspondence. Original PDF operators are retained
for output. The supported profile is deliberately bounded and fails closed.
"""
import math
import re
from dataclasses import dataclass
import pathops
import pikepdf

from .ai_metadata import decode_native, parse_native, ps_string, MATRIX
from .scene import Scene, I, point, multiply, path_geometry, instruction, union
from .pdf import parse_label

DIRECTIONAL=re.compile(r'vers[ _-]?(?:la[ _-])?(?:sortie|issue)|fl[eè]che|direction|arrow',re.I)
MARKER=re.compile(r'\bvei\b|vous[ _-]*[eê]tes|nouveau symbole',re.I)


def geometry_path(geometry):
    p=pathops.Path();started=False
    for row in geometry:
        if row[0]=='m':
            if started:p.close()
            p.moveTo(*row[1:]);started=True
        elif row[0]=='l':p.lineTo(*row[1:])
        elif row[0]=='c':p.cubicTo(*row[1:])
        elif row[0]=='h':p.close();started=False
    if started:p.close()
    return p


def samples(geometry):
    """Bounded subdivision for matching only, never for exported PDF paths."""
    last=first=None
    def line(a,b):
        count=max(1,math.ceil(math.dist(a,b)/.01))
        if count>200000:raise ValueError('Contour de symbole trop étendu.')
        for i in range(count+1):
            t=i/count;yield (a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t)
    def curve(a,b,c,d,depth=0):
        chord=math.dist(a,d)
        distance=lambda p: math.dist(p,a) if chord==0 else abs((p[0]-a[0])*(d[1]-a[1])-(p[1]-a[1])*(d[0]-a[0]))/chord
        # Also subdivide collinear curves with non-monotonic control points.
        polygon=math.dist(a,b)+math.dist(b,c)+math.dist(c,d)
        if depth>=18 or max(distance(b),distance(c),polygon-chord)<.00025:
            yield from line(a,d);return
        mid=lambda p,q:((p[0]+q[0])/2,(p[1]+q[1])/2)
        ab=mid(a,b);bc=mid(b,c);cd=mid(c,d);abc=mid(ab,bc);bcd=mid(bc,cd);abcd=mid(abc,bcd)
        yield from curve(a,ab,abc,abcd,depth+1);yield from curve(abcd,bcd,cd,d,depth+1)
    for row in geometry:
        op=row[0]
        if op=='m':
            if last is not None and first is not None:yield from line(last,first)
            last=first=row[1:]
        elif op=='l':yield from line(last,row[1:]);last=row[1:]
        elif op=='c':yield from curve(last,row[1:3],row[3:5],row[5:7]);last=row[5:7]
        elif op=='h':
            if last is not None:yield from line(last,first)
            last=first=None
    if last is not None and first is not None:yield from line(last,first)


def outlines_match(a,b):
    # Match complete outline samples in both directions. Spacing <= .01 pt,
    # curve flatness <= .00025 pt, sample distance <= .008 pt: a conservative
    # .02 pt geometric correspondence bound. This never changes output paths.
    from collections import defaultdict
    def index(geometry):
        grid=defaultdict(list);points=[]
        for p in samples(geometry):
            if len(points)>=2000000:raise ValueError('Symbole trop complexe pour la comparaison.')
            points.append(p);grid[(math.floor(p[0]*100),math.floor(p[1]*100))].append(p)
        return grid,points
    aa,ap=index(a);bb,bp=index(b)
    if not ap or not bp:return False
    for points,grid in [(ap,bb),(bp,aa)]:
        for x,y in points:
            ix,iy=math.floor(x*100),math.floor(y*100)
            if not any((x-u)**2+(y-v)**2<=.008**2 for dx in (-1,0,1) for dy in (-1,0,1)
                       for u,v in grid.get((ix+dx,iy+dy),())):return False
    return True


def native_geometry(text, matrix=I, commented=False):
    commands=[];result=[]
    for raw in text.splitlines():
        if commented:
            if not raw.startswith('%_'):continue
            raw=raw[2:]
        elif raw.startswith('%'):continue
        bits=raw.split()
        if not bits:continue
        op=bits[-1]
        try:values=[float(x) for x in bits[:-1]]
        except ValueError:continue
        if any(not math.isfinite(x) for x in values):raise ValueError('Coordonnée native non finie.')
        mapping={'m':'m','l':'l','L':'l','c':'c','C':'c','v':'v','V':'v','y':'y','Y':'y'}
        if op in mapping:
            if len(values)!={'m':2,'l':2,'c':6,'v':4,'y':4}[mapping[op]]:raise ValueError('Tracé natif incomplet.')
            commands.append(instruction(mapping[op],values))
        elif op in ('f','F','s','S','b','B','n','N'):
            if commands and op not in ('n','N'):
                _,geom=path_geometry(commands,matrix)
                result.extend(geom);result.append(('h',))
            commands=[]
    if commands:raise ValueError('Tracé natif non terminé.')
    return result


def center(bounds):return ((bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2)


@dataclass
class Symbol:
    id: str
    name: str
    layer: str
    items: list
    bounds: tuple
    directional: bool
    marker: bool


@dataclass
class Marker:
    id: str
    index: int
    symbol: Symbol
    stem: int
    head: int
    label: int
    kind: str
    paper: str
    orientation: str
    direction: tuple


def bind(page, scene):
    native=decode_native(page);meta=parse_native(native)
    raw=native.decode('latin1').replace('\r\n','\n').replace('\r','\n')
    crop=re.findall(r'^%AI3_Cropmarks:\s*([^\n]+)',raw,re.M)
    if len(crop)!=1:raise ValueError('Repère natif Illustrator ambigu.')
    nb=list(map(float,crop[0].split()));pb=list(map(float,page.mediabox))
    if len(nb)!=4 or any(abs(x-y)>.01 for x,y in zip((nb[2]-nb[0],nb[3]-nb[1]),(pb[2]-pb[0],pb[3]-pb[1]))):
        raise ValueError('Repères Illustrator/PDF incompatibles.')
    offset=(1,0,0,1,pb[0]-nb[0],pb[1]-nb[1]);definitions={}
    for m in re.finditer(r'^%AI14_BeginSymbol\n(.*?)^%AI10_EndSymbol',raw,re.M|re.S):
        name,end=ps_string(m[1],0);definitions[name]=m[1][end:]
    symbols=[];assigned=set();native_texts={};visible={};text_blocks={}
    for layer_match in re.finditer(r'^%AI5_BeginLayer\n(.*?)^%AI5_EndLayer--',raw,re.M|re.S):
        block=layer_match[1];name=None
        for m in re.finditer(r'^\(',block,re.M):
            candidate,end=ps_string(block,m.start())
            if re.match(r'\s+Ln(?:\s|$)',block[end:]):name=candidate;break
        if name is None:raise ValueError('Nom de calque manquant.')
        flags=re.match(r'\s*((?:\d+\s+){13}\d+)\s+Lb\b',block)
        if not flags:raise ValueError('Visibilité native du calque inconnue.')
        visible[name]=bool(int(flags[1].split()[0]))
        native_texts[name]=len(re.findall(r'^/AI11Text\s*:',block,re.M))
        text_blocks[name]=block
        records=list(re.finditer(r'^/SymbolInstance\s*:\s*',block,re.M))
        for n,record in enumerate(records):
            symbol_name,end=ps_string(block,record.end())
            ref=re.match(r'\s*/SymbolRef\s*,',block[end:]);matrix=MATRIX.match(block,end+ref.end()) if ref else None
            if not matrix:raise ValueError('Matrice native de symbole absente.')
            native_matrix=tuple(map(float,matrix[1].split()));pdf_matrix=multiply(offset,native_matrix)
            limit=records[n+1].start() if n+1<len(records) else len(block)
            segment=block[end:limit];start=segment.find('%_X=');finish=segment.find('%_X+',start)
            is_marker=bool(MARKER.search(symbol_name))
            if not visible[name]:continue
            if start>=0 and finish>start:
                geom=native_geometry(segment[start:finish],offset,True)
                if not geom:raise ValueError('Apparence native de symbole vide.')
                bbox=geometry_path(geom).bounds
                candidates=[it for it in scene.items if it.kind=='path' and it.layer==name and
                            all((geometry_path(it.geometry).bounds[j]>=bbox[j]-.02 if j<2 else geometry_path(it.geometry).bounds[j]<=bbox[j]+.02) for j in range(4))]
                actual=[row for it in candidates for row in it.geometry+([('h',)] if it.operator not in ('S',) else [])]
                if not candidates or not outlines_match(geom,actual):
                    raise ValueError('Correspondance PDF incomplète pour le symbole « '+symbol_name+' ».')
            else:
                candidates=[it for it in scene.items if it.kind=='form' and it.layer==name and max(abs(a-b) for a,b in zip(it.matrix,pdf_matrix))<.002]
                if len(candidates)!=1 or symbol_name not in definitions:raise ValueError('Symbole PDF réutilisé non identifié : '+symbol_name)
                obj=scene.resources.XObject[candidates[0].resource];sub=Scene(obj)
                if any(it.kind!='path' for it in sub.items):raise ValueError('Symbole mixte non pris en charge.')
                geom=native_geometry(definitions[symbol_name])
                actual=[row for it in sub.items for row in it.geometry+ [('h',)]]
                if not outlines_match(geom,actual):raise ValueError('Définition PDF du symbole différente de la définition native.')
            ids=[it.index for it in candidates]
            if assigned.intersection(ids):raise ValueError('Deux symboles partagent des tracés PDF : association ambiguë.')
            assigned.update(ids)
            symbols.append(Symbol('symbol-'+str(len(symbols)+1),symbol_name,name,ids,union(it.bounds for it in candidates),bool(DIRECTIONAL.search(symbol_name)),is_marker))
    if len(symbols)!=sum(len(l['symbol_instances']) for l in meta['layers'] if visible.get(l['name'])):
        raise ValueError('Des symboles natifs n’ont pas été associés.')
    # Text may live on any visible plan layer, including Niveau or SIG.
    # Validate frame grouping rather than requiring a particular layer name.
    for name,count in native_texts.items():
        if not visible.get(name):continue
        fixed=re.match(r'^(fonds? de plans?|cadre|trous?|sp[ée]cimen|adresse|psi|situation|plan de masse|date|l[eé]gende)',name,re.I)
        if fixed:continue
        texts=[it for it in scene.items if it.kind=='text' and it.layer==name]
        # VEI codes are associated with their discs below and removed from the
        # generated drawing; they do not need a room-label rotation anchor.
        if texts and all(parse_label(it.text) for it in texts):continue
        if count!=len(texts) or (name.casefold().startswith('niveau') and any('\ufffd' in it.text for it in texts)):
            from .textframes import bind_text_frames
            try:bind_text_frames(raw,text_blocks[name],texts)
            except ValueError as error:raise ValueError(f'Calque « {name} » : {error}') from error
        else:
            for it in texts:it.text_anchor=center(it.bounds)
    markers=[];used=set()
    def blue(c):return c is not None and len(c)==4 and c[0]>.65 and .4<c[1]<.9 and c[2]<.2 and c[3]<.2
    labels=[it for it in scene.items if it.kind=='text' and parse_label(it.text)]
    for symbol in sorted((s for s in symbols if s.marker),key=lambda s:(-center(s.bounds)[1],center(s.bounds)[0])):
        anchor=center(symbol.bounds)
        # Manually placed stems may start slightly off-centre inside the disc.
        # Require a unique stem beginning well inside it, rather than exact
        # equality with the disc's bounding-box centre.
        inner_radius=.4*min(symbol.bounds[2]-symbol.bounds[0],symbol.bounds[3]-symbol.bounds[1])
        stems=[it for it in scene.items if it.kind=='path' and it.layer==symbol.layer and it.operator=='S' and blue(it.stroke) and
               2<=len(it.geometry)<=6 and all(row[0] in ('m','l') for row in it.geometry) and
               min(math.dist(anchor,it.geometry[0][1:]),math.dist(anchor,it.geometry[-1][1:]))<=inner_radius]
        if len(stems)!=1:raise ValueError('Tige VEI absente ou ambiguë.')
        stem=stems[0];points=[row[1:] for row in stem.geometry]
        if math.dist(anchor,points[-1])<math.dist(anchor,points[0]):points.reverse()
        direction=(points[-1][0]-points[-2][0],points[-1][1]-points[-2][1])
        heads=[it for it in scene.items if it.kind=='path' and it.layer==symbol.layer and it.operator in ('f','f*','F') and blue(it.fill)
               and math.dist(center(it.bounds),points[-1])<15]
        near=sorted(labels,key=lambda it:math.dist(center(it.bounds),anchor))
        if len(heads)!=1 or not near or math.dist(center(near[0].bounds),anchor)>65 or (len(near)>1 and math.dist(center(near[1].bounds),anchor)-math.dist(center(near[0].bounds),anchor)<8):
            raise ValueError('Pointe ou étiquette VEI absente ou ambiguë.')
        label=near[0];parsed=parse_label(label.text);ids={stem.index,heads[0].index,label.index,*symbol.items}
        if used.intersection(ids):raise ValueError('Composant partagé entre plusieurs VEI.')
        used.update(ids);index=len(markers)+1
        markers.append(Marker(f'p001-vei{labels.index(label)+1:03d}',index,symbol,stem.index,heads[0].index,label.index,parsed['type'],parsed['paper'],parsed['orientation'],direction))
    if not markers or len(markers)!=len(labels):raise ValueError('Tous les VEI du BAT ne sont pas identifiés.')
    if any(it.kind=='path' and (blue(it.stroke) and it.operator=='S' or blue(it.fill) and it.operator in ('f','f*','F')) and
           it.layer in {m.symbol.layer for m in markers} and it.index not in used and it.index not in assigned for it in scene.items):
        raise ValueError('Tracé bleu supplémentaire non associé à un VEI.')
    return symbols,markers,visible
