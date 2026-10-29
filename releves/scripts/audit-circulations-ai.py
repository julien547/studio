"""Read an actual PDF-compatible AI without changing it. This is NOT an AI writer.

PyMuPDF is a local audit dependency only. The Illustrator private object tree is
inventoried by DOEMO-Exporter-Circulations.jsx, not reconstructed from this PDF.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
import fitz


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('--output',required=True);args=p.parse_args()
    source=Path(args.source);output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    original=source.read_bytes();sha=hashlib.sha256(original).hexdigest();report={'source_name':source.name,'sha256':sha,'bytes':len(original),
        'scope':'PDF-compatible preview vector audit only','native_illustrator_opened':False,'native_ai_saved':False,
        'native_round_trip':'pending_on_licensed_Illustrator_workstation','pages':[]}
    with fitz.open(source) as doc:
        report['pdf_metadata']=doc.metadata
        for index,page in enumerate(doc):
            paths=page.get_drawings();colors=Counter();greens=[]
            for n,path in enumerate(paths):
                fill=path.get('fill')
                if fill:colors[tuple(round(c,4) for c in fill)]+=1
                # Candidates for audit only. A colour does not validate circulation.
                if fill and len(fill)==3 and .3<fill[0]<.9 and fill[1]>fill[0]+.03 and fill[1]>fill[2]+.1 and path['rect'].get_area()>20:
                    greens.append({'pdf_path_index':n,'bounds_pdf_points':list(path['rect']),'fill_rgb':list(fill),'segments':len(path['items']),'closed':path['closePath']})
            page.get_pixmap(matrix=fitz.Matrix(1800/page.rect.width,1800/page.rect.width),alpha=False).save(output/f'page-{index+1}-original.png')
            report['pages'].append({'page':index+1,'dimensions_pt':list(page.rect),'vector_paths':len(paths),'image_objects':len(page.get_images()),
                'text_blocks':len(page.get_text('blocks')),'sample_labels':page.get_text().splitlines()[:90],
                'fill_colors':[{'rgb':list(c),'count':count} for c,count in colors.most_common(12)],'existing_green_candidates':greens})
            # Add ONLY inspection boxes on a disposable PDF copy, never in the source.
            for candidate in greens:page.draw_rect(fitz.Rect(candidate['bounds_pdf_points']),color=(.2,.3,.9),width=.7,overlay=True)
            page.get_pixmap(matrix=fitz.Matrix(1800/page.rect.width,1800/page.rect.width),alpha=False).save(output/f'page-{index+1}-audit.png')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==sha
    report['source_unchanged']=True
    (output/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'source':source.name,'pages':len(report['pages']),'paths':sum(v['vector_paths'] for v in report['pages']),
        'green_candidates':sum(len(v['existing_green_candidates']) for v in report['pages']),'native_ai_saved':False},ensure_ascii=False))


if __name__=='__main__':main()
