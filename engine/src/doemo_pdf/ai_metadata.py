"""Read-only Illustrator roundtrip metadata, not an Illustrator interpreter.

Only the observed AI24 Zstandard container and explicit SymbolInstance records
are supported. No PostScript/JavaScript is evaluated or used as executable code.
Names and matrices are evidence for matching PDF objects, not proof of a match.
"""

from collections import Counter
import hashlib
import math
import re

import zstandard

from .pdf import file_hash, open_pdf

MAX_NATIVE = 64*1024*1024
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
MATRIX = re.compile(r"\s*((?:"+NUMBER+r"\s+){5}"+NUMBER+r")\s+/RTransformMatrix\s*;")
PREFIX = b"%AI24_ZStandard_Data"


def ps_string(text, offset):
    """Read one balanced PostScript literal; decode escapes, never evaluate it."""
    if offset >= len(text) or text[offset] != '(':
        raise ValueError("Chaîne Illustrator attendue.")
    depth = 1; output = []; i = offset+1
    while i < len(text) and depth:
        ch = text[i]; i += 1
        if ch == '\\':
            if i == len(text):
                raise ValueError("Échappement Illustrator tronqué.")
            ch = text[i]; i += 1
            if ch in '01234567':
                digits = ch
                while i < len(text) and len(digits) < 3 and text[i] in '01234567':
                    digits += text[i]; i += 1
                output.append(chr(int(digits,8)))
            elif ch in '\r\n':
                if ch=='\r' and i<len(text) and text[i]=='\n': i+=1
            else: output.append({'n':'\n','r':'\r','t':'\t','b':'\b','f':'\f'}.get(ch,ch))
        elif ch == '(':
            depth += 1; output.append(ch)
        elif ch == ')':
            depth -= 1
            if depth: output.append(ch)
        else: output.append(ch)
    if depth:
        raise ValueError("Chaîne Illustrator non terminée.")
    # Raw content is decoded losslessly as Latin-1; individual names are UTF-8.
    raw=''.join(output).encode('latin-1')
    return raw.decode('utf-8'),i


def parse_native(data):
    if len(data)>MAX_NATIVE:
        raise ValueError("Données Illustrator décompressées trop volumineuses.")
    text=data.decode('latin-1')
    layers=[]
    layer_pattern=re.compile(r"^%AI5_BeginLayer\s*\n(.*?)^%AI5_EndLayer--",re.S|re.M)
    normalized=text.replace('\r\n','\n').replace('\r','\n')
    # The subset currently supports top-level layer records as observed in the
    # supplied AI. Nested or incomplete records must not be silently accepted.
    starts=len(re.findall(r'^%AI5_BeginLayer\s*$',normalized,re.M))
    records=list(layer_pattern.finditer(normalized))
    if len(records)!=starts:
        raise ValueError("Hiérarchie de calques Illustrator non prise en charge.")
    for record in records:
        block=record[1]
        if re.search(r'^%AI5_BeginLayer',block,re.M):
            raise ValueError("Calques Illustrator imbriqués : import non validé.")
        name=None
        for match in re.finditer(r'^\(',block,re.M):
            candidate,end=ps_string(block,match.start())
            if re.match(r'\s+Ln(?:\s|$)',block[end:]):name=candidate;break
        if name is None:
            raise ValueError("Nom de calque Illustrator introuvable.")
        instances=[]
        for match in re.finditer(r'^/SymbolInstance\s*:\s*',block,re.M):
            symbol,end=ps_string(block,match.end())
            ref=re.match(r'\s*/SymbolRef\s*,',block[end:])
            if not ref:
                raise ValueError("Référence de symbole Illustrator non prise en charge.")
            matrix=MATRIX.match(block,end+ref.end())
            if not matrix:
                raise ValueError("Matrice de symbole Illustrator absente ou non prise en charge.")
            values=[float(v) for v in matrix[1].split()]
            if not all(math.isfinite(v) for v in values):
                raise ValueError("Matrice Illustrator non finie.")
            instances.append({'symbol':symbol,'matrix_native':values,
                              'record_offset':record.start()+match.start(),
                              'pdf_object_binding':'unverified'})
        layers.append({'name':name,'symbol_instances':instances})
    total=len(re.findall(r'^/SymbolInstance\s*:',normalized,re.M))
    accounted=sum(len(layer['symbol_instances']) for layer in layers)
    return {'native_format':'AI24_ZStandard_Data','decoded_bytes':len(data),
            'decoded_sha256':hashlib.sha256(data).hexdigest(),
            'symbol_definition_count':len(re.findall(r'^%AI14_BeginSymbol\s*$',normalized,re.M)),
            'symbol_instance_count_in_layers':accounted,'other_symbol_instance_records':total-accounted,
            'layers':layers,'complete_illustrator_interpretation':False,
            'production_ready':False,'warning':'Identités et matrices natives ; correspondance aux opérateurs PDF non validée.'}


def inspect_ai_metadata(path):
    initial=file_hash(path)
    with open_pdf(path) as pdf:
        page=pdf.pages[0]
        private=page.obj.get('/PieceInfo',{}).get('/Illustrator',{}).get('/Private')
        if private is None:
            raise ValueError("Données natives Illustrator absentes.")
        keys=[key for key in private.keys() if re.fullmatch(r'/AI(?:PDF)?PrivateData\d+',key)]
        keys.sort(key=lambda key:int(re.search(r'\d+$',key)[0]))
        if not keys or [int(re.search(r'\d+$',k)[0]) for k in keys]!=list(range(1,len(keys)+1)):
            raise ValueError("Blocs natifs Illustrator incomplets.")
        parts=[];total=0
        for key in keys:
            part=private[key].read_bytes();total+=len(part)
            if total>MAX_NATIVE:raise ValueError("Données natives compressées trop volumineuses.")
            parts.append(part)
        packed=b''.join(parts)
        if not packed.startswith(PREFIX+b'\x28\xb5\x2f\xfd'):
            raise ValueError("Compression Illustrator non prise en charge.")
        compressed=packed[len(PREFIX):]
        try:
            if zstandard.get_frame_parameters(compressed).window_size > MAX_NATIVE:
                raise ValueError("Fenêtre de décompression Illustrator trop volumineuse.")
            size=zstandard.frame_content_size(compressed)
            if size not in (zstandard.CONTENTSIZE_UNKNOWN,zstandard.CONTENTSIZE_ERROR) and size>MAX_NATIVE:
                raise ValueError("Données natives décompressées trop volumineuses.")
            data=zstandard.ZstdDecompressor(max_window_size=MAX_NATIVE).decompress(compressed,max_output_size=MAX_NATIVE)
        except zstandard.ZstdError as error:
            raise ValueError("Flux Illustrator non décompressable dans les limites autorisées.") from error
        result=parse_native(data)
        oc=pdf.Root.get('/OCProperties',{});defaults=oc.get('/D',{})
        off={x.objgen for x in defaults.get('/OFF',[])}
        on={x.objgen for x in defaults.get('/ON',[])}
        visibility={str(x.get('/Name','')):(x.objgen in on or (str(defaults.get('/BaseState','/ON'))=='/ON' and x.objgen not in off))
                    for x in oc.get('/OCGs',[])}
        names=Counter(str(x.get('/Name','')) for x in oc.get('/OCGs',[]))
        for layer in result['layers']:
            layer['visible_in_default_pdf']=visibility.get(layer['name']) if names[layer['name']]==1 else None
        result['source_sha256']=initial
        result['compressed_bytes']=len(packed)
    if file_hash(path)!=initial:
        raise ValueError("Source modifiée pendant l'inspection native.")
    result['source_unchanged']=True
    return result
