"""DOEMO Walls: geometry from architectural evidence, independent of RTMDet.

This module accepts a *semantic raster*, never object-detection bounding boxes.
Existing native/vector and Studio Plans geometric proposals remain usable through
studio_adapter. A semantic model must be qualified separately before deployment.
No weights are bundled or downloaded. All generated geometry requires review.
"""
import math
import cv2
import numpy as np
from .geometry import wall, distance

VERSION='doemo-walls-0.2.0'
CLASSES=['background','wall','partition','door','window','stairs','text',
         'annotation','furniture','symbol','room']


def consolidate_parallel_evidence(candidates, max_separation=6., angle_degrees=1.5, min_overlap=8.):
    """Experimental scan proposal stage: thin observed traces -> one median axis.

    This is NOT semantic segmentation. Cluster only overlapping parallel traces,
    bound total transverse spread (no transitive chain across a whole room), and
    retain only extents supported by at least two distinct traces. Never union
    across an unsupported longitudinal gap. Unknown/single traces remain review
    evidence, not automatically asserted wall axes. No human edits may enter here.
    """
    if any(w['status']!='pending' or w['method']=='manual' or w['openings'] for w in candidates):
        raise ValueError('Regroupement réservé aux propositions automatiques sans ouvertures ; préserver les corrections')
    remaining=sorted(candidates,key=lambda w:-distance(w['a'],w['b']))
    axes=[];unresolved=[]
    while remaining:
        seed=remaining.pop(0);length=distance(seed['a'],seed['b'])
        origin=np.array(seed['a']);u=(np.array(seed['b'])-origin)/length;n=np.array([-u[1],u[0]])
        group=[(seed,0.,length,0.)];low_offset=high_offset=0.
        for other in remaining[:]:
            a,b=np.array(other['a'])-origin,np.array(other['b'])-origin
            direction=b-a;other_length=float(np.linalg.norm(direction))
            if abs(float(direction@n))/other_length>math.sin(math.radians(angle_degrees)):continue
            lo,hi=sorted((float(a@u),float(b@u)));offset=float(((a+b)/2)@n)
            # Opposite pixels on a single ink stroke are not two wall faces.
            if abs(offset)<.65:continue
            if max(high_offset,offset)-min(low_offset,offset)>max_separation:continue
            if max(0,min(length,hi)-max(0,lo))<min_overlap:continue
            if any(abs(offset-g[3])<.65 and min(hi,g[2])-max(lo,g[1])>min_overlap for g in group):continue
            group.append((other,lo,hi,offset));remaining.remove(other)
            low_offset,high_offset=min(low_offset,offset),max(high_offset,offset)
        if len(group)==1:
            unresolved.append(seed);continue
        # A sweep retains only jointly observed portions. Seed extents cap any extension.
        cuts=sorted({max(0.,min(length,t)) for _,lo,hi,_ in group for t in (lo,hi)})
        intervals=[]
        for lo,hi in zip(cuts,cuts[1:]):
            middle=(lo+hi)/2;support=[g for g in group if g[1]<=middle<=g[2]]
            if len(support)<2:continue
            offsets=[g[3] for g in support];median=(min(offsets)+max(offsets))/2
            thickness=max(offsets)-min(offsets)
            # Adjacent pieces merge only if median position and supported span agree.
            if intervals and abs(intervals[-1][1]-lo)<1e-8 and abs(intervals[-1][2]-median)<1e-6:
                intervals[-1]=(intervals[-1][0],hi,median,max(thickness,intervals[-1][3]))
            else:intervals.append((lo,hi,median,thickness))
        for lo,hi,median,thickness in intervals:
            if hi-lo<2:continue
            start=(origin+u*lo+n*median).tolist();end=(origin+u*hi+n*median).tolist()
            axes.append(wall(start,end,thickness,method='parallel_group_median_proposal',confidence=0.,
                evidence=[{'source_candidates':[g[0]['id'] for g in group],
                           'max_separation_document_units':max_separation,
                           'semantic_status':'unknown','review':['wall_or_window','missing_parts','junctions','openings']}]))
    return {'walls':axes,'unresolved':unresolved,'method':'geometric_proposals_only',
            'model_inference':False,'validated':False}


def thin(mask):
    """Topology preserving Zhang–Suen thinning; no dilation or gap closing."""
    z=np.pad(mask.astype(np.uint8),1)
    for _ in range(1024):
        changed=False
        for phase in (0,1):
            p=[z[:-2,1:-1],z[:-2,2:],z[1:-1,2:],z[2:,2:],
               z[2:,1:-1],z[2:,:-2],z[1:-1,:-2],z[:-2,:-2]]
            neighbors=sum(p)
            transitions=sum(((p[i]==0)&(p[(i+1)%8]==1)).astype(np.uint8) for i in range(8))
            if phase==0:
                edges=(p[0]*p[2]*p[4]==0)&(p[2]*p[4]*p[6]==0)
            else:
                edges=(p[0]*p[2]*p[6]==0)&(p[0]*p[4]*p[6]==0)
            remove=(z[1:-1,1:-1]==1)&(neighbors>=2)&(neighbors<=6)&(transitions==1)&edges
            changed |= bool(remove.any());z[1:-1,1:-1][remove]=0
        if not changed:return z[1:-1,1:-1].astype(bool)
    raise ValueError('Masque trop épais : réduction non convergente')


def skeleton_chains(skeleton):
    pixels=set(map(tuple,np.argwhere(skeleton)))
    def neighbors(p):
        y,x=p;out=[]
        for dy,dx in ((-1,0),(0,-1),(0,1),(1,0),(-1,-1),(-1,1),(1,-1),(1,1)):
            q=(y+dy,x+dx)
            if q not in pixels:continue
            # A diagonal shortcut across an existing orthogonal edge creates false triangles.
            if dy and dx and ((y+dy,x) in pixels or (y,x+dx) in pixels):continue
            out.append(q)
        return sorted(out)
    graph={p:neighbors(p) for p in pixels};visited=set();chains=[]
    def walk(a,b):
        chain=[a,b];visited.add(tuple(sorted((a,b))))
        while len(graph[b])==2:
            c=next(p for p in graph[b] if p!=a);edge=tuple(sorted((b,c)))
            if edge in visited:break
            visited.add(edge);chain.append(c);a,b=b,c
        return chain
    for a in sorted(graph,key=lambda p:(len(graph[p])==2,p)):
        for b in graph[a]:
            if tuple(sorted((a,b))) not in visited:chains.append(walk(a,b))
    return chains


def reconstruct_mask(labels, *, classes, source_sha256, model_sha256,
                     document_size, image_to_document, text_polygons=()):
    """Mask pixel centers -> document units with an explicit affine transform.

    An opening label is a hard exclusion. Unknown pixels are not wall evidence.
    OCR exclusions operate in this same raster, not guessed PDF coordinates.
    Keep every branch endpoint; simplify only within observed wall pixels.
    """
    if classes!=CLASSES or not isinstance(labels,np.ndarray) or labels.ndim!=2:
        raise ValueError('Segmentation architecturale requise ; les boîtes RTMDet ne sont pas des murs')
    if labels.size>20_000_000 or not np.issubdtype(labels.dtype,np.integer) or labels.min()<0 or labels.max()>=len(classes):
        raise ValueError('Masque invalide')
    if any(len(s)!=64 or any(c not in '0123456789abcdef' for c in s) for s in (source_sha256,model_sha256)):
        raise ValueError('Empreintes de provenance requises')
    if len(image_to_document)!=6 or not all(math.isfinite(v) for v in image_to_document):
        raise ValueError('Transformation manquante')
    a,b,c,d,e,f=image_to_document
    det=a*d-b*c
    if abs(det)<1e-12:raise ValueError('Transformation singulière')
    mask=np.isin(labels,[1,2]).astype(np.uint8)
    for polygon in text_polygons:
        pts=np.asarray(polygon,dtype=float)
        if pts.ndim!=2 or pts.shape[1]!=2 or len(pts)<3 or not np.isfinite(pts).all():
            raise ValueError('Polygone OCR invalide')
        cv2.fillPoly(mask,[np.rint(pts).astype(np.int32)],0)
    radius=cv2.distanceTransform(mask,cv2.DIST_L2,5)
    skeleton=thin(mask)
    output=[]
    def document(p):
        x,y=p;return [a*x+c*y+e,b*x+d*y+f]
    for chain_index,chain in enumerate(skeleton_chains(skeleton)):
        if len(chain)<2:continue
        raw=np.array([[x+.5,y+.5] for y,x in chain],np.float32)
        simplified=cv2.approxPolyDP(raw,.6,False)[:,0,:]
        # Verify every simplified segment remains within semantic support.
        supported=True
        for p,q in zip(simplified,simplified[1:]):
            points=np.linspace(p,q,max(2,int(distance(p,q)*3)+1))
            ix=np.clip(np.floor(points[:,0]).astype(int),0,mask.shape[1]-1)
            iy=np.clip(np.floor(points[:,1]).astype(int),0,mask.shape[0]-1)
            if not mask[iy,ix].all():supported=False;break
        if not supported:simplified=raw
        for segment_index,(p,q) in enumerate(zip(simplified,simplified[1:])):
            p,q=p.tolist(),q.tolist();start,end=document(p),document(q)
            if distance(start,end)<1e-6:continue
            if any(not 0<=v[0]<=document_size[0] or not 0<=v[1]<=document_size[1] for v in (start,end)):
                raise ValueError('Masque hors page : vérifier la transformation')
            center=(np.array(p)+q)/2;ix,iy=np.floor(center).astype(int)
            thickness=float(2*radius[iy,ix]*abs(det)*distance(p,q)/distance(start,end))
            w=wall(start,end,thickness or None,method='architectural_mask_medial_axis',confidence=0.,
                   evidence=[{'source_sha256':source_sha256,'model_sha256':model_sha256,
                              'chain':chain_index,'segment':segment_index,'image_to_document':image_to_document,
                              'review':['semantic_class','junction','opening','scan_legibility']}])
            w['kind']='partition' if labels[iy,ix]==2 else 'wall'
            output.append(w)
    return {'module':VERSION,'method':'semantic_mask_medial_axis','status':'pending',
            'walls':output,'scale':None,'model_sha256':model_sha256,
            'metrics':{'skeleton_pixels':int(skeleton.sum()),'proposed_segments':len(output),
                       'validated_walls':0,'accuracy':None}}
