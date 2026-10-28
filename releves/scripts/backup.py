"""Consistent SQLite backup + immutable documents/libraries. Destination must be new.
Run while imports/library approvals are paused. Never copy a live database file.
"""
import argparse
import os
import shutil
import sqlite3
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('destination');args=p.parse_args()
root=Path(os.environ.get('DOEMO_RELEVES_DATA','/var/lib/doemo-studio/releves'))
destination=Path(args.destination);destination.mkdir(mode=0o700)
with sqlite3.connect(root/'releves.sqlite3') as source,sqlite3.connect(destination/'releves.sqlite3') as target:
    source.backup(target)
for name in ('documents','libraries'):
    if (root/name).exists():shutil.copytree(root/name,destination/name)
print('Sauvegarde créée. Protéger et chiffrer ce dossier avant transfert.')
