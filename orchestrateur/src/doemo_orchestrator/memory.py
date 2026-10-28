"""Mémoire commune et registre des corrections.

Mémoire commune ne signifie pas accès libre aux dossiers clients :
  * globale DOEMO : lue par toutes les applications ; une application ne peut que PROPOSER
    (brouillon), seul l'administrateur valide ;
  * par application : écrite et lue uniquement par l'application, jamais partagée ;
  * projets clients : ils restent dans l'application d'origine. Ici on ne garde que des
    RÉFÉRENCES (identifiants de projet), jamais les fichiers.
Une correction est enregistrée immédiatement et durablement, avec sa traçabilité complète ;
elle n'entre dans un jeu de données qu'après validation ET autorisation de réutilisation.
Les jeux de données sont distincts par moteur et chacun n'accepte que son format.
"""
from __future__ import annotations

import json
import uuid

from .db import ENGINES
from .service import Conflict, NotFound, Orchestrator, OrchestratorError

KINDS = ("abbreviation", "reading_rule", "drawing_convention", "equipment_category", "example", "architectural_rule", "instruction", "parameter")
MAX_VALUE_BYTES = 64 * 1024
MAX_CORRECTION_BYTES = 256 * 1024
# Un format d'annotation par moteur : on ne mélange jamais les formats dans un même jeu de données.
DATASET_FORMAT = {"qwen": "qa_json", "paddleocr": "ocr_lines", "rtmdet": "coco_boxes", "murs": "wall_segments"}


def _entry(row):
    d = dict(row); d["value"] = json.loads(d["value"]); return d


def _check_value(kind, key, value):
    if kind not in KINDS:
        raise OrchestratorError("Type de mémoire inconnu : %s" % kind)
    if not key or len(key) > 200:
        raise OrchestratorError("Clé invalide")
    raw = json.dumps(value, ensure_ascii=False)
    if len(raw.encode("utf-8")) > MAX_VALUE_BYTES:
        raise OrchestratorError("Entrée de mémoire trop volumineuse")
    return raw


def put_app(o: Orchestrator, app_id, kind, key, value, author):
    """Mémoire propre à l'application : écrite par elle-même, validée d'emblée, jamais partagée."""
    raw = _check_value(kind, key, value)
    with o.db.connect(immediate=True) as c:
        c.execute("UPDATE memory_entries SET status='retired' WHERE scope='app' AND app_id=? AND key=? AND status!='retired'", (app_id, key))
        ident = uuid.uuid4().hex
        c.execute("""INSERT INTO memory_entries(id,scope,app_id,kind,key,value,status,author,created,validated_by,validated_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?)""", ("%s" % ident, "app", app_id, kind, key, raw, "validated", author, o.now(), author, o.now()))
        return _entry(c.execute("SELECT * FROM memory_entries WHERE id=?", (ident,)).fetchone())


def propose_global(o: Orchestrator, app_id, kind, key, value, author):
    """Une application propose une règle globale : elle reste en brouillon jusqu'à validation par l'administrateur."""
    raw = _check_value(kind, key, value)
    with o.db.connect(immediate=True) as c:
        if c.execute("SELECT 1 FROM memory_entries WHERE scope='global' AND key=? AND status!='retired' AND app_id IS NOT ?", (key, app_id)).fetchone():
            raise Conflict("Une entrée globale existe déjà pour cette clé : demander sa modification à l'administrateur")
        c.execute("UPDATE memory_entries SET status='retired' WHERE scope='global' AND app_id=? AND key=? AND status='draft'", (app_id, key))
        ident = uuid.uuid4().hex
        c.execute("INSERT INTO memory_entries(id,scope,app_id,kind,key,value,status,author,created) VALUES(?,?,?,?,?,?,?,?,?)",
                  (ident, "global", app_id, kind, key, raw, "draft", author, o.now()))
        return _entry(c.execute("SELECT * FROM memory_entries WHERE id=?", (ident,)).fetchone())


def validate_global(o: Orchestrator, entry_id, validated_by):
    with o.db.connect(immediate=True) as c:
        row = c.execute("SELECT * FROM memory_entries WHERE id=?", (entry_id,)).fetchone()
        if not row or row["scope"] != "global":
            raise NotFound("Proposition introuvable")
        c.execute("UPDATE memory_entries SET status='retired' WHERE scope='global' AND key=? AND status='validated' AND id!=?", (row["key"], entry_id))
        c.execute("UPDATE memory_entries SET status='validated',validated_by=?,validated_at=? WHERE id=?", (validated_by, o.now(), entry_id))
        return _entry(c.execute("SELECT * FROM memory_entries WHERE id=?", (entry_id,)).fetchone())


def set_global(o: Orchestrator, kind, key, value, author):
    """Écriture directe de l'administrateur dans la mémoire globale."""
    raw = _check_value(kind, key, value)
    with o.db.connect(immediate=True) as c:
        c.execute("UPDATE memory_entries SET status='retired' WHERE scope='global' AND key=? AND status!='retired'", (key,))
        ident = uuid.uuid4().hex
        c.execute("""INSERT INTO memory_entries(id,scope,app_id,kind,key,value,status,author,created,validated_by,validated_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (ident, "global", None, kind, key, raw, "validated", author, o.now(), author, o.now()))
        return _entry(c.execute("SELECT * FROM memory_entries WHERE id=?", (ident,)).fetchone())


def read_for_app(o: Orchestrator, app_id):
    """Ce qu'une application a le droit de lire : le global validé + SA mémoire. Rien des autres applications."""
    with o.db.connect() as c:
        rows = c.execute("""SELECT * FROM memory_entries WHERE status='validated' AND
                            (scope='global' OR (scope='app' AND app_id=?)) ORDER BY scope,key""", (app_id,)).fetchall()
        mine = c.execute("SELECT * FROM memory_entries WHERE scope='global' AND status='draft' AND app_id=?", (app_id,)).fetchall()
    return {"validated": [_entry(r) for r in rows], "my_proposals": [_entry(r) for r in mine]}


# ---- corrections ----------------------------------------------------------------------
def submit_correction(o: Orchestrator, app_id, engine, annotation_type, author, payload, project_id=None, model_version=None):
    if engine not in ENGINES:
        raise OrchestratorError("Moteur inconnu : %s" % engine)
    if not annotation_type or not author:
        raise OrchestratorError("Type d'annotation et auteur requis")
    if payload.get("format") != DATASET_FORMAT[engine]:
        raise OrchestratorError("Format d'annotation « %s » attendu pour %s : les formats ne se mélangent pas" % (DATASET_FORMAT[engine], engine))
    raw = json.dumps(payload, ensure_ascii=False)
    if len(raw.encode("utf-8")) > MAX_CORRECTION_BYTES:
        raise OrchestratorError("Correction trop volumineuse : transmettre une référence de fichier")
    ident = uuid.uuid4().hex
    with o.db.connect(immediate=True) as c:   # persistée immédiatement
        c.execute("""INSERT INTO corrections(id,app_id,project_id,engine,annotation_type,model_version,author,created,payload)
                     VALUES(?,?,?,?,?,?,?,?,?)""", (ident, app_id, project_id, engine, annotation_type, model_version, author, o.now(), raw))
    return ident


def _decide(o, correction_id, status, by, reuse_allowed):
    with o.db.connect(immediate=True) as c:
        row = c.execute("SELECT status FROM corrections WHERE id=?", (correction_id,)).fetchone()
        if not row:
            raise NotFound("Correction introuvable")
        if row["status"] != "pending":
            raise Conflict("Cette correction a déjà été traitée")
        c.execute("UPDATE corrections SET status=?,reuse_allowed=?,validated_by=?,validated_at=? WHERE id=?",
                  (status, 1 if (status == "validated" and reuse_allowed) else 0, by, o.now(), correction_id))


def validate_correction(o, correction_id, by, reuse_allowed=False):
    _decide(o, correction_id, "validated", by, reuse_allowed)


def reject_correction(o, correction_id, by):
    _decide(o, correction_id, "rejected", by, False)


def list_corrections(o, app_id, status=None, limit=100):
    sql, args = "SELECT id,project_id,engine,annotation_type,model_version,author,created,status,reuse_allowed FROM corrections WHERE app_id=?", [app_id]
    if status:
        sql += " AND status=?"; args.append(status)
    with o.db.connect() as c:
        return [dict(r) for r in c.execute(sql + " ORDER BY created DESC LIMIT ?", args + [max(1, min(500, limit))])]


def export_dataset(o, engine):
    """Jeu de données commun d'un moteur : uniquement corrections validées ET réutilisables, avec leur traçabilité."""
    if engine not in ENGINES:
        raise OrchestratorError("Moteur inconnu : %s" % engine)
    with o.db.connect() as c:
        rows = c.execute("SELECT * FROM corrections WHERE engine=? AND status='validated' AND reuse_allowed=1 ORDER BY created", (engine,)).fetchall()
    return {"engine": engine, "format": DATASET_FORMAT[engine], "count": len(rows),
            "records": [{"id": r["id"], "app": r["app_id"], "project": r["project_id"], "annotation_type": r["annotation_type"],
                         "model_version": r["model_version"], "author": r["author"], "created": r["created"],
                         "validated_by": r["validated_by"], "payload": json.loads(r["payload"])} for r in rows]}
