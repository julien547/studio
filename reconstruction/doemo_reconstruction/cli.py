import argparse
import json
from pathlib import Path
from .extract import reconstruct
from .regions import separate_levels
from .geometry import edit, validate
from .export import export_svg, connector_payload, training_records


def write(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    temp.replace(path)


def main():
    p=argparse.ArgumentParser(description='DOEMO reconstruction — prototype avec revue humaine')
    sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('reconstruct');r.add_argument('source');r.add_argument('output');r.add_argument('--pages',type=int,nargs='+');r.add_argument('--regions',help='JSON des niveaux/régions sur les pages')
    e=sub.add_parser('edit');e.add_argument('document');e.add_argument('operation');e.add_argument('--level',required=True);e.add_argument('--actor',required=True);e.add_argument('--revision',required=True,type=int)
    x=sub.add_parser('export');x.add_argument('document');x.add_argument('output');x.add_argument('--preview',action='store_true')
    t=sub.add_parser('training');t.add_argument('document');t.add_argument('output')
    c=sub.add_parser('connector');c.add_argument('document');c.add_argument('output')
    args=p.parse_args()
    if args.command=='reconstruct':
        doc=reconstruct(args.source,args.pages)
        if args.regions: doc=separate_levels(doc,json.loads(Path(args.regions).read_text()))
        validate(doc);write(args.output,doc)
        print(json.dumps({'levels':len(doc['levels']),'walls_pending':sum(len(l['walls']) for l in doc['levels']),'production_ready':False}))
    else:
        doc=validate(json.loads(Path(args.document).read_text()))
        if args.command=='edit':
            if doc['revision']!=args.revision: raise ValueError('Révision périmée')
            write(args.document,edit(doc,args.level,json.loads(Path(args.operation).read_text()),args.actor))
        elif args.command=='connector':write(args.output,connector_payload(doc))
        elif args.command=='training':
            Path(args.output).write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in training_records(doc)),encoding='utf-8')
        else:
            dest=Path(args.output);dest.mkdir(parents=True,exist_ok=True)
            for number,level in enumerate(doc['levels'],1):
                # Never use document-provided identifiers as file paths.
                (dest/f'level-{number}.svg').write_text(export_svg(level,not args.preview),encoding='utf-8')


if __name__=='__main__':main()
