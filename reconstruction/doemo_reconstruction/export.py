import copy
import html
from .geometry import axis_points, solid_intervals, validate
from .axis_review import require_reviewed_axes, review_axes, valid_reviews

LAYERS=('walls','doors','windows','stairs','rooms','texts','fire_equipment')
LABELS={'walls':'Murs','doors':'Portes','windows':'Fenêtres','stairs':'Escaliers',
        'rooms':'Pièces','texts':'Textes','fire_equipment':'Équipements incendie'}


def export_svg(level, approved_only=True):
    if approved_only:require_reviewed_axes(level)
    w,h=level['width'],level['height']
    units='pt' if level['unit']=='pt' else 'px'
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" width="{w}{units}" height="{h}{units}" viewBox="0 0 {w} {h}">']
    svg.append(f'<g id="reference" inkscape:groupmode="layer" inkscape:label="Référence" style="display:none"><image href="{html.escape(level["reference"],quote=True)}" width="{w}" height="{h}"/></g>')
    for layer in LAYERS:
        svg.append(f'<g id="{layer}" inkscape:groupmode="layer" inkscape:label="{LABELS[layer]}">')
        if layer=='walls':
            for wall in level['walls']:
                if wall['status']=='rejected' or (approved_only and wall['status']!='approved'): continue
                if wall['status']=='approved' and any(o['status']!='approved' for o in wall['openings']):
                    raise ValueError('Ouverture non validée')
                svg.append(f'<g id="wall-{html.escape(wall["id"],quote=True)}" data-status="{wall["status"]}">')
                for lo,hi in solid_intervals(wall):
                    a,b=axis_points(wall,lo,hi)
                    svg.append(f'<path d="M {a[0]:.6f} {a[1]:.6f} L {b[0]:.6f} {b[1]:.6f}" fill="none" stroke="#000000" stroke-width="{level.get("stroke_width",1.)}" stroke-linecap="butt" stroke-linejoin="miter"/>')
                svg.append('</g>')
        svg.append('</g>')
    svg.append('</svg>')
    return '\n'.join(svg)


def connector_payload(doc):
    """Reviewable transport contract. No call to an unknown localhost connector."""
    validate(doc)
    if any(not l['floor_validated'] for l in doc['levels']):
        raise ValueError('Valider l’identification des niveaux avant le transfert')
    levels=[]
    for level in doc['levels']:
        require_reviewed_axes(level)
        walls=[]
        for w in level['walls']:
            if w['status']!='approved': continue
            if any(o['status']!='approved' for o in w['openings']):
                raise ValueError('Ouverture non validée')
            walls.append({'id':w['id'],'paths':[axis_points(w,a,b) for a,b in solid_intervals(w)],
                          'detected_thickness':w['thickness']})
        if not walls:
            raise ValueError('Aucun mur validé dans un niveau')
        levels.append({'id':level['id'],'width':level['width'],'height':level['height'],
                       'unit':level['unit'],'walls':walls,'reference':level['reference'],
                       'scale':level['scale'],'stroke_width':level.get('stroke_width',1.)})
    return {'schema':'doemo.architecture.illustrator/2','source':doc['source'],
            'revision':doc['revision'],'layers':LABELS,'levels':levels,
            'status':'requires_local_connector_adapter'}


def training_records(doc):
    validate(doc)
    records={}
    unresolved={l['id']:{i for p in review_axes(l) if not p['resolved'] for i in p['wall_ids']} for l in doc['levels']}
    for entry in doc['history']:
        if entry['operation']['op']!='approve': continue
        w=next(w for w in entry['after']['walls'] if w['id']==entry['operation']['id'])
        # Do not retain labels subsequently edited/deleted without another approval.
        level=next(l for l in doc['levels'] if l['id']==entry['level_id'])
        current=next((x for x in level['walls'] if x['id']==w['id']),None)
        if current!=w: continue
        if w['id'] in unresolved[level['id']]:continue
        records[(level['id'],w['id'])]={'schema':'doemo.training.architecture/1','source':doc['source'],
                        'level_id':level['id'],'coordinate':level['coordinate'],
                        'revision':entry['revision'],'validated_by':entry['actor'],'wall':copy.deepcopy(w),
                        'axis_reviews':copy.deepcopy([r for r in valid_reviews(level) if w['id'] in r['wall_ids']])}
    return list(records.values())
