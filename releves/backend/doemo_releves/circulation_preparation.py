"""Reviewable hints for raw Illustrator vectors; no inferred closure is applied.

Source geometry/hashes remain intact. Only roles, level masks and virtual
thresholds can be changed here. Suggestions are deliberately not ground truth.
"""
import re
import unicodedata
from typing import Literal

from pydantic import Field, model_validator
from shapely.geometry import LineString, Polygon

from . import circulations as g
from .models import Model


class Preparation(Model):
    revision:int=Field(ge=0)
    operation:Literal['roles','footprint','threshold','remove_level','remove_threshold']
    ids:list[str]=Field(default_factory=list,max_length=1000)
    role:Literal['wall','boundary','door_threshold','passage','obstacle','existing_green','unknown']='unknown'
    level_id:str=Field(default='',max_length=100)
    name:str=Field(default='',max_length=100)
    artboard:int=Field(default=0,ge=0,le=99)
    shape:g.Shape|None=None
    points:list[g.Coord]=Field(default_factory=list,max_length=2)
    replace_reviewed:bool=False

    @model_validator(mode='after')
    def points_valid(self):
        import math
        if any(not math.isfinite(v) or abs(v)>1e7 for p in self.points for v in p):raise ValueError('Coordonnées de seuil invalides')
        return self


def rgb(c):
    if not c:return None
    try:
        if c[0]=='RGBColor':return tuple(float(v)/255 for v in c[1:4])
        if c[0]=='CMYKColor':return tuple((1-float(v)/100)*(1-float(c[4])/100) for v in c[1:4])
        if c[0]=='GrayColor':return (1-float(c[1])/100,)*3
    except (ValueError,TypeError,IndexError):return None
    return None


def suggestions(source:g.Source,rules:g.Rules):
    roles=[];outlines=[];skipped=0
    scale=min(min(r-l,t-b) for l,t,r,b in source.artboards)
    for p in source.paths:
        if not p.visible or p.clipped:
            skipped+=1;continue
        name=''.join(c for c in unicodedata.normalize('NFD',p.layer.lower()) if not unicodedata.combining(c))
        pts=g.flatten(p,rules.curve_tolerance_pt);line=LineString(pts)
        if p.role=='unknown':
            color=rgb(p.fill if p.filled else p.stroke)
            dark=color is not None and len(color)==3 and max(color)<.35
            semantic=bool(re.search(r'\b(murs?|cloisons?|walls?|architecture)\b',name))
            # Thin filled shapes or long stroked paths are candidates, never facts.
            polygon=Polygon(pts) if p.closed and p.filled else None
            slender=polygon is not None and polygon.is_valid and polygon.area>0 and 2*polygon.area/max(line.length,1e-6)<scale*.02
            if semantic or (dark and line.length>scale*.12 and (not p.filled or slender)):
                roles.append(dict(id=p.id,role='wall',confidence=.7 if semantic else .4,reason='Nom du calque architectural à confirmer' if semantic else 'Tracé sombre et allongé ; peut aussi être une cote ou un symbole'))
            elif p.filled and color is not None and len(color)==3 and color[1]>color[0]+.03 and color[1]>color[2]+.03:
                roles.append(dict(id=p.id,role='existing_green',confidence=.35,reason='Remplissage vert : vérifier s’il s’agit d’une circulation existante'))
        # Real closed loops only, never replace a building by its bounding box.
        if p.closed and not p.filled:
            polygon=Polygon(pts)
            if not polygon.is_valid:continue
            for i,(l,t,r,b) in enumerate(source.artboards):
                board=Polygon([(l,b),(r,b),(r,t),(l,t)])
                if board.covers(polygon) and polygon.area>board.area*.01:
                    outlines.append(dict(id=p.id,artboard=i,area_pt2=round(polygon.area,2),reason='Contour fermé existant : confirmer le bâtiment, pas une pièce ou le cartouche'))
    return dict(roles=roles[:1000],outlines=sorted(outlines,key=lambda v:-v['area_pt2'])[:200],
                total_roles=len(roles),total_outlines=len(outlines),excluded_paths=skipped,
                automatic_changes=False)


def prepare(state,request:Preparation):
    source=g.Source.model_validate(state['source']);paths={p.id:p for p in source.paths}
    if len(set(request.ids))!=len(request.ids) or any(i not in paths for i in request.ids):raise ValueError('Sélection de tracés invalide')
    if request.operation=='roles':
        if not request.ids:raise ValueError('Sélectionner les tracés à qualifier')
        for ident in request.ids:
            p=paths[ident]
            if p.clipped:raise ValueError('Objet composé ou masqué : préparer sa géométrie dans Illustrator')
            if not p.visible:raise ValueError('Tracé masqué : le rendre exploitable dans Illustrator')
            if request.role in ('existing_green','obstacle') and not(p.closed and p.filled):raise ValueError('Contour fermé et rempli requis pour cet obstacle ou vert existant')
            if request.role=='door_threshold' and (p.closed or len(p.nodes)!=2 or any(n[:2]!=n[2:4] or n[:2]!=n[4:6] for n in p.nodes)):
                raise ValueError('Un seuil est un segment droit entre jambages, pas un arc de porte')
            p.role=request.role
    elif request.operation=='footprint':
        if not request.level_id.strip():raise ValueError('Nom de niveau requis')
        shape=request.shape
        if request.ids:
            if len(request.ids)!=1 or shape is not None:raise ValueError('Choisir un seul contour ou dessiner une emprise')
            p=paths[request.ids[0]]
            if not p.closed or p.clipped or not p.visible:raise ValueError('Contour fermé visible et sans masque requis')
            shape=g.Shape(shell=g.flatten(p,state['rules']['curve_tolerance_pt']))
        if shape is None:raise ValueError('Tracer ou choisir l’emprise réelle')
        level=g.Level(id=request.level_id,name=request.name or request.level_id,artboard=request.artboard,footprint=shape)
        source.levels=[v for v in source.levels if v.id!=level.id]+[level]
    elif request.operation=='remove_level':
        if not any(v.id==request.level_id for v in source.levels):raise ValueError('Niveau absent')
        source.levels=[v for v in source.levels if v.id!=request.level_id]
    elif request.operation=='threshold':
        if len(request.points)!=2 or LineString(request.points).length<1e-6:raise ValueError('Deux jambages distincts requis')
        level=next((v for v in source.levels if v.id==request.level_id),None)
        if not level or not g.poly(level.footprint).covers(LineString(request.points)):raise ValueError('Seuil hors emprise')
        ident='virtual-threshold-'+g.digest(sorted(request.points))[:24]
        if ident in paths:raise ValueError('Seuil déjà présent')
        source.paths.append(g.VectorPath(id=ident,role='door_threshold',nodes=[(*p,*p,*p) for p in request.points],layer='DOEMO — seuil virtuel'))
    elif request.operation=='remove_threshold':
        if not request.ids or any(not i.startswith('virtual-threshold-') or paths[i].layer!='DOEMO — seuil virtuel' for i in request.ids):raise ValueError('Seuls les seuils virtuels créés dans DOEMO peuvent être retirés')
        source.paths=[p for p in source.paths if p.id not in request.ids]
    # Re-run validation after mutations, including overlaps and artboard limits.
    result=g.reconstruct(g.Source.model_validate(source.model_dump()),g.Rules.model_validate(state['rules']))
    result['color']=state['color']
    return result
