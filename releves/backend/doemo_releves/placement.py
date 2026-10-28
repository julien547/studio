"""Connect observed equipment to approved library assets without inventing anchors."""
import re
import unicodedata
from .models import Mapping, Point


def key(text):
    value=unicodedata.normalize('NFKD',unicodedata.normalize('NFKC',text)).casefold()
    return re.sub(r'[^a-z0-9]+',' ',''.join(c for c in value if not unicodedata.combining(c))).strip()


def business_type(text):
    if "?" in text:return None
    value=key(text)
    if value in ('pcf','porte coupe feu','portes coupe feu'):return 'PCF'
    if value in ('vei','vous etes ici','pe','plan evacuation','plan d evacuation'):return 'VEI'
    if re.fullmatch(r'(?:ext|extincteur|extincteur portatif|h2o|co2|ep|ep6|abc|ab)(?: (?:eau|poudre|co2|h2o|abc|portatif|[0-9]+|[0-9]+l|[0-9]+kg|l|kg))*',value):return 'EXT_PORTATIF'
    return None


def prepare(state,library,catalogue,document_id,page):
    assets={a['id']:a for a in (library or {}).get('assets',[])} if (library or {}).get('archive_verified') else {}
    entries=[c for c in catalogue if c.get('active')]
    original=state.model_dump()
    prior=[m.model_dump() for m in state.mappings]
    for a in state.annotations:
        if (a.source_document_id,a.source_page)!=(document_id,page) or a.status in ('confirmed','rejected'):continue
        before=a.model_dump()
        exact=[m for m in state.mappings if m.confirmed and key(m.annotation)==key(a.text)]
        pairs={(m.equipment_type,m.asset_id) for m in exact}
        # Conflicting project rules remain unresolved, never choose by ordering.
        if len(pairs)>1:continue
        matched=exact[0] if exact else None
        inferred=business_type(a.equipment_type) or business_type(a.text)
        if not inferred and "?" not in (a.equipment_type or a.text):
            candidates={c['code'] for c in entries if any(key(v)==key(a.equipment_type or a.text) for v in [c['code'],c['name'],*c.get('synonyms',[])])}
            inferred=next(iter(candidates)) if len(candidates)==1 else None
        if not a.equipment_type:
            a.equipment_type=(inferred or (matched.equipment_type if matched else ''))
        # Normalize known business variants; never use colour or COCO labels.
        canonical=business_type(a.equipment_type)
        if canonical and not a.review.equipment and not a.asset_id:a.equipment_type=canonical
        suggested=None
        if matched and matched.equipment_type==a.equipment_type:suggested=matched.asset_id
        if not suggested:
            candidates={c.get('asset_id') for c in entries if c['code']==a.equipment_type and c.get('asset_id')}
            if len(candidates)==1:suggested=next(iter(candidates))
        if not suggested:
            named=[v['id'] for v in assets.values() if business_type(v.get('name',''))==a.equipment_type and a.equipment_type
                   and all(v.get(k) for k in ('verified','approved','pictogram_candidate'))]
            if len(named)==1:suggested=named[0]
        asset=assets.get(suggested)
        if not a.asset_id and asset and all(asset.get(k) for k in ('verified','approved','pictogram_candidate')):
            # An explicitly recognisable PCF/VEI/extinguisher cannot be swapped.
            named=business_type(asset.get('name',''))
            if not named or named==a.equipment_type:a.asset_id=asset['id']
        if not a.floor_id:
            point=a.anchor or Point(x=a.bbox.x+a.bbox.w/2,y=a.bbox.y+a.bbox.h/2)
            floors=[f for f in state.floors if (f.source_document_id,f.source_page)==(document_id,page) and f.source_region
                    and f.source_region.x<=point.x<=f.source_region.x+f.source_region.w and f.source_region.y<=point.y<=f.source_region.y+f.source_region.h]
            if len(floors)==1:a.floor_id=floors[0].id
        if a.asset_id and a.equipment_type and not any(m.equipment_type==a.equipment_type and m.asset_id==a.asset_id for m in state.mappings):
            state.mappings.append(Mapping(annotation=a.text.strip()[:200] or a.equipment_type,equipment_type=a.equipment_type,asset_id=a.asset_id))
        if before['equipment_type']!=a.equipment_type:a.review.equipment=False
        if before['asset_id']!=a.asset_id:a.review.asset=False
        if before['floor_id']!=a.floor_id:a.review.floor=False
        if a.model_dump()!=before:a.training_accepted=False
        a.status='uncertain_position' if not a.anchor else 'missing_asset' if not a.asset_id else 'review'
    if prior!=[m.model_dump() for m in state.mappings]:state.mapping_version+=1
    if state.model_dump()!=original:state.workflow='review'
    return state


def summary(state,library,document_id=None,page=None):
    assets={a['id']:a for a in (library or {}).get('assets',[])} if (library or {}).get('archive_verified') else {};rows=[]
    for a in state.annotations:
        if a.status=='rejected' or (document_id and (a.source_document_id,a.source_page)!=(document_id,page)):continue
        asset=assets.get(a.asset_id);issues=[]
        if not a.equipment_type:issues.append('Équipement à identifier')
        if not asset or not all(asset.get(k) for k in ('verified','approved','pictogram_candidate')):issues.append('Pictogramme SAI approuvé à associer')
        if not a.anchor:issues.append('Position réelle à pointer')
        if not a.floor_id:issues.append('Niveau à attribuer')
        if not any(m.confirmed and m.asset_id==a.asset_id and m.equipment_type==a.equipment_type for m in state.mappings):issues.append('Correspondance métier à confirmer')
        if a.status!='confirmed':issues.append('Placement à vérifier')
        rows.append({'id':a.id,'text':a.text,'equipment_type':a.equipment_type,'asset_id':a.asset_id,'preview_ready':bool(a.anchor and asset and asset.get('preview') and asset.get('approved') and asset.get('verified') and asset.get('pictogram_candidate')),'issues':issues})
    return {'annotations':rows,'preview_ready':sum(r['preview_ready'] for r in rows),'unresolved':sum(bool(r['issues']) for r in rows)}
