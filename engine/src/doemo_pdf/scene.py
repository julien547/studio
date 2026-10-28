"""Separate PDF paint operations while retaining their original operators/resources.

Strict importer for the simple Illustrator PDF profile. It never renders a plan
into pixels. Unsupported PDF constructs are rejected, not silently dropped.
"""
from dataclasses import dataclass, field
from io import BytesIO
import copy
import math

import pathops
import pikepdf
from fontTools.agl import UV2AGL
from fontTools.cffLib import CFFFontSet
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

I = (1., 0., 0., 1., 0., 0.)
PATH = {'m', 'l', 'c', 'v', 'y', 're', 'h'}
PAINT = {'S', 's', 'f', 'F', 'f*', 'B', 'B*', 'b', 'b*'}
GRAPHICS = {'cm', 'w', 'J', 'j', 'M', 'd', 'ri', 'i', 'gs', 'CS', 'cs', 'SC', 'SCN', 'sc', 'scn', 'G', 'g', 'RG', 'rg', 'K', 'k'}
TEXT = {'Tf', 'Tc', 'Tw', 'Tz', 'TL', 'Tr', 'Ts'}


def multiply(a, b):
    """a(b(point)), including reflected native/Form matrices."""
    return (a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
            a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3],
            a[0]*b[4]+a[2]*b[5]+a[4], a[1]*b[4]+a[3]*b[5]+a[5])


def point(m, p):
    x, y = p
    return (m[0]*x+m[2]*y+m[4], m[1]*x+m[3]*y+m[5])


def instruction(op, args=()):
    return pikepdf.ContentStreamInstruction(list(args), pikepdf.Operator(op))


def union(boxes):
    boxes = list(boxes)
    if not boxes: raise ValueError('Ensemble graphique vide.')
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def transform_box(box, m):
    a,b,c,d=box
    pts=[point(m,p) for p in [(a,b),(a,d),(c,b),(c,d)]]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def path_geometry(commands, ctm=I):
    """Normalize path syntax for inspection, never substitute it in PDF output."""
    path = pathops.Path(); geometry=[]; last=None
    for ins in commands:
        op=str(ins.operator); v=list(map(float,ins.operands))
        pts=[point(ctm,v[i:i+2]) for i in range(0,len(v),2)] if op!='re' else []
        if op=='m': path.moveTo(*pts[0]);geometry.append(('m',*pts[0]));last=pts[0]
        elif op=='l': path.lineTo(*pts[0]);geometry.append(('l',*pts[0]));last=pts[0]
        elif op in ('c','v','y'):
            if last is None: raise ValueError('Courbe sans origine.')
            if op=='v':pts=[last,*pts]
            if op=='y':pts=[*pts,pts[-1]]
            path.cubicTo(*(x for p in pts for x in p));geometry.append(('c',*(x for p in pts for x in p)));last=pts[-1]
        elif op=='h': path.close();geometry.append(('h',))
        elif op=='re':
            x,y,w,h=v;pts=[point(ctm,p) for p in [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]]
            path.moveTo(*pts[0]);geometry.append(('m',*pts[0]))
            for p in pts[1:]:path.lineTo(*p);geometry.append(('l',*p))
            path.close();geometry.append(('h',));last=pts[0]
    return path, geometry


class FontMetrics:
    def __init__(self, font):
        self.font=font; self.cache={};self.encoding={};self.scale=1.
        enc=font.get('/Encoding',pikepdf.Name.WinAnsiEncoding)
        if isinstance(enc,pikepdf.Dictionary):
            if enc.get('/BaseEncoding',pikepdf.Name.WinAnsiEncoding)!=pikepdf.Name.WinAnsiEncoding:
                raise ValueError('Encodage de police non pris en charge.')
            at=0
            for x in enc.get('/Differences',[]):
                if isinstance(x,int):at=x
                else:self.encoding[at]=str(x)[1:];at+=1
        elif str(enc)!='/WinAnsiEncoding': raise ValueError('Encodage de police non pris en charge.')
        descriptor=font.get('/FontDescriptor',{})
        if '/FontFile3' in descriptor and str(descriptor['/FontFile3'].get('/Subtype'))=='/Type1C':
            cff=CFFFontSet();cff.decompile(BytesIO(descriptor['/FontFile3'].read_bytes()),None)
            top=cff.topDictIndex[0]
            if list(top.FontMatrix)!=[.001,0,0,.001,0,0]:raise ValueError('Matrice de police CFF non prise en charge.')
            self.glyphs=top.CharStrings
        elif '/FontFile2' in descriptor:
            tt=TTFont(BytesIO(descriptor['/FontFile2'].read_bytes()));self.glyphs=tt.getGlyphSet();self.scale=1000/tt['head'].unitsPerEm
            self.cmap=tt.getBestCmap()
        else:raise ValueError('Police incorporée requise pour mesurer les textes sans les reconstruire.')
        self.first=int(font.get('/FirstChar',0));self.widths=list(map(float,font.get('/Widths',[])))
        if not self.widths:raise ValueError('Largeurs de police absentes.')

    def glyph(self, code):
        if code in self.cache:return self.cache[code]
        try: char=bytes([code]).decode('cp1252')
        except UnicodeDecodeError:char='\0'
        name=self.encoding.get(code, getattr(self,'cmap',{}).get(ord(char), UV2AGL.get(ord(char),'.notdef')))
        if name not in self.glyphs:raise ValueError('Glyphe incorporé introuvable : '+name)
        pen=BoundsPen(self.glyphs);self.glyphs[name].draw(pen)
        b=tuple(v*self.scale for v in pen.bounds) if pen.bounds else None
        index=code-self.first
        if not 0<=index<len(self.widths):raise ValueError('Largeur de glyphe absente.')
        self.cache[code]=(b,self.widths[index]);return self.cache[code]

    def measure(self, operands, state):
        x=0.;boxes=[]; size=state['size'];scale=state['Tz']/100
        for value in operands:
            if not isinstance(value,pikepdf.String): x-=float(value)*size/1000;continue
            for code in bytes(value):
                b,w=self.glyph(code)
                if b:boxes.append((x+b[0]*size/1000,b[1]*size/1000+state['Ts'],x+b[2]*size/1000,b[3]*size/1000+state['Ts']))
                x+=w*size/1000+state['Tc']+(state['Tw'] if code==32 else 0)
        box=union(boxes) if boxes else (0,0,0,0)
        return (box[0]*scale,box[1],box[2]*scale,box[3]),x*scale


@dataclass
class Paint:
    index: int
    layer: str | None
    kind: str
    stream: bytes
    bounds: tuple
    geometry: list = field(default_factory=list)
    stroke: tuple | None = None
    fill: tuple | None = None
    operator: str = ''
    text: str = ''
    matrix: tuple = I
    resource: str | None = None


class Scene:
    def __init__(self, container):
        self.resources=container.obj.Resources if isinstance(container,pikepdf.Page) else container.Resources
        self.ops=list(pikepdf.parse_content_stream(container));self.items=[];self.fonts={}
        if len(self.ops)>200000:raise ValueError('Document trop complexe pour cet import.')
        self._parse()

    def _parse(self):
        history=[];stack=[];layer=None;marks=[];path=[];clip=None;tm=lm=I;in_text=False
        state={'ctm':I,'width':1.,'cap':0,'join':0,'miter':10.,'stroke':None,'fill':None,'clip_bounds':None,
               'font':None,'size':0.,'Tc':0.,'Tw':0.,'Tz':100.,'TL':0.,'Tr':0.,'Ts':0.}
        def emit(kind, commands, bounds, **kwargs):
            if state['clip_bounds'] is not None:
                cb=state['clip_bounds']
                bounds=(max(bounds[0],cb[0]),max(bounds[1],cb[1]),min(bounds[2],cb[2]),min(bounds[3],cb[3]))
                if bounds[0]>bounds[2] or bounds[1]>bounds[3]:
                    raise ValueError('Objet entièrement hors de son masque : import non pris en charge.')
            stream=pikepdf.unparse_content_stream([instruction('q'),*history,*commands,instruction('Q')])
            self.items.append(Paint(len(self.items),layer,kind,stream,tuple(bounds),**kwargs))
        for ins in self.ops:
            op=str(ins.operator);v=ins.operands
            if op=='q':stack.append((list(history),copy.copy(state)))
            elif op=='Q':
                if not stack:raise ValueError('Pile graphique PDF déséquilibrée.')
                history,state=stack.pop()
            elif op=='BDC':
                if str(v[0])!='/OC' or str(v[1]) not in self.resources.get('/Properties',{}):
                    raise ValueError('Contenu marqué PDF non pris en charge.')
                marks.append(layer);layer=str(self.resources.Properties[v[1]].get('/Name',''))
            elif op=='EMC':
                if not marks:raise ValueError('Calques PDF déséquilibrés.')
                layer=marks.pop()
            elif op in GRAPHICS:
                if path:raise ValueError('Changement graphique au milieu d’un tracé non pris en charge.')
                history.append(ins)
                if op=='cm':state['ctm']=multiply(state['ctm'],tuple(map(float,v)))
                elif op in ('K','k'):state['stroke' if op=='K' else 'fill']=tuple(map(float,v))
                elif op in ('G','RG','CS','SC','SCN'):state['stroke']=None
                elif op in ('g','rg','cs','sc','scn'):state['fill']=None
                elif op in ('w','J','j','M'):state[{'w':'width','J':'cap','j':'join','M':'miter'}[op]]=float(v[0])
            elif op in PATH:path.append(ins)
            elif op in ('W','W*'):clip=ins
            elif op in PAINT or op=='n':
                if op!='n':
                    shape,geometry=path_geometry(path,state['ctm'])
                    if op in ('S','s','B','B*','b','b*'):
                        if op in ('s','b','b*'):shape.close()
                        ctm=state['ctm'];sx=math.hypot(ctm[0],ctm[1]);sy=math.hypot(ctm[2],ctm[3])
                        if abs(sx-sy)>.0001 or abs(ctm[0]*ctm[2]+ctm[1]*ctm[3])>.0001:raise ValueError('Trait déformé non pris en charge.')
                        stroke=pathops.Path(shape)
                        stroke.stroke(state['width']*sx,[pathops.LineCap.BUTT_CAP,pathops.LineCap.ROUND_CAP,pathops.LineCap.SQUARE_CAP][int(state['cap'])],
                                      [pathops.LineJoin.MITER_JOIN,pathops.LineJoin.ROUND_JOIN,pathops.LineJoin.BEVEL_JOIN][int(state['join'])],state['miter'])
                        bounds=union([shape.bounds,stroke.bounds])
                    else:bounds=shape.bounds
                    emit('path',[*path,*([clip] if clip else []),ins],bounds,geometry=geometry,stroke=state['stroke'],fill=state['fill'],operator=op)
                if clip:
                    cb=path_geometry(path,state['ctm'])[0].bounds
                    old=state['clip_bounds']
                    state['clip_bounds']=cb if old is None else (max(cb[0],old[0]),max(cb[1],old[1]),min(cb[2],old[2]),min(cb[3],old[3]))
                    history.extend([*path,clip,instruction('n')])
                path=[];clip=None
            elif op=='Do':
                obj=self.resources.XObject[v[0]];kind=str(obj.get('/Subtype'))
                if kind not in ('/Image','/Form'):raise ValueError('XObject non pris en charge.')
                m=multiply(state['ctm'],tuple(map(float,obj.get('/Matrix',I))))
                box=list(map(float,obj.get('/BBox',[0,0,1,1])))
                emit('form' if kind=='/Form' else 'image',[ins],transform_box(box,m),matrix=m,resource=str(v[0]))
            elif op=='BT':
                if in_text:raise ValueError('Objets texte imbriqués.')
                in_text=True;tm=lm=I
            elif op=='ET':in_text=False
            elif op in TEXT:
                if op=='Tf':state['font']=str(v[0]);state['size']=float(v[1])
                else:state[op]=float(v[0])
                if state['Tr']!=0:raise ValueError('Texte de découpage ou en contour non pris en charge.')
            elif op=='Tm':tm=lm=tuple(map(float,v))
            elif op in ('Td','TD','T*'):
                dx,dy=(0,-state['TL']) if op=='T*' else tuple(map(float,v))
                if op=='TD':state['TL']=-dy
                lm=multiply(lm,(1,0,0,1,dx,dy));tm=lm
            elif op in ('Tj','TJ'):
                if not in_text or not state['font']:raise ValueError('Texte PDF sans état complet.')
                name=state['font']
                if name not in self.fonts:self.fonts[name]=FontMetrics(self.resources.Font[name])
                values=v if op=='Tj' else v[0]
                box,advance=self.fonts[name].measure(values,state)
                commands=[instruction('BT'),instruction('Tf',[pikepdf.Name(name),state['size']])]
                commands.extend(instruction(k,[state[k]]) for k in sorted(TEXT) if k!='Tf')
                commands.extend([instruction('Tm',tm),ins,instruction('ET')])
                raw=b''.join(bytes(x) for x in values if isinstance(x,pikepdf.String))
                emit('text',commands,transform_box(box,multiply(state['ctm'],tm)),text=raw.decode('cp1252',errors='replace'),matrix=multiply(state['ctm'],tm),operator=op)
                tm=multiply(tm,(1,0,0,1,advance,0))
            else:raise ValueError('Opérateur PDF non pris en charge : '+op)
        if stack or marks or path or in_text:raise ValueError('Flux PDF incomplet.')

    def forms(self, source, destination, page_box):
        resources=destination.copy_foreign(source.make_indirect(self.resources))
        forms=[]
        for item in self.items:
            form=destination.make_stream(item.stream)
            form.Type=pikepdf.Name.XObject;form.Subtype=pikepdf.Name.Form
            form.BBox=pikepdf.Array(page_box);form.Resources=resources
            forms.append(form)
        return forms
