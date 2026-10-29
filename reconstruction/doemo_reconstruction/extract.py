"""PDF vector recovery first; conservative raster baseline, no neural weights bundled."""
import base64
import hashlib
import io
import csv
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import pypdfium2 as pdfium
from pypdf import PdfReader
from .geometry import pair_boundaries, distance, merge_collinear_fragments, drop_page_frames
from .pdf_vectors import recover_vectors, transform
from . import semantic_walls

# Raster cleanup, as a fraction of the longest page side: fragments of one wall cut by the scan are joined when they
# lie within 0.4 % of one line and are at most 0.6 % apart (smaller than any door at the usual 1/200 to 1/50 plans).
MERGE_OFFSET_FRACTION = .004
MERGE_GAP_FRACTION = .006


def image_url(image):
    data=io.BytesIO();image.save(data,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(data.getvalue()).decode()


def pdf_transform(crop, rotation):
    x0,y0,x1,y1=map(float,crop)
    if rotation==0:
        return [1,0,0,-1,-x0,y1]
    if rotation==90:
        return [0,1,1,0,-y0,-x0]
    if rotation==180:
        return [-1,0,0,1,x1,-y0]
    if rotation==270:
        return [0,-1,-1,0,y1,x1]
    raise ValueError('Rotation PDF invalide')


def ocr_texts(image, width, height):
    if not shutil.which('tesseract'): return []
    data=io.BytesIO();image.save(data,format='PNG')
    try:
        process=subprocess.run(['tesseract','stdin','stdout','-l','eng','--psm','11','tsv'],
                               input=data.getvalue(),capture_output=True,timeout=45,check=True)
    except (subprocess.SubprocessError,OSError):
        return []
    texts=[]
    for row in csv.DictReader(io.StringIO(process.stdout.decode()),delimiter='\t'):
        if float(row['conf'])<60 or not row['text'].strip(): continue
        x,y,w,h=[int(row[k]) for k in ('left','top','width','height')]
        texts.append({'text':row['text'],'bbox':[x*width/image.width,y*height/image.height,
                      (x+w)*width/image.width,(y+h)*height/image.height],
                      'confidence':float(row['conf'])/100,'status':'pending','method':'tesseract'})
    return texts


def raster_lines(image, width, height, text_boxes=()):
    rgb=np.array(image.convert('RGB'))
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    # Exclude colored handwritten marks/symbols; black annotations remain uncertain.
    chroma=rgb.max(axis=2).astype(int)-rgb.min(axis=2).astype(int)
    gray[chroma>35]=255
    for text in text_boxes:
        x0,y0,x1,y1=text['bbox']
        cv2.rectangle(gray,(int(x0*image.width/width),int(y0*image.height/height)),
                      (int(x1*image.width/width),int(y1*image.height/height)),255,-1)
    segments=cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)[0]
    lines=[]
    if segments is not None:
        for x0,y0,x1,y1 in segments[:,0,:]:
            a=[float(x0)*width/image.width,float(y0)*height/image.height]
            b=[float(x1)*width/image.width,float(y1)*height/image.height]
            if distance(a,b)>=12:
                lines.append((a,b))
    return lines


def reconstruct(source, pages=None):
    source=Path(source)
    if source.stat().st_size>100*1024*1024:
        raise ValueError('Source supérieure à 100 Mio')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    result={'schema':'doemo.architecture/1','revision':0,'history':[],
            'source':{'name':source.name,'sha256':digest},'levels':[],
            'models':{'segmentation':'not_configured','existing_ai':'not_connected'},
            'production_ready':False}
    is_pdf=source.read_bytes()[:5]==b'%PDF-'
    pdf=pdfium.PdfDocument(source) if is_pdf else None
    reader=PdfReader(source) if is_pdf else None
    indices=pages or list(range(1,len(pdf)+1 if pdf else 2))
    if len(indices)>20 or len(set(indices))!=len(indices):
        raise ValueError('Sélection de pages invalide (maximum 20)')
    try:
        for number in indices:
            if number<1 or number>(len(pdf) if pdf else 1):
                raise ValueError('Page inexistante')
            paths,texts,native_walls=[],[],[]
            frames,fusion=0,None
            semantic,semantic_note=None,None
            has_images=False
            if pdf:
                page=pdf[number-1]
                width,height=page.get_size()
                scale=min(2.,2400/max(width,height))
                image=page.render(scale=scale).to_pil().convert('RGB')
                original_page=reader.pages[number-1]
                if float(original_page.get('/UserUnit',1))!=1:
                    raise ValueError('PDF UserUnit non standard : conversion à valider avant reconstruction')
                matrix=pdf_transform(original_page.cropbox, original_page.rotation%360)
                paths,native_walls,texts,has_images=recover_vectors(page,matrix)
                unit='pt'
                coordinate={'pdf_to_document':matrix,'cropbox':list(map(float,original_page.cropbox)),
                            'rotation':original_page.rotation,'user_unit':float(original_page.get('/UserUnit',1))}
            else:
                with Image.open(source) as im:
                    if im.width*im.height>60_000_000:
                        raise ValueError('Image supérieure à 60 mégapixels')
                    image=im.convert('RGB')
                width,height=image.size;unit='px';coordinate={'origin':'image_top_left'}
            ocr=ocr_texts(image,width,height)
            # A lone vector annotation must not hide a scanned plan. Mixed pages
            # keep both sources as pending proposals; proximity review resolves
            # possible duplicates. Pure vector pages never reinterpret excluded
            # dashed/clipped paths as continuous axes through a raster fallback.
            method='mixed' if has_images and native_walls else ('raster_baseline' if has_images or not pdf else 'vector')
            walls=list(native_walls)
            if method in ('raster_baseline','mixed'):
                semantic_sha=None
                if semantic_walls.configured():
                    semantic,semantic_sha,semantic_note=semantic_walls.propose(image,width,height,digest,ocr)
                if semantic is not None and semantic_walls.mode()=='replace':
                    walls.extend(semantic)
                    result['models']['segmentation']=semantic_sha
                else:
                    raster_walls=pair_boundaries(raster_lines(image,width,height,ocr))
                    span=max(width,height)
                    raster_walls,frames=drop_page_frames(raster_walls,width,height)
                    raster_walls,fusion=merge_collinear_fragments(raster_walls,MERGE_OFFSET_FRACTION*span,MERGE_GAP_FRACTION*span,bounds=(width,height))
                    walls.extend(raster_walls)
                    if semantic is not None:
                        walls.extend(semantic)
                        result['models']['segmentation']=semantic_sha
            # Clipped/outside geometry is retained in raw vectors but cannot be accepted as walls.
            walls=[w for w in walls if all(0<=p[0]<=width and 0<=p[1]<=height for p in (w['a'],w['b']))]
            warnings=['Valider l’étage et chaque mur : mobilier, cotes et cadres peuvent produire des candidats.',
                      'Portes, fenêtres, escaliers et pièces non reconnus par ce moteur de référence.',
                      'Aucune échelle métrique validée. Aucun passage raccordé automatiquement.']
            deferred=sum(bool(p['deferred_reason']) for p in paths)
            if deferred:
                warnings.append(f'{deferred} tracé(s) PDF conservé(s) dans la référence et les données brutes, sans axe vectoriel automatique : contrôler les murs manquants.')
            if native_walls:
                warnings.append('Les traits PDF sont des axes proposés, sans identification architecturale. Vérifier leur visibilité sur la référence et résoudre les doubles axes éventuels.')
            if fusion and fusion['output']<fusion['input']:
                warnings.append(f"Nettoyage du scan : {fusion['input']} fragments de murs rassemblés en {fusion['output']} propositions (alignés, même épaisseur, sans combler d'ouverture).")
            if frames:
                warnings.append(f"{frames} cadre(s) de feuille écarté(s) des propositions de murs.")
            if semantic is not None:
                warnings.append(f"Murs proposés par le modèle de segmentation entraîné (empreinte {result['models']['segmentation'][:12]}…) : aucun n'est validé, contrôler chacun.")
            elif semantic_note:
                warnings.append(f"Modèle de murs non utilisé ({semantic_note}) : propositions du moteur géométrique.")
            if method=='mixed':
                warnings.append('Page mixte : propositions vectorielles et raster superposées. Contrôler les doublons, les annotations et les ouvertures avant validation.')
            result['levels'].append({'id':f'page-{number}','source_page':number,
                'name':f'Page {number} — niveau à confirmer','floor_validated':False,
                'width':width,'height':height,'unit':unit,'coordinate':coordinate,'scale':None,
                'reference':image_url(image),'method':method,'raw_vectors':paths,'text_bounds_pdf':texts,
                'walls':walls,'doors':[],'windows':[],'stairs':[],'rooms':[],'texts':ocr, 'fire_equipment':[],
                'warnings':warnings})
    finally:
        if pdf: pdf.close()
    return result
