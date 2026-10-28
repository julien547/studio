from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import uuid
from .models import ProjectState


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.root / "releves.sqlite3"
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
                state TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                metadata TEXT NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(id));
            CREATE TABLE IF NOT EXISTS libraries (id TEXT PRIMARY KEY, metadata TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, project_id TEXT, actor TEXT NOT NULL,
                action TEXT NOT NULL, data TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
            ''')

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.database, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            with c:
                yield c
        finally:
            c.close()

    def create(self, actor, name):
        ident = uuid.uuid4().hex
        with self.connect() as c:
            c.execute("INSERT INTO projects(id,owner,name,state) VALUES(?,?,?,?)",
                      (ident, actor, name, ProjectState(revision=0).model_dump_json()))
        return ident

    def get(self, ident, actor, admin=False):
        with self.connect() as c:
            row = c.execute("SELECT * FROM projects WHERE id=?", (ident,)).fetchone()
            if not row or (row["owner"] != actor and not admin):
                raise LookupError("Projet inaccessible")
            docs = c.execute("SELECT id,metadata FROM documents WHERE project_id=?", (ident,)).fetchall()
        return {"id": row["id"], "owner": row["owner"], "name": row["name"],
                "state": json.loads(row["state"]),
                "documents": [dict(id=r["id"], **json.loads(r["metadata"])) for r in docs]}

    def listing(self, actor, admin=False):
        with self.connect() as c:
            rows = c.execute("SELECT id,name,owner,revision,created FROM projects" +
                             ("" if admin else " WHERE owner=?") + " ORDER BY created DESC",
                             () if admin else (actor,)).fetchall()
        return [dict(r) for r in rows]

    def save(self, project_id, actor, state, action="review"):
        # Caller has checked owner/admin and validated references and registration evidence.
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            expected = state.revision
            state = state.model_copy(deep=True)
            state.revision += 1
            result = c.execute("UPDATE projects SET state=?,revision=? WHERE id=? AND revision=?",
                               (state.model_dump_json(), state.revision, project_id, expected))
            if result.rowcount != 1:
                raise Conflict("Projet modifié dans une autre session : recharger avant de sauvegarder")
            c.execute("INSERT INTO events(project_id,actor,action,data) VALUES(?,?,?,?)",
                      (project_id, actor, action, json.dumps({"revision": state.revision})))
        return state

    def library(self, ident):
        with self.connect() as c:
            row = c.execute("SELECT metadata FROM libraries WHERE id=?", (ident,)).fetchone()
        if not row:
            raise ValueError("Bibliothèque introuvable")
        return json.loads(row["metadata"])

    def libraries(self):
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute("SELECT metadata FROM libraries")]

    def put_library(self, result):
        with self.connect() as c:
            c.execute("INSERT OR REPLACE INTO libraries VALUES(?,?)", (result["id"], json.dumps(result)))
