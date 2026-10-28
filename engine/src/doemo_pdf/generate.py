"""Linux batch generation for the verified, single-page Illustrator profile.

Outputs are test plans requiring visual review. Unsupported bindings/layouts
fail the whole batch; a ZIP is published only after every PDF has been checked.
"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import math
import os
import re
import shutil
import tempfile
import zipfile

import pikepdf
import pathops
from pypdf._codecs.core_font_metrics import CORE_FONT_METRICS

from .pdf import open_pdf, selected_page, file_hash, resources_fingerprint, digest
from .scene import Scene, I, instruction, multiply, transform_box, union
from .bindings import bind, center, geometry_path
from .geometry import Matrix, component_transform, rotation_to_up
from .batch import template_index, check_template
from .settings import templates_dir
from .levels import validate_document, level_path, pdf_path
from .template_zones import detect_zone, named as zone_name


def rotation(angle, anchor=(0,0)):
    r=math.radians(angle);c,s=math.cos(r),math.sin(r);x,y=anchor
    return (c,s,-s,c,x-c*x+s*y,y-s*x-c*y)


def fit_box(box, slot, upscale=True, align='center'):
    w,h=box[2]-box[0],box[3]-box[1]
    if min(w,h)<=0:raise ValueError('Bloc graphique sans dimensions.')
    scale=min((slot[2]-slot[0])/w,(slot[3]-slot[1])/h,math.inf if upscale else 1)
    if scale<=0:raise ValueError('Zone de placement vide.')
    x=(slot[0]+slot[2]-w*scale)/2;y=(slot[1]+slot[3]-h*scale)/2
    if align=='bottom-right':x=slot[2]-w*scale;y=slot[1]
    return (scale,0,0,scale,x-scale*box[0],y-scale*box[1])


def role(layer):
    name=(layer or '').casefold().strip()
    if re.match(r'^(fonds? de plans?|cadre|trous? de per[cç]age|sp[ée]cimen)($|[ _-])',name):return 'decoration'
    if re.match(r'^(adresse|psi|situation|plan de masse)($|[ _-])',name):return 'header'
    if name.startswith('date'):return 'footer'
    if name.startswith('niveau'):return 'level'
    if name.startswith(('logo','doemo_logo','doemo logo')):return 'logo'
    if name.startswith(('legende','légende')):return 'legend'
    return 'plan'


def batch_date():
    """One local calendar date for the whole lot, even across midnight."""
    return datetime.now(ZoneInfo(os.environ.get('DOEMO_TIMEZONE') or 'Europe/Paris')).date()


def footer_label(scene, indices, number, generated_on):
    if not indices:return None,None
    # Only publication metadata is rewritten; architectural text stays intact.
    items=[scene.items[i] for i in indices]
    if any(it.kind!='text' for it in items):
        raise ValueError('Le cartouche date du BAT contient des éléments non textuels non pris en charge.')
    value=''.join(it.text for it in sorted(items,key=lambda it:(-round(it.bounds[1]/8),it.bounds[0])))
    match=re.fullmatch(r'\s*(Mise\s+à\s+jour\s+n[°º]\s*\d+\s*-\s*Date\s+et\s+n[°º]\s*du\s+plan\s*:\s*)\d{2}-\d{2}-\d{4}\s*-\s*(.+)-\d+\s*',value)
    if not match:raise ValueError('Date et référence du plan non reconnues dans le cartouche du BAT.')
    reference=f'{match[2].strip()}-{number}'
    return f'{match[1]}{generated_on:%d-%m-%Y} - {reference}',reference


def template_scene(pdf):
    pg=selected_page(pdf,0)
    if len(pdf.pages)!=1:raise ValueError('Trame multipage non prise en charge.')
    scene=Scene(pg);box=tuple(map(float,pg.cropbox))
    defaults=pdf.Root.get('/OCProperties',{}).get('/D',{})
    off={x.objgen for x in defaults.get('/OFF',[])}
    layers={str(v.get('/Name')):v.objgen not in off for v in scene.resources.get('/Properties',{}).values()}
    zone,scene.zone_detection=detect_zone(scene,box,layers,role)
    selected=[it.index for it in scene.items if layers.get(it.layer,True) and not zone_name(it.layer) and role(it.layer) not in ('header','footer','legend')]
    return scene,box,tuple(zone),selected


def inspect_template(path):
    try:
        with open_pdf(path) as pdf:scene,box,zone,_=template_scene(pdf)
    except ValueError as error:raise ValueError(f'Trame {Path(path).name} : {error}') from error
    return {'file':Path(path).name,'sha256':file_hash(path),'page_box':list(box),'zone':list(zone),'zone_detection':scene.zone_detection}


def inspect_generation(source, client='doemo'):
    with open_pdf(source) as pdf:
        if len(pdf.pages)!=1:raise ValueError('Cet import natif prend actuellement en charge un BAT à une page. Le découpage multipage reste disponible séparément.')
        pg=selected_page(pdf,0);require_native_metadata(pg);scene=Scene(pg);symbols,markers,visible=bind(pg,scene)
        directory=templates_dir(client);index=template_index(directory);templates={}
        for marker in markers:
            key=(marker.kind,marker.paper,marker.orientation)
            if key in templates:continue
            found=index.get(key,[])
            if len(found)!=1:raise ValueError('Trame '+ '-'.join(key)+' absente ou ambiguë dans le dossier client.')
            path=found[0];sha=check_template(path,key)
            details=inspect_template(path)
            templates[key]={'reference':f'{client}/{path.relative_to(directory).as_posix()}','sha256':sha,'zone':details['zone'],'zone_detection':details['zone_detection']}
        return {'status':'ready_for_test_generation','generation_available':True,'production_ready':False,
                'source_sha256':file_hash(source),'client':client,'marker_count':len(markers),'symbol_count':len(symbols),
                'profile':'illustrator-ai24-single-page','markers':[{'id':m.id,'index':m.index,'type':m.kind,'paper':m.paper,'orientation':m.orientation,
                'direction':list(m.direction),'point':list(center(m.symbol.bounds)),'template':templates[(m.kind,m.paper,m.orientation)]['reference']} for m in markers],
                'templates':list(templates.values()),'warnings':['PDF de test : contrôle visuel requis.',
                'Zones des trames détectées automatiquement ; vérifier le placement.',
                'Les équipements des calques natifs visibles sont inclus, même si leur impression était désactivée.']}


def require_native_metadata(page):
    if page.obj.get('/PieceInfo',{}).get('/Illustrator',{}).get('/Private') is None:
        raise ValueError('Ce PDF ne contient pas les données natives Illustrator nécessaires à la génération. Importez le fichier .ai original enregistré avec compatibilité PDF.')


class Composer:
    def __init__(self,pdf,page):
        self.pdf=pdf;self.page=page;self.ops=[];page.Resources=pikepdf.Dictionary(XObject=pikepdf.Dictionary())
    def place(self,form,matrix=I):
        key=pikepdf.Name('/P'+str(len(self.page.Resources.XObject)))
        self.page.Resources.XObject[key]=form
        self.ops.extend([instruction('q'),instruction('cm',matrix),instruction('Do',[key]),instruction('Q')])
    def finish(self):self.page.Contents=self.pdf.make_stream(pikepdf.unparse_content_stream(self.ops))


def make_group(pdf,forms,indices,page_box,transforms=None,clip=None):
    xobjects=pikepdf.Dictionary();ops=[]
    if clip is not None:ops=list(pikepdf.parse_content_stream(pdf.make_stream(pdf_path(clip))))
    for i in indices:
        key=pikepdf.Name('/I'+str(i));xobjects[key]=forms[i]
        ops.extend([instruction('q'),instruction('cm',(transforms or {}).get(i,I)),instruction('Do',[key]),instruction('Q')])
    group=pdf.make_stream(pikepdf.unparse_content_stream(ops));group.Type=pikepdf.Name.XObject;group.Subtype=pikepdf.Name.Form
    group.BBox=pikepdf.Array(page_box);group.Resources=pikepdf.Dictionary(XObject=xobjects)
    return group


def build_plan(source, scene, symbols, markers, visible, marker, template_path, output, levels=None, generated_on=None):
    source_page=source.pages[0];source_box=tuple(map(float,source_page.mediabox))
    with open_pdf(template_path) as template:
        try:ts,ab,zone,template_ids=template_scene(template)
        except ValueError as error:raise ValueError(f'Trame {Path(template_path).name} : {error}') from error
        out=pikepdf.Pdf.new();page=out.add_blank_page(page_size=(ab[2]-ab[0],ab[3]-ab[1]));page.MediaBox=pikepdf.Array(ab)
        source_group=source_page.obj.get('/Group');template_group=template.pages[0].obj.get('/Group')
        separate_template_group=source_group is not None and template_group is not None and str(source_group.get('/CS'))!=str(template_group.get('/CS'))
        if separate_template_group:
            def is_cmyk(space):
                return str(space)=='/DeviceCMYK' or (isinstance(space,pikepdf.Array) and str(space[0])=='/ICCBased' and int(space[1].get('/N',0))==4)
            if not all(is_cmyk(group.get('/CS')) for group in (source_group,template_group)):
                raise ValueError('Espaces de fusion du BAT et de la trame non pris en charge.')
        if source_group is not None:page.obj.Group=out.copy_foreign(source.make_indirect(source_group))
        elif template_group is not None:page.obj.Group=out.copy_foreign(template.make_indirect(template_group))
        if source.Root.get('/OutputIntents') or template.Root.get('/OutputIntents'):raise ValueError('Profils colorimétriques de sortie non pris en charge par ce profil.')
        sf=scene.forms(source,out,source_box);tf=ts.forms(template,out,ab);writer=Composer(out,page)
        if separate_template_group:
            # Keep the template's original blending space in its own isolated
            # group, while source fragments retain the BAT's page ICC space.
            template_form=make_group(out,tf,template_ids,ab)
            template_form.Group=out.copy_foreign(template.make_indirect(template_group))
            template_form.Group.I=True
            writer.place(template_form)
        else:
            for i in template_ids:writer.place(tf[i])
        groups={k:[] for k in ['plan','header','footer','level','logo','legend','decoration']}
        for it in scene.items:
            if visible.get(it.layer,False):groups[role(it.layer)].append(it.index)
        if sum(scene.items[i].kind=='text' for i in groups['level'])>1:
            # A BAT with several level labels keeps them at their source
            # positions; collecting them in one footer would reorder levels.
            groups['plan']=sorted(groups['plan']+groups['level']);groups['level']=[]
        # Auto-detected free space can extend up to the banner. Reserve room
        # for the source address before fitting the plan, rather than letting
        # it overlap the banner or creating an inverted header slot.
        header_top=ab[3]-96
        if groups['header']:
            hb=union(scene.items[i].bounds for i in groups['header'])
            header_height=(hb[3]-hb[1])*min(1,(zone[2]-zone[0]-24)/(hb[2]-hb[0]))
            zone=(zone[0],zone[1],zone[2],min(zone[3],header_top-header_height-16))
        # The one isolated image in the footer is the client logo; a scan of the
        # building must never be guessed to be a logo or quietly discarded.
        images=[scene.items[i] for i in groups['plan'] if scene.items[i].kind=='image']
        logo=[it for it in images if it.bounds[3]<source_box[1]+.2*(source_box[3]-source_box[1]) and
              it.bounds[2]-it.bounds[0]<.35*(source_box[2]-source_box[0])]
        if images and (len(images)!=1 or len(logo)!=1):raise ValueError('Image de plan ou logo ambigu : préparation requise.')
        for it in logo:groups['plan'].remove(it.index);groups['logo'].append(it.index)
        if marker.kind=='PI' and groups['logo']:
            lb=union(scene.items[i].bounds for i in groups['logo'])
            logo_scale=min(1,.30*(ab[2]-ab[0])/(lb[2]-lb[0]),(.12*(ab[3]-ab[1])-10)/(lb[3]-lb[1]))
            zone=(zone[0],max(zone[1],ab[1]+22+(lb[3]-lb[1])*logo_scale+10),zone[2],zone[3])
        if not groups['plan']:raise ValueError('Dessin architectural absent.')
        all_labels={m.label for m in markers};hidden=set(all_labels)
        for m in markers:
            if m.id!=marker.id:hidden.update([m.stem,m.head,*m.symbol.items])
        plan=[i for i in groups['plan'] if i not in hidden]
        angle=rotation_to_up(marker.direction);turn=rotation(angle);local={}
        for symbol in symbols:
            if not symbol.directional:
                correction=rotation(-angle,center(symbol.bounds))
                for i in symbol.items:local[i]=correction
        for i in plan:
            if scene.items[i].kind=='text':local[i]=rotation(-angle,scene.items[i].text_anchor or center(scene.items[i].bounds))
        clip=None;level_id=None
        if marker.kind=='PE' and levels and levels['levels']:
            assigned=[x for x in levels['levels'] if marker.id in x.get('vei_ids',[])]
            if len(assigned)!=1:raise ValueError('Associez le VEI '+str(marker.index)+' à un niveau avant de générer le PE.')
            clip=level_path(assigned[0]);level_id=assigned[0]['id']
            if not list(clip):raise ValueError('Niveau sélectionné vide.')
            for i in [marker.stem,marker.head,*marker.symbol.items]:
                x0,y0,x1,y1=transform_box(scene.items[i].bounds,local.get(i,I))
                envelope=geometry_path([('m',x0,y0),('l',x1,y0),('l',x1,y1),('l',x0,y1),('h',)])
                outside=pathops.op(envelope,clip,pathops.PathOp.DIFFERENCE)
                if list(outside):
                    raise ValueError('Le contour ne contient pas entièrement la zone occupée par le VEI '+str(marker.index)+'. Élargissez-le pour conserver la pastille et sa flèche.')
        transformed={i:multiply(turn,local.get(i,I)) for i in plan}
        bounds=union(transform_box(scene.items[i].bounds,transformed[i]) for i in plan)
        if clip is not None:bounds=transform_box(clip.bounds,turn)
        # Reserve distinct rows for the level name, legend and order footer.
        useful=(zone[0]+12,zone[1]+12,zone[2]-12,zone[3]-12)
        unique=[];seen=set()
        for symbol in symbols:
            if symbol.marker or symbol.name in seen:continue
            seen.add(symbol.name);unique.append(symbol)
        columns=3;rows=math.ceil(len(unique)/columns);legend_height=rows*21+21
        legend_slot=(useful[0],useful[1]+14,useful[2],useful[1]+14+legend_height)
        plan_slot=(useful[0],legend_slot[3]+36,useful[2],useful[3])
        fit=fit_box(bounds,plan_slot)
        # Match the script's page-centred placement as far as the available zone permits.
        w=(bounds[2]-bounds[0])*fit[0];h=(bounds[3]-bounds[1])*fit[0]
        cx=max(plan_slot[0]+w/2,min((ab[0]+ab[2])/2,plan_slot[2]-w/2))
        cy=max(plan_slot[1]+h/2,min((ab[1]+ab[3])/2,plan_slot[3]-h/2))
        fit=(fit[0],0,0,fit[0],cx-fit[0]*center(bounds)[0],cy-fit[0]*center(bounds)[1])
        # The outer level clip is in original PDF coordinates. Compensation is
        # inside that clip; global orientation is applied to the complete group.
        group_box=union([source_box,*(transform_box(scene.items[i].bounds,local.get(i,I)) for i in plan)])
        group=make_group(out,sf,plan,group_box,local,clip)
        global_matrix=multiply(fit,turn);writer.place(group,global_matrix)
        placed=transform_box(bounds,fit)
        def block(ids,slot,upscale=False,align='center'):
            if not ids:return
            b=union(scene.items[i].bounds for i in ids);m=fit_box(b,slot,upscale,align)
            writer.place(make_group(out,sf,ids,source_box),m)
        # Header stays in the free band under the template banner.
        block(groups['header'],(useful[0],zone[3]+16,useful[2],header_top))
        block(groups['level'],(useful[0],placed[1]-30,useful[2],placed[1]-8))
        footer,reference=footer_label(scene,groups['footer'],marker.index,generated_on or batch_date())
        selfont=out.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font,Subtype=pikepdf.Name.Type1,BaseFont=pikepdf.Name.Helvetica,Encoding=pikepdf.Name.WinAnsiEncoding))
        boldfont=out.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font,Subtype=pikepdf.Name.Type1,BaseFont=pikepdf.Name('/Helvetica-Bold'),Encoding=pikepdf.Name.WinAnsiEncoding))
        page.Resources.Font=pikepdf.Dictionary(Legend=selfont,LegendBold=boldfont)
        def text(value,x,y,size,bold=False,color=None):
            writer.ops.extend([instruction('q'),instruction('k',color) if color else instruction('g',[0]),instruction('BT'),instruction('Tf',[pikepdf.Name.LegendBold if bold else pikepdf.Name.Legend,size]),
              instruction('Tm',[1,0,0,1,x,y]),instruction('Tj',[pikepdf.String(value.encode('cp1252',errors='replace'))]),instruction('ET'),instruction('Q')])
        footer_bounds=None
        if footer:
            # Standard PDF font covers all date/sequence digits, unlike the
            # source subset, which may not contain tomorrow's digits.
            widths=CORE_FONT_METRICS['Helvetica'].character_widths
            width=sum(widths.get(c,widths['default']) for c in footer)/1000
            size=min(5.5,(ab[2]-ab[0]-40)/width)
            x=(ab[0]+ab[2]-width*size)/2;y=ab[1]+8
            text(footer,x,y,size)
            footer_bounds=[x,y-size*.25,x+width*size,y+size]
        # Size columns to their labels, not to the full available page width.
        # The title sits outside the border, as in the client's legend samples.
        label_size=6.5;label_widths=CORE_FONT_METRICS['Helvetica-Bold'].character_widths
        def label_width(value):return sum(label_widths.get(c,label_widths['default']) for c in value)*label_size/1000
        labels=[]
        for symbol in unique:
            lines=['']
            for word in symbol.name.upper().split():
                candidate=(lines[-1]+' '+word).strip()
                if lines[-1] and label_width(candidate)>150:lines.append(word)
                else:lines[-1]=candidate
            labels.append(lines)
        active_columns=min(columns,max(1,len(unique)))
        widths=[24+max((label_width(line) for n,lines in enumerate(labels) if n//rows==col for line in lines),default=60)
                for col in range(active_columns)]
        gap=12;padding=4
        compact_width=sum(widths)+gap*(active_columns-1)+padding*2
        available=legend_slot[2]-legend_slot[0]
        legend_scale=min(1,available/compact_width)
        x0=(legend_slot[0]+legend_slot[2]-compact_width*legend_scale)/2
        top=legend_slot[3]-13
        row_height=max(21,max((len(lines)*8 for lines in labels),default=0))
        legend_frame=[x0,top-(max(rows,1)*row_height+padding*2)*legend_scale,x0+compact_width*legend_scale,top]
        legend_color=(1,0,1,0) if marker.kind=='PE' else (0,.99,.97,0)
        writer.ops.extend([instruction('q'),instruction('K',legend_color),instruction('w',[1.5 if marker.kind=='PE' else .75]),
                           instruction('re',[legend_frame[0],legend_frame[1],legend_frame[2]-legend_frame[0],legend_frame[3]-legend_frame[1]]),
                           instruction('S'),instruction('Q')])
        text('LEGENDE',legend_frame[0],legend_frame[3]+3,11,True,legend_color)
        for n,symbol in enumerate(unique):
            col,row=divmod(n,rows)
            x=x0+(padding+sum(widths[:col])+gap*col)*legend_scale
            y=top-(padding+16+row*row_height)*legend_scale
            symbol_group=make_group(out,sf,symbol.items,source_box)
            writer.place(symbol_group,fit_box(symbol.bounds,(x,y,x+16*legend_scale,y+16*legend_scale)))
            for k,line in enumerate(labels[n]):text(line,x+24*legend_scale,y+(5-k*8)*legend_scale,label_size*legend_scale,True)
        if groups['logo']:
            slot=(ab[2]-12-(ab[2]-ab[0])*.30,ab[1]+22,ab[2]-12,ab[1]+12+(ab[3]-ab[1])*.12)
            # Existing prevention objects set the bottom of the available space.
            bands=[ts.items[i] for i in template_ids if ts.items[i].fill is not None and len(ts.items[i].fill)==4
                   and ts.items[i].fill[0]<.4 and ts.items[i].fill[1]<.4 and ts.items[i].fill[2]>.5 and ts.items[i].fill[3]<.4
                   and ts.items[i].bounds[0]>(ab[0]+ab[2])/2 and ts.items[i].bounds[3]<(ab[1]+ab[3])/2
                   and ts.items[i].bounds[2]-ts.items[i].bounds[0]>(ab[2]-ab[0])*.1
                   and ts.items[i].bounds[3]-ts.items[i].bounds[1]<(ab[3]-ab[1])*.05]
            if marker.kind=='PE' and len(bands)==1:
                band=bands[0].bounds
                obstacles=[ts.items[i].bounds for i in template_ids if ts.items[i].bounds[2]>band[0] and ts.items[i].bounds[0]<band[2]
                           and ts.items[i].bounds[3]<band[1] and ts.items[i].bounds[1]>ab[1]+12]
                slot=(band[0],ab[1]+22,band[2],min((b[1] for b in obstacles),default=band[1])-8)
            block(groups['logo'],slot,marker.kind=='PE','center' if marker.kind=='PE' else 'bottom-right')
        writer.finish();out.docinfo['/Title']='DOEMO Studio — PDF de test — VEI '+str(marker.index)
        out.docinfo['/Subject']='Généré sur Linux depuis le BAT ; contrôle visuel requis.'
        before=[digest(f.read_bytes()) for f in sf];resources=resources_fingerprint(sf[0].Resources)
        with Path(output).open('xb') as f:out.save(f)
        with open_pdf(output) as checked:
            # Recursively verify every original paint fragment that was included.
            found=set();seen_objects=set()
            def visit(obj):
                if obj.objgen in seen_objects:return
                seen_objects.add(obj.objgen)
                if obj.get('/Subtype')==pikepdf.Name.Form:
                    found.add(digest(obj.read_bytes()))
                    for child in obj.get('/Resources',{}).get('/XObject',{}).values():visit(child)
            for obj in checked.pages[0].Resources.XObject.values():visit(obj)
            expected={before[i] for i in plan+groups['header']+groups['level']+groups['logo']}
            if not expected<=found:raise ValueError('Fragment source modifié pendant la génération.')
            # Fonts/images shared by all source fragments must survive unchanged.
            first=checked.pages[0].Resources.XObject
            all_resources=[]
            for obj in first.values():all_resources.extend(resources_fingerprint(obj))
            if not set(resources)<=set(all_resources):raise ValueError('Ressource incorporée perdue pendant la génération.')
        direction=(global_matrix[0]*marker.direction[0]+global_matrix[2]*marker.direction[1],global_matrix[1]*marker.direction[0]+global_matrix[3]*marker.direction[1])
        if abs(direction[0])>1e-7 or direction[1]<=0:raise ValueError('VEI mal orienté.')
        return {'vei':marker.index,'id':marker.id,'type':marker.kind,'file':Path(output).name,'sha256':file_hash(output),
          'angle':angle,'scale':fit[0],'direction_after':list(direction),'active_vei_count':1,'hidden_vei_count':len(markers)-1,
          'level':level_id,'plan_reference':reference,'footer_text':footer,
          'layout':{'zone':list(zone),'zone_detection':ts.zone_detection,'plan_bounds':list(placed),'legend_frame':legend_frame,'legend_color_cmyk':legend_color,'footer_bounds':footer_bounds},
          'source_fragments_unchanged':True,'publication_metadata_rewritten':bool(footer),
          'embedded_resources_unchanged':True,'production_ready':False,'status':'test_pdf_generated'}


def generate_batch(source, destination, client='doemo', levels=None, basename=None):
    destination=Path(destination)
    if destination.exists():raise ValueError('Refus d’écraser un lot existant.')
    initial=file_hash(source);directory=templates_dir(client);templates=template_index(directory);generated_on=batch_date()
    if levels is not None:levels=validate_document(source,levels)['document']
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix='.lot-',dir=destination.parent))
    published=False
    try:
        with open_pdf(source) as pdf:
            if len(pdf.pages)!=1:raise ValueError('Génération native multipage non encore prise en charge.')
            page=selected_page(pdf,0);require_native_metadata(page);scene=Scene(page);symbols,markers,visible=bind(page,scene)
            if len(markers)>100:raise ValueError('Ce profil est limité à 100 VEI par lot.')
            source_name=basename or Path(source).stem
            stem=re.sub(r'[^\w.-]+','-',source_name,flags=re.UNICODE).strip('.-')[:100] or 'plan'
            results=[];template_hashes={}
            for marker in markers:
                key=(marker.kind,marker.paper,marker.orientation);found=templates.get(key,[])
                if len(found)!=1:raise ValueError('Trame '+ '-'.join(key)+' absente ou ambiguë dans le dossier client.')
                template=found[0];template_hashes[str(template)]=check_template(template,key)
                name=f'{stem}-VEI-{marker.index:02d}-'+ '-'.join(key)+'.pdf'
                result=build_plan(pdf,scene,symbols,markers,visible,marker,template,temporary/name,levels,generated_on)
                result['template']=f'{client}/{template.relative_to(directory).as_posix()}';results.append(result)
                if sum(p.stat().st_size for p in temporary.iterdir())>256*1024*1024:raise ValueError('Lot supérieur à 256 Mio.')
        if file_hash(source)!=initial or any(file_hash(p)!=h for p,h in template_hashes.items()):raise ValueError('Une source a changé pendant la génération.')
        report={'schema_version':1,'engine_version':'0.3.4','generation_date':generated_on.isoformat(),'status':'test_batch_complete','production_ready':False,'source_sha256':initial,
                'source_unchanged':True,'client':client,'count':len(results),'results':results,
                'warnings':['Contrôler visuellement les PDF avant utilisation.',
                'Les zones de trames sont détectées automatiquement ; ce profil prend en charge les BAT Illustrator AI24 à une page.',
                'Les calques natifs visibles non imprimables sont inclus, comme dans le script 1.0.16.']}
        (temporary/'rapport.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        with zipfile.ZipFile(temporary/'plans.zip','x',zipfile.ZIP_DEFLATED) as archive:
            for result in results:archive.write(temporary/result['file'],result['file'])
            archive.write(temporary/'rapport.json','rapport.json')
        with zipfile.ZipFile(temporary/'plans.zip') as archive:
            if archive.testzip() is not None or len(archive.namelist())!=len(results)+1:raise ValueError('Archive ZIP incomplète.')
        # Reserve without replacement, then publish the completion manifest last.
        # No downloader may expose the directory before that manifest exists.
        destination.mkdir(mode=0o700)
        published=True
        for p in temporary.iterdir():
            if p.name!='rapport.json':os.rename(p,destination/p.name)
        os.rename(temporary/'rapport.json',destination/'rapport.json')
        return report
    except Exception:
        if published:shutil.rmtree(destination)
        raise
    finally:
        if temporary.exists():shutil.rmtree(temporary)
