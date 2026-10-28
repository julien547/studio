"""Bind multiline text to native glyph sequences or decoded Unicode stories."""
import base64
import math
import re

import pikepdf

from .scene import union


def bind_text_frames(raw, block, items):
    sections=re.findall(r'%AI11_BeginTextDocument(.*?)%AI11_EndTextDocument',raw,re.S)
    if len(sections)!=1:raise ValueError('Document texte natif absent ou ambigu pour les libellés multilignes.')
    encoded=''.join(line[1:] for line in sections[0].splitlines() if line.startswith('%')).split('~>')[0]
    if len(encoded)>5*1024*1024:raise ValueError('Document texte natif trop volumineux.')
    try:
        data=base64.a85decode(encoded.encode('ascii'))
        stories=pikepdf.Object.parse(b'<<'+data+b'>>')['/1']['/1']
    except Exception as error:raise ValueError('Document texte natif non lisible.') from error
    records=list(re.finditer(r'^/AI11Text\s*:',block,re.M));patterns=[]
    def runs(obj,depth=0):
        if depth>40:raise ValueError('Document texte natif trop imbriqué.')
        if isinstance(obj,pikepdf.Dictionary):
            if str(obj.get('/99'))=='/G':
                glyphs=obj.get('/5')
                # Older Illustrator records store the same glyph sequence in
                # the expanded run table, alongside per-glyph positions.
                if glyphs is None:glyphs=obj.get('/21',{}).get('/0')
                if glyphs is None:raise ValueError('Séquence de glyphes native absente.')
                return [tuple(map(int,glyphs))]
            return [run for value in obj.values() for run in runs(value,depth+1)]
        if isinstance(obj,pikepdf.Array):return [run for value in obj for run in runs(value,depth+1)]
        return []
    for n,record in enumerate(records):
        part=block[record.end():records[n+1].start() if n+1<len(records) else len(block)]
        # Illustrator keeps a previous story reference inside FreeUndo records.
        # The commented replacement is the current text represented in the PDF.
        undo=re.match(r'\s*(\d+) /FreeUndo',part)
        pattern=r'^%_(\d+) /StoryIndex' if undo and undo[1]=='1' else r'^(\d+) /StoryIndex'
        refs=re.findall(pattern,part,re.M)
        if len(refs)!=1:raise ValueError('Référence du bloc texte natif ambiguë.')
        index=int(refs[0])
        if index>=len(stories):raise ValueError('Référence du bloc texte natif invalide.')
        story=stories[index];lines=str(story['/0']['/0']).rstrip('\n').split('\n');glyphs=runs(story['/1'])
        # The final glyph represents the native line terminator; its ID varies
        # with the font (e.g. 1 in SourceSans, 3 in Montserrat).
        if len(glyphs)!=len(lines) or any(len(g)!=len(line)+1 for g,line in zip(glyphs,lines)):
            raise ValueError('Structure du libellé natif non prise en charge.')
        patterns.append((tuple(g[:-1] for g in glyphs),lines))
    candidates=[]
    for pattern,lines in patterns:
        choices=[]
        for start in range(len(items)-len(pattern)+1):
            subset=items[start:start+len(pattern)]
            if not all((it.glyph_ids==glyphs if it.glyph_ids else it.text==line)
                       for it,glyphs,line in zip(subset,pattern,lines)):continue
            first=subset[0]
            if any(max(abs(a-b) for a,b in zip(first.matrix[:4],it.matrix[:4]))>1e-6 for it in subset):continue
            # This profile is horizontal, centre-aligned multiline point text.
            if len(subset)>1:
                if abs(first.matrix[1])+abs(first.matrix[2])>1e-6 or first.matrix[0]<=0 or first.matrix[3]<=0:continue
                if any(abs((a.bounds[0]+a.bounds[2]-b.bounds[0]-b.bounds[2])/2)>1 or
                       not 0 < a.matrix[5]-b.matrix[5] < 3*math.hypot(*first.matrix[:2])
                       for a,b in zip(subset,subset[1:])):continue
            choices.append(tuple(range(start,start+len(pattern))))
        if not choices:raise ValueError('Le libellé natif ne correspond pas aux glyphes PDF : '+ ' / '.join(lines))
        candidates.append(choices)
    # Require a unique, disjoint assignment covering every text operation.
    order=sorted(range(len(candidates)),key=lambda n:len(candidates[n]));solutions=[];visits=0
    # Repeated identical one-line labels (BUREAU, etc.) are interchangeable
    # native records, not different geometrical groupings. Canonical ordering
    # avoids factorial searches while retaining ambiguity checks on partitions.
    previous={};last={}
    for n in order:
        key=(patterns[n][0],tuple(patterns[n][1]))
        previous[n]=last.get(key);last[key]=n
    def solve(at,used,chosen):
        nonlocal visits
        visits+=1
        if visits>10000:raise ValueError('Association des blocs texte trop ambiguë.')
        if len(solutions)>1:return
        if at==len(order):
            if len(used)==len(items):solutions.append(dict(chosen))
            return
        n=order[at]
        for choice in candidates[n]:
            if used.intersection(choice):continue
            prior=previous[n]
            if prior is not None and choice[0]<=chosen[prior][0]:continue
            chosen[n]=choice;solve(at+1,used.union(choice),chosen);chosen.pop(n)
    solve(0,set(),{})
    if len(solutions)!=1:raise ValueError('Association des blocs texte absente ou ambiguë.')
    for n,choice in solutions[0].items():
        box=union(items[i].bounds for i in choice);anchor=((box[0]+box[2])/2,(box[1]+box[3])/2)
        for i,line in zip(choice,patterns[n][1]):items[i].text_anchor=anchor;items[i].text=line
