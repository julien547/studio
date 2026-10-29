"""Vector-only region reconstruction. Native AI writing belongs to Illustrator.

All coordinates are Illustrator document points, y upwards. No raster flood fill,
no inferred doorway closure, and no model-generated coordinates enter this engine.
"""
import hashlib
import json
import math
import time
import unicodedata
from typing import Literal

from pydantic import Field, model_validator
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize_full, unary_union, split
from .models import Model

VERSION='doemo.circulations/1'
Coord=tuple[float,float]


def digest(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class Shape(Model):
    shell:list[Coord]=Field(min_length=3,max_length=20000)
    holes:list[list[Coord]]=Field(default_factory=list,max_length=500)

    @model_validator(mode='after')
    def valid(self):
        if sum(len(r) for r in self.holes)>50000:raise ValueError('Trop de sommets')
        for ring in [self.shell,*self.holes]:
            if len(ring)<3 or any(not math.isfinite(v) or abs(v)>1e7 for p in ring for v in p):raise ValueError('Coordonnées invalides')
        p=Polygon(self.shell,self.holes)
        if not p.is_valid or p.area<=1e-8:raise ValueError('Contour croisé, dégénéré ou évidement invalide')
        return self


class VectorPath(Model):
    id:str=Field(min_length=1,max_length=200)
    role:Literal['wall','boundary','door_threshold','passage','obstacle','existing_green','unknown']='unknown'
    # Each node: anchor x/y, left handle x/y, right handle x/y, in document coordinates.
    nodes:list[tuple[float,float,float,float,float,float]]=Field(min_length=2,max_length=20000)
    closed:bool=False
    filled:bool=False
    stroke_width:float=Field(default=0,ge=0,le=1000)
    visible:bool=True
    clipped:bool=False
    layer:str=Field(default='',max_length=500)
    fill:list|None=None
    stroke:list|None=None

    @model_validator(mode='after')
    def finite(self):
        if any(not math.isfinite(v) or abs(v)>1e7 for node in self.nodes for v in node):raise ValueError('Coordonnées vectorielles invalides')
        if self.filled and not self.closed:raise ValueError('Un obstacle rempli doit être fermé')
        return self


class Text(Model):
    text:str=Field(max_length=4000)
    point:Coord
    level:str=Field(max_length=100)

    @model_validator(mode='after')
    def finite(self):
        if any(not math.isfinite(v) or abs(v)>1e7 for v in self.point):raise ValueError('Position de texte invalide')
        return self


class Level(Model):
    id:str=Field(min_length=1,max_length=100)
    name:str=Field(max_length=100)
    artboard:int=Field(ge=0,le=99)
    footprint:Shape


class Source(Model):
    schema_version:Literal['doemo.circulations-source/1']='doemo.circulations-source/1'
    provider:Literal['illustrator','pdf_audit']
    document_id:str=Field(min_length=1,max_length=200)
    source_name:str=Field(max_length=300)
    source_sha256:str=Field(pattern='^[0-9a-f]{64}$')
    architecture_sha256:str=Field(pattern='^[0-9a-f]{64}$')
    units:Literal['pt']='pt'
    coordinate_system:Literal['illustrator_document_y_up']='illustrator_document_y_up'
    color_space:Literal['RGB','CMYK']
    artboards:list[tuple[float,float,float,float]]=Field(min_length=1,max_length=100)
    levels:list[Level]=Field(min_length=1,max_length=100)
    paths:list[VectorPath]=Field(max_length=20000)
    texts:list[Text]=Field(default_factory=list,max_length=10000)
    inventory:dict=Field(default_factory=dict)

    @model_validator(mode='after')
    def unique(self):
        if len({p.id for p in self.paths})!=len(self.paths) or len({l.id for l in self.levels})!=len(self.levels):raise ValueError('Identifiants dupliqués')
        if sum(len(p.nodes) for p in self.paths)>200000:raise ValueError('Source trop complexe ; séparer les niveaux')
        for rect in self.artboards:
            if any(not math.isfinite(x) or abs(x)>1e7 for x in rect) or not(rect[0]<rect[2] and rect[3]<rect[1]):raise ValueError('Plan de travail invalide')
        for level in self.levels:
            if level.artboard>=len(self.artboards):raise ValueError('Plan de travail absent')
            l,t,r,b=self.artboards[level.artboard]
            if not Polygon([(l,b),(r,b),(r,t),(l,t)]).covers(poly(level.footprint)):raise ValueError('Emprise hors du plan de travail')
        for i,a in enumerate(self.levels):
            for b in self.levels[i+1:]:
                if poly(a.footprint).intersection(poly(b.footprint)).area>1e-6:raise ValueError('Niveaux superposés : séparer leurs emprises')
        return self


class Rules(Model):
    curve_tolerance_pt:float=Field(default=.1,gt=0,le=1)
    gap_tolerance_pt:float=Field(default=.25,ge=0,le=5)
    minimum_area_pt2:float=Field(default=1,gt=0,le=10000)
    confidence_threshold:float=Field(default=.95,ge=.5,le=1)
    include:list[Literal['hall','stair','landing','sas','outside']]=Field(default_factory=list)


class Color(Model):
    mode:Literal['RGB','CMYK','SPOT']
    values:list[float]=Field(default_factory=list,max_length=4)
    swatch:str=Field(default='',max_length=200)
    opacity:float=Field(default=100,gt=0,le=100)
    tint:float=Field(default=100,ge=0,le=100)
    approved:bool=False

    @model_validator(mode='after')
    def valid(self):
        if self.mode=='SPOT':
            if not self.swatch or self.values:raise ValueError('Choisir une nuance existante pour le ton direct')
        elif len(self.values)!=(3 if self.mode=='RGB' else 4) or any(not math.isfinite(x) or not 0<=x<=(255 if self.mode=='RGB' else 100) for x in self.values):raise ValueError('Composantes de couleur invalides')
        return self


def poly(shape):
    v=shape.model_dump() if isinstance(shape,Shape) else shape
    return Polygon(v['shell'],v.get('holes',[]))


def shapes(g):
    if g.is_empty:return []
    if g.geom_type=='Polygon':return [dict(shell=list(g.exterior.coords),holes=[list(r.coords) for r in g.interiors])]
    if g.geom_type in ('MultiPolygon','GeometryCollection'):return [s for p in g.geoms for s in shapes(p)]
    return []


def flatten(path,tolerance):
    points=[path.nodes[0][:2]]
    def cubic(a,b,c,d,depth=0):
        chord=LineString([a,d])
        if max(chord.distance(Point(b)),chord.distance(Point(c)))<=tolerance:
            points.append(d);return
        if depth>=20:raise ValueError('Courbe trop complexe pour la tolérance demandée')
        mid=lambda x,y:((x[0]+y[0])/2,(x[1]+y[1])/2)
        ab,bc,cd=mid(a,b),mid(b,c),mid(c,d);abc,bcd=mid(ab,bc),mid(bc,cd);m=mid(abc,bcd)
        cubic(a,ab,abc,m,depth+1);cubic(m,bcd,cd,d,depth+1)
    nodes=path.nodes
    for i in range(len(nodes) if path.closed else len(nodes)-1):
        a,b=nodes[i],nodes[(i+1)%len(nodes)]
        cubic(a[:2],a[4:6],b[2:4],b[:2])
        if len(points)>50000:raise ValueError('Trop de sommets après subdivision')
    return points


def classify(labels,rules):
    text=' '.join(labels).lower();text=''.join(c for c in unicodedata.normalize('NFD',text) if not unicodedata.combining(c))
    excluded=['bureau','reunion','classe','chambre','reserve','technique','sanitaire','vestiaire','cuisine','stockage','ascenseur','gaine','surface de vente','archives']
    circulation=any(w in text for w in ['couloir','degagement','circulation','passage commun'])
    if any(w in text for w in excluded):return ('unknown',0.,'Libellés incompatibles dans une région : vérifier les seuils') if circulation else ('room',.99,'Libellé de local exclu')
    for word,code in [('escalier','stair'),('palier','landing'),('sas','sas'),('hall','hall'),('terrasse','outside'),('exterieur','outside')]:
        if word in text:return ('circulation',.96,'Inclusion configurée : '+word) if code in rules.include else ('technical' if code in ['stair','landing'] else 'unknown',.5,'Inclusion à confirmer : '+word)
    if circulation:return 'circulation',.98,'Libellé vectoriel de circulation'
    return 'unknown',0.,'Aucun libellé suffisant ; sélection et revue requises'


def reconstruct(source:Source,rules:Rules):
    start=time.perf_counter();result=[];warnings=[];lines=[];obstacles=[];existing=[]
    for p in source.paths:
        if not p.visible or p.role=='unknown':continue
        if p.clipped:
            warnings.append('Objet masqué exclu du calcul : '+p.id);continue
        pts=flatten(p,rules.curve_tolerance_pt)
        if p.role=='passage':continue
        if p.closed and p.filled and p.role in ('wall','obstacle','existing_green'):
            g=Polygon(pts)
            if not g.is_valid:raise ValueError('Tracé rempli invalide : '+p.id)
            (existing if p.role=='existing_green' else obstacles).append(g)
        elif p.role in ('wall','boundary','door_threshold'):
            line=LineString(pts);lines.append(line)
            if p.role=='wall' and p.stroke_width:obstacles.append(line.buffer(p.stroke_width/2,cap_style='flat',join_style='mitre'))
    geometry_time=time.perf_counter();blocked=unary_union(obstacles);greens=unary_union(existing)
    for level in source.levels:
        footprint=poly(level.footprint)
        network=unary_union([footprint.boundary,*[l.intersection(footprint) for l in lines],blocked.intersection(footprint).boundary])
        faces,cuts,dangles,invalid=polygonize_full(network)
        unresolved=not cuts.is_empty or not dangles.is_empty or not invalid.is_empty
        if unresolved:warnings.append(level.id+' : limites incomplètes ; aucune fermeture arbitraire, contrôler les régions')
        for face in faces.geoms:
            if not footprint.covers(face.representative_point()):continue
            free=face.difference(blocked).difference(greens).intersection(footprint)
            for shape in shapes(free):
                g=poly(shape)
                if g.area<rules.minimum_area_pt2:continue
                labels=[t.text for t in source.texts if t.level==level.id and g.covers(Point(t.point))]
                category,confidence,reason=classify(labels,rules)
                if unresolved or not (lines or obstacles) or any(p.clipped and p.role!='unknown' for p in source.paths):
                    confidence=min(confidence,.49);reason+=' ; géométrie incomplète'
                ident=digest([level.id,g.normalize().wkb_hex])[:24]
                result.append(dict(id=ident,level=level.id,artboard=level.artboard,shape=shape,category=category,
                                   confidence=confidence,reason=reason,labels=labels,status='proposed',
                                   suggested=category=='circulation' and confidence>=rules.confidence_threshold,origin='vector_rules',original_category=category))
    if not lines and not obstacles:warnings.append('Aucune limite architecturale qualifiée : annoter les rôles des tracés avant calcul')
    if rules.gap_tolerance_pt:warnings.append('Tolérance d’inspection '+str(rules.gap_tolerance_pt)+' pt ; aucun raccord automatique de traits disjoints')
    return dict(schema_version=VERSION,source=source.model_dump(),source_version=digest(source.model_dump()),rules=rules.model_dump(),regions=result,
                color=None,warnings=warnings,revision=0,timings_ms=dict(flatten=round((geometry_time-start)*1000,2),total=round((time.perf_counter()-start)*1000,2)),
                native_ai_verified=False)


def constraints(state,g,level_id):
    source=Source.model_validate(state['source']);level=next((l for l in source.levels if l.id==level_id),None)
    if not level or not poly(level.footprint).covers(g):raise ValueError('Surface hors de l’emprise du niveau')
    for p in source.paths:
        if not p.visible or p.clipped:continue
        if p.role in ('wall','obstacle','existing_green'):
            pts=flatten(p,state['rules']['curve_tolerance_pt'])
            forbidden=Polygon(pts) if p.filled and p.closed else LineString(pts).buffer(p.stroke_width/2,cap_style='flat',join_style='mitre') if p.stroke_width else None
            if forbidden is not None and g.intersection(forbidden).area>1e-6:raise ValueError('Surface sur un mur, obstacle ou vert existant')
    return level


def edit(state,operation,ids,geometry=None,category=None):
    """All edits go through the same footprint/wall/overlap checks."""
    selected=[r for r in state['regions'] if r['id'] in ids]
    if len(selected)!=len(set(ids)):raise ValueError('Région absente')
    if operation in ('accept','reject'):
        if not selected:raise ValueError('Sélectionner une région')
        for r in selected:
            if operation=='accept':constraints(state,poly(r['shape']),r['level'])
            r.update(status='validated' if operation=='accept' else 'rejected',category='circulation' if operation=='accept' else (category or 'room'),origin='human')
        return
    if not selected:raise ValueError('Sélectionner une région du niveau')
    if len({r['level'] for r in selected})!=1:raise ValueError('Fusion entre niveaux interdite')
    old=unary_union([poly(r['shape']) for r in selected]);added=[]
    if operation=='merge':added=shapes(old)
    elif operation in ('replace','add'):
        added=[Shape.model_validate(geometry).model_dump()]
    elif operation=='hole':added=shapes(old.difference(poly(Shape.model_validate(geometry))))
    elif operation=='split':
        cutter=LineString(geometry);added=shapes(split(old,cutter))
        if len(added)<2:raise ValueError('La ligne ne sépare pas la région')
    else:raise ValueError('Opération inconnue')
    if not added:raise ValueError('La correction supprime toute la surface ; utiliser Rejeter')
    remaining=state['regions'] if operation=='add' else [r for r in state['regions'] if r['id'] not in ids]
    for shape in added:
        g=poly(shape);level=constraints(state,g,selected[0]['level'])
        if any(g.intersection(poly(r['shape'])).area>1e-6 for r in remaining if r['level']==level.id):raise ValueError('Surfaces superposées ; exclure ou ajuster la région voisine')
        remaining.append(dict(id=digest([level.id,shape,state['revision']])[:24],level=level.id,artboard=level.artboard,shape=shape,category='unknown',confidence=0.,reason='Contour corrigé à valider',labels=[],status='proposed',suggested=False,origin='human_geometry',original_category=selected[0]['category']))
    state['regions']=remaining


def export(state):
    source=Source.model_validate(state['source']);color=Color.model_validate(state['color'] or {})
    if source.provider!='illustrator':raise ValueError('Extraction native Illustrator requise ; aperçu PDF insuffisant')
    if not color.approved:raise ValueError('Nuance à valider')
    if color.mode!='SPOT' and color.mode!=source.color_space:raise ValueError('Préserver le mode colorimétrique du document')
    regions=[r for r in state['regions'] if r['status']=='validated' and r['category']=='circulation']
    if not regions:raise ValueError('Aucune circulation validée')
    for i,r in enumerate(regions):
        g=poly(r['shape']);constraints(state,g,r['level'])
        if any(g.intersection(poly(other['shape'])).area>1e-6 for other in regions[i+1:]):raise ValueError('Circulations superposées')
    return dict(schema_version='doemo.circulations-export/1',processing_version=VERSION,document_id=source.document_id,
                source_name=source.source_name,source_sha256=source.source_sha256,architecture_sha256=source.architecture_sha256,
                units=source.units,coordinate_system=source.coordinate_system,artboards=source.artboards,color_space=source.color_space,
                source_version=state['source_version'],result_version=state['revision'],color=color.model_dump(),regions=regions,
                layer='DOEMO — VERT CIRCULATIONS',native_ai_verified=False)
