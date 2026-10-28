"""Durable OVH job queue. Use local POSIX storage, never SQLite on geesefs/FUSE."""
import contextlib
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid

ACTIVE=('queued','running','saving','interrupted')


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


class JobStore:
    def __init__(self,path):
        self.path=str(path)
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, project TEXT NOT NULL, page INTEGER NOT NULL,
                  key TEXT NOT NULL, digest TEXT NOT NULL, kind TEXT NOT NULL,
                  request TEXT NOT NULL, status TEXT NOT NULL, progress INTEGER NOT NULL,
                  created REAL NOT NULL, updated REAL NOT NULL, attempt INTEGER NOT NULL,
                  result TEXT, error TEXT, UNIQUE(project,key));
                CREATE TABLE IF NOT EXISTS events (
                  seq INTEGER PRIMARY KEY, job_id TEXT NOT NULL, attempt INTEGER NOT NULL,
                  at REAL NOT NULL, stage TEXT NOT NULL, detail TEXT);
            ''')

    @contextlib.contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        try:
            yield db;db.commit()
        except BaseException:
            db.rollback();raise
        finally:db.close()

    def submit(self,kind,request,key,now=None):
        now=time.time() if now is None else now
        body=canonical(request);digest=hashlib.sha256((kind+body).encode()).hexdigest()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM jobs WHERE project=? AND key=?',(request['project_id'],key)).fetchone()
            if old:
                if old['digest']!=digest:raise ValueError('Clé de relance utilisée pour une autre analyse')
                if old['status']=='failed':
                    db.execute("UPDATE jobs SET status='queued',progress=0,updated=?,error=NULL WHERE id=?",(now,old['id']))
                return old['id']
            job_id=str(uuid.uuid4())
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
              (job_id,request['project_id'],request['page'],key,digest,kind,body,'queued',0,now,now,0,None,None))
        return job_id

    def claim(self):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:return None
            now=time.time();attempt=row['attempt']+1
            db.execute("UPDATE jobs SET status='running',progress=5,attempt=?,updated=? WHERE id=?",(attempt,now,row['id']))
            db.execute('INSERT INTO events(job_id,attempt,at,stage) VALUES (?,?,?,?)',(row['id'],attempt,now,'running'))
        return self.get(row['id'],include_request=True)

    def stage(self,job_id,stage,progress,detail=None):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status,attempt,progress FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row or row['status'] not in ('running','saving'):raise ValueError('Tâche inactive')
            if not row['progress']<=progress<100:raise ValueError('Progression invalide')
            now=time.time();status='saving' if stage=='saving' else row['status']
            db.execute('UPDATE jobs SET progress=?,status=?,updated=? WHERE id=?',(progress,status,now,job_id))
            db.execute('INSERT INTO events(job_id,attempt,at,stage,detail) VALUES (?,?,?,?,?)',(job_id,row['attempt'],now,stage,canonical(detail)))

    def finish(self,job_id,result):
        # The result and completed marker commit together on OVH. Never overwrite a reviewed project.
        encoded=canonical(result)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status,attempt FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row or row['status']!='saving':raise ValueError('Résultat hors phase de sauvegarde')
            now=time.time()
            db.execute("UPDATE jobs SET status='completed',progress=100,result=?,updated=?,error=NULL WHERE id=?",(encoded,now,job_id))
            db.execute('INSERT INTO events(job_id,attempt,at,stage) VALUES (?,?,?,?)',(job_id,row['attempt'],now,'completed'))

    def fail(self,job_id,error):
        with self.connection() as db:
            db.execute("UPDATE jobs SET status='failed',error=?,updated=? WHERE id=? AND status IN ('running','saving')",(error[:500],time.time(),job_id))
            row=db.execute('SELECT attempt FROM jobs WHERE id=?',(job_id,)).fetchone()
            db.execute('INSERT INTO events(job_id,attempt,at,stage,detail) VALUES (?,?,?,?,?)',(job_id,row['attempt'],time.time(),'failed',error[:500]))

    def recover(self):
        # Unknown remote activity prevents automatic retry/stop after an OVH restart.
        with self.connection() as db:
            db.execute("UPDATE jobs SET status='interrupted',error='Vérifier le worker avant réconciliation' WHERE status IN ('running','saving')")

    def reconcile(self,job_id,remote_idle):
        if remote_idle is not True:raise ValueError('Activité distante non résolue')
        with self.connection() as db:
            db.execute("UPDATE jobs SET status='queued',progress=0,updated=? WHERE id=? AND status='interrupted'",(time.time(),job_id))

    def get(self,job_id,include_request=False):
        with self.connection() as db:
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if row is None:raise KeyError(job_id)
            result=dict(row)
            result['attempts']=[dict(r) for r in db.execute('SELECT attempt,at,stage,detail FROM events WHERE job_id=? ORDER BY seq',(job_id,))]
        result['result']=json.loads(result['result']) if result['result'] else None
        if include_request:result['request']=json.loads(result['request'])
        else:result.pop('request')
        return result

    def idle(self,now=None,seconds=1800):
        now=time.time() if now is None else now
        with self.connection() as db:
            count=db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running','saving','interrupted')").fetchone()[0]
            last=db.execute('SELECT MAX(updated) FROM jobs').fetchone()[0]
        # An empty database is not evidence that this GPU belongs to an idle worker.
        return count==0 and last is not None and now-last>=seconds
