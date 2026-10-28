"""Registre central des versions de modèles.

Un entraînement produit une version « candidate » (poids ou adaptateur, jeu de données,
configuration, métriques). Elle n'est utilisable qu'après approbation explicite. Chaque
application choisit parmi les versions approuvées ; l'ancienne reste disponible pour un
retour arrière. Les artefacts sont immuables : la somme SHA-256 est vérifiée à la publication.
"""
from __future__ import annotations

import json
import re
import uuid

from .db import ENGINES, Database
from .service import Conflict, NotFound, Orchestrator, OrchestratorError

SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _version(row):
    d = dict(row)
    d["config"] = json.loads(d["config"])
    d["metrics"] = json.loads(d["metrics"])
    return d


def register(o: Orchestrator, engine, name, artifact_uri, sha256, created_by,
             dataset_ref=None, config=None, metrics=None):
    if engine not in ENGINES:
        raise OrchestratorError("Moteur inconnu : %s" % engine)
    if not SHA256.match(sha256 or ""):
        raise OrchestratorError("Somme SHA-256 invalide : l'intégrité de l'artefact doit être vérifiable")
    if not artifact_uri or ".." in artifact_uri or artifact_uri.startswith("/"):
        raise OrchestratorError("Emplacement d'artefact invalide (chemin relatif au stockage des modèles requis)")
    ident = uuid.uuid4().hex
    with o.db.connect(immediate=True) as c:
        c.execute("""INSERT INTO model_versions(id,engine,name,artifact_uri,sha256,dataset_ref,config,metrics,created_by,created)
                     VALUES(?,?,?,?,?,?,?,?,?,?)""",
                  (ident, engine, name, artifact_uri, sha256, dataset_ref, json.dumps(config or {}),
                   json.dumps(metrics or {}), created_by, o.now()))
        return _version(c.execute("SELECT * FROM model_versions WHERE id=?", (ident,)).fetchone())


def approve(o: Orchestrator, version_id, approved_by):
    with o.db.connect(immediate=True) as c:
        row = c.execute("SELECT * FROM model_versions WHERE id=?", (version_id,)).fetchone()
        if not row:
            raise NotFound("Version introuvable")
        if row["status"] == "retired":
            raise Conflict("Une version retirée ne peut pas être approuvée")
        c.execute("UPDATE model_versions SET status='approved',approved_by=?,approved_at=? WHERE id=?",
                  (approved_by, o.now(), version_id))
        return _version(c.execute("SELECT * FROM model_versions WHERE id=?", (version_id,)).fetchone())


def select(o: Orchestrator, app_id, engine, version_id, set_by):
    """Affecte une version approuvée à une application ; conserve la précédente pour le retour arrière."""
    with o.db.connect(immediate=True) as c:
        v = c.execute("SELECT * FROM model_versions WHERE id=?", (version_id,)).fetchone()
        if not v or v["engine"] != engine:
            raise NotFound("Version introuvable pour ce moteur")
        if v["status"] != "approved":
            raise Conflict("Seule une version approuvée peut être sélectionnée")
        if not c.execute("SELECT 1 FROM apps WHERE id=?", (app_id,)).fetchone():
            raise NotFound("Application inconnue")
        old = c.execute("SELECT version_id FROM model_selection WHERE app_id=? AND engine=?", (app_id, engine)).fetchone()
        c.execute("""INSERT INTO model_selection(app_id,engine,version_id,previous_version_id,set_by,set_at) VALUES(?,?,?,?,?,?)
                     ON CONFLICT(app_id,engine) DO UPDATE SET version_id=excluded.version_id,
                     previous_version_id=model_selection.version_id,set_by=excluded.set_by,set_at=excluded.set_at""",
                  (app_id, engine, version_id, old[0] if old else None, set_by, o.now()))


def rollback(o: Orchestrator, app_id, engine, set_by):
    with o.db.connect(immediate=True) as c:
        row = c.execute("SELECT * FROM model_selection WHERE app_id=? AND engine=?", (app_id, engine)).fetchone()
        if not row or not row["previous_version_id"]:
            raise Conflict("Aucune version précédente à rétablir")
        prev = c.execute("SELECT status FROM model_versions WHERE id=?", (row["previous_version_id"],)).fetchone()
        if not prev or prev["status"] != "approved":
            raise Conflict("La version précédente n'est plus approuvée")
        c.execute("UPDATE model_selection SET version_id=?,previous_version_id=?,set_by=?,set_at=? WHERE app_id=? AND engine=?",
                  (row["previous_version_id"], row["version_id"], set_by, o.now(), app_id, engine))


def retire(o: Orchestrator, version_id):
    with o.db.connect(immediate=True) as c:
        if c.execute("SELECT 1 FROM model_selection WHERE version_id=?", (version_id,)).fetchone():
            raise Conflict("Cette version est encore utilisée par une application")
        c.execute("UPDATE model_versions SET status='retired' WHERE id=?", (version_id,))


def list_versions(o: Orchestrator, engine=None, approved_only=False):
    sql, args = "SELECT * FROM model_versions WHERE 1=1", []
    if engine:
        sql += " AND engine=?"; args.append(engine)
    if approved_only:
        sql += " AND status='approved'"
    with o.db.connect() as c:
        return [_version(r) for r in c.execute(sql + " ORDER BY created DESC", args)]


def selections(o: Orchestrator, app_id):
    with o.db.connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM model_selection WHERE app_id=?", (app_id,))]
