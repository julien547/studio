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
from fontTools.agl import UV2AGL, toUnicode
from fontTools.cffLib import CFFFontSet
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from pypdf._codecs import charset_encoding
from pypdf._cmap import _parse_to_unicode
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

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


def cmyk_color(space,values,resources):
    """Read CMYK equivalents for identification only; preserve PDF colour ops."""
    if isinstance(space,pikepdf.Name):
        if str(space)=='/DeviceCMYK':return tuple(map(float,values)) if len(values)==4 else None
        if str(space)=='/DeviceGray' and len(values)==1:return (0.,0.,0.,1-float(values[0]))
        if str(space)=='/DeviceRGB' and len(values)==3:
            if all(float(v)>=.999 for v in values):return (0.,0.,0.,0.)
            if all(float(v)<=.001 for v in values):return (0.,0.,0.,1.)
            return None
        space=resources.get('/ColorSpace',{}).get(space)
    if not isinstance(space,pikepdf.Array):return None
    if str(space[0])=='/ICCBased' and int(space[1].get('/N',0))==4:
        return tuple(map(float,values)) if len(values)==4 else None
    if str(space[0])=='/ICCBased' and int(space[1].get('/N',0)) in (1,3):
        return cmyk_color(pikepdf.Name.DeviceGray if int(space[1]['/N'])==1 else pikepdf.Name.DeviceRGB,values,resources)
    if str(space[0])=='/Separation' and len(values)==1:
        fn=space[3]
        if not isinstance(fn,pikepdf.Dictionary) or int(fn.get('/FunctionType',-1))!=2:return None
        c0=list(map(float,fn.get('/C0',[0])));c1=list(map(float,fn.get('/C1',[1])))
        domain=list(map(float,fn.get('/Domain',[0,1])));t=max(domain[0],min(domain[1],float(values[0])))**float(fn['/N'])
        if len(c0)!=len(c1):return None
        return cmyk_color(space[2],[a+t*(b-a) for a,b in zip(c0,c1)],resources)
    return None


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
        self.composite=str(font.get('/Subtype'))=='/Type0';self.unicode={}
        if font.get('/ToUnicode') is not None:
            data=font.ToUnicode.read_bytes()
            if len(data)>1024*1024:raise ValueError('Table Unicode de police trop volumineuse.')
            stream=DecodedStreamObject();stream.set_data(data)
            self.unicode,_=_parse_to_unicode(DictionaryObject({NameObject('/ToUnicode'):stream}))
        if self.composite:
            self._init_cid(font)
            return
        enc=font.get('/Encoding',pikepdf.Name.WinAnsiEncoding)
        base=enc.get('/BaseEncoding',pikepdf.Name.StandardEncoding) if isinstance(enc,pikepdf.Dictionary) else enc
        if str(base) not in ('/WinAnsiEncoding','/MacRomanEncoding','/StandardEncoding'):
            raise ValueError('Encodage simple de police non pris en charge : '+str(base))
        self.characters=dict(enumerate(charset_encoding[str(base)]))
        if isinstance(enc,pikepdf.Dictionary):
            at=0
            for x in enc.get('/Differences',[]):
                if isinstance(x,int):at=x
                else:self.encoding[at]=str(x)[1:];at+=1
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

    def _init_cid(self,font):
        if str(font.get('/Encoding'))!='/Identity-H':
            raise ValueError('Encodage composite de police non pris en charge : '+str(font.get('/Encoding')))
        descendants=font.get('/DescendantFonts',[])
        if len(descendants)!=1:raise ValueError('Police CID sans descendant unique.')
        cid=descendants[0];descriptor=cid.get('/FontDescriptor',{})
        if str(cid.get('/Subtype'))!='/CIDFontType2' or '/FontFile2' not in descriptor:
            raise ValueError('Identity-H requiert actuellement une police TrueType CID incorporée.')
        tt=TTFont(BytesIO(descriptor.FontFile2.read_bytes()));self.glyphs=tt.getGlyphSet()
        self.glyph_order=tt.getGlyphOrder();self.scale=1000/tt['head'].unitsPerEm
        mapping=cid.get('/CIDToGIDMap',pikepdf.Name.Identity)
        self.cid_to_gid=None
        if isinstance(mapping,pikepdf.Stream):
            self.cid_to_gid=mapping.read_bytes()
            if len(self.cid_to_gid)>131072 or len(self.cid_to_gid)%2:raise ValueError('Table CIDToGIDMap invalide.')
        elif str(mapping)!='/Identity':raise ValueError('Table CIDToGIDMap non prise en charge.')
        self.default_width=float(cid.get('/DW',1000));self.cid_widths={}
        values=list(cid.get('/W',[]));at=0
        while at<len(values):
            start=int(values[at]);entry=values[at+1];at+=2
            if isinstance(entry,pikepdf.Array):widths=list(map(float,entry));end=start+len(widths)-1
            else:
                end=int(entry)
                if not 0<=start<=end<=65535:raise ValueError('Plage de largeurs CID invalide.')
                widths=[float(values[at])]*(end-start+1);at+=1
            if start<0 or end>65535:raise ValueError('Plage de largeurs CID invalide.')
            self.cid_widths.update(zip(range(start,end+1),widths))

    def codes(self,raw):
        if not self.composite:return list(raw)
        if len(raw)%2:raise ValueError('Texte Identity-H tronqué : code CID incomplet.')
        return [int.from_bytes(raw[i:i+2],'big') for i in range(0,len(raw),2)]

    def decode(self,raw):
        chars=[]
        for code in self.codes(raw):
            char=self.unicode.get(chr(code))
            if char is None and not self.composite:
                char=toUnicode(self.encoding[code]) if code in self.encoding else self.characters.get(code,'')
            chars.append(char or '\ufffd')
        return ''.join(chars)

    def glyph(self, code):
        if code in self.cache:return self.cache[code]
        if self.composite:
            gid=code if self.cid_to_gid is None else int.from_bytes(self.cid_to_gid[code*2:code*2+2],'big')
            if gid>=len(self.glyph_order):raise ValueError('Indice de glyphe CID hors de la police incorporée.')
            name=self.glyph_order[gid];width=self.cid_widths.get(code,self.default_width)
        else:
            char=self.characters.get(code,'\0')
            name=self.encoding.get(code, getattr(self,'cmap',{}).get(ord(char), UV2AGL.get(ord(char),'.notdef')))
            index=code-self.first
            if not 0<=index<len(self.widths):raise ValueError('Largeur de glyphe absente.')
            width=self.widths[index]
        if name not in self.glyphs:raise ValueError('Glyphe incorporé introuvable : '+name)
        pen=BoundsPen(self.glyphs);self.glyphs[name].draw(pen)
        b=tuple(v*self.scale for v in pen.bounds) if pen.bounds else None
        self.cache[code]=(b,width);return self.cache[code]

    def measure(self, operands, state):
        x=0.;boxes=[]; size=state['size'];scale=state['Tz']/100
        for value in operands:
            if not isinstance(value,pikepdf.String): x-=float(value)*size/1000;continue
            for code in self.codes(bytes(value)):
                b,w=self.glyph(code)
                if b:boxes.append((x+b[0]*size/1000,b[1]*size/1000+state['Ts'],x+b[2]*size/1000,b[3]*size/1000+state['Ts']))
                x+=w*size/1000+state['Tc']+(state['Tw'] if code==32 and not self.composite else 0)
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
    glyph_ids: tuple = ()
    text_anchor: tuple | None = None


class Scene:
    def __init__(self, container):
        self.resources=container.obj.Resources if isinstance(container,pikepdf.Page) else container.Resources
        self.ops=list(pikepdf.parse_content_stream(container));self.items=[];self.fonts={};self.guides=[]
        if len(self.ops)>200000:raise ValueError('Document trop complexe pour cet import.')
        self._parse()

    def _parse(self):
        history=[];stack=[];layer=None;marks=[];path=[];clip=None;tm=lm=I;in_text=False
        state={'ctm':I,'width':1.,'cap':0,'join':0,'miter':10.,'stroke':None,'fill':None,'clip_bounds':None,
               'stroke_space':pikepdf.Name.DeviceGray,'fill_space':pikepdf.Name.DeviceGray,
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
                elif op in ('K','k','G','g','RG','rg'):
                    key='stroke' if op.isupper() else 'fill'
                    state[key+'_space']=pikepdf.Name('/'+{'K':'DeviceCMYK','G':'DeviceGray','RG':'DeviceRGB'}[op.upper()])
                    state[key]=cmyk_color(state[key+'_space'],v,self.resources)
                elif op in ('CS','cs'):
                    key='stroke' if op=='CS' else 'fill';state[key+'_space']=v[0];state[key]=None
                elif op in ('SC','SCN','sc','scn'):
                    key='stroke' if op.isupper() else 'fill';state[key]=cmyk_color(state[key+'_space'],v,self.resources)
                elif op in ('w','J','j','M'):state[{'w':'width','J':'cap','j':'join','M':'miter'}[op]]=float(v[0])
            elif op in PATH:path.append(ins)
            elif op in ('W','W*'):clip=ins
            elif op in PAINT or op=='n':
                if op=='n' and path and clip is None:
                    shape,_=path_geometry(path,state['ctm'])
                    self.guides.append({'layer':layer,'bounds':tuple(shape.bounds)})
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
                font=self.fonts[name]
                glyph_names=[font.encoding.get(code,'') for code in font.codes(raw)]
                glyph_ids=tuple(int(n[3:]) for n in glyph_names) if glyph_names and all(n.startswith('gid') and n[3:].isdigit() for n in glyph_names) else ()
                emit('text',commands,transform_box(box,multiply(state['ctm'],tm)),text=font.decode(raw),matrix=multiply(state['ctm'],tm),operator=op,glyph_ids=glyph_ids)
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
