"""Generate the training contract from the actual backend routes, without secrets."""
import argparse
import json
import tempfile
from pathlib import Path
from doemo_releves.api import create_app
from doemo_releves.training import PREFIX
p=argparse.ArgumentParser();p.add_argument('output');args=p.parse_args()
with tempfile.TemporaryDirectory(prefix='doemo-openapi-') as root:
 schema=create_app(root).openapi()
 schema['info']={'title':'DOEMO Training API — backend OVH privé','version':'1.0.0'}
 schema['paths']={k:v for k,v in schema['paths'].items() if k.startswith(PREFIX)}
 Path(args.output).write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n')
