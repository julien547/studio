"""Logique de l'orchestrateur : soumission, attribution, suivi, annulation, relance, statistiques."""
from __future__ import annotations

import json
import secrets
import sqlite3
import time
import uuid

from . import scheduler
from .db import ACTIVE, ENGINES, FINAL, KINDS, Database, hash_token

LEASE_SECONDS = 120          # un worker doit signaler sa présence plus souvent que cela
MAX_PAYLOAD_BYTES = 256 * 1024
MAX_QUEUED_PER_APP = 500     # protection contre la surcharge
MAX_QUEUED_PER_USER = 100
WORKER_ONLINE_SECONDS = 30
RECENT_WINDOW = 600


class OrchestratorError(Exception):
    status = 400


class NotFound(OrchestratorError):
    status = 404


class Forbidden(OrchestratorError):
    status = 403


class Overloaded(OrchestratorError):
    status = 429


class Conflict(OrchestratorError):
    status = 409


def _task(row):
    if row is None:
        return None
    d = dict(row)
    for key in ("payload", "result"):
        d[key] = json.loads(d[key]) if d.get(key) else None
    d["cancel_requested"] = bool(d["cancel_requested"])
    return d


class Orchestrator:
    def __init__(self, db: Database, clock=time.time):
        self.db = db
        self.now = clock

    # ---- applications et workers -------------------------------------------------
    def create_app(self, app_id, label, max_running=2):
        token = "app_" + secrets.token_urlsafe(32)
        with self.db.connect(immediate=True) as c:
            c.execute("INSERT INTO apps(id,label,token_hash,max_running,created) VALUES(?,?,?,?,?)",
                      (app_id, label, hash_token(token), max_running, self.now()))
        return token  # affiché une seule fois ; seul son empreinte est conservée

    def create_worker(self, worker_id, label, engines, capacity=1, gpu=None):
        bad = [e for e in engines if e not in ENGINES]
        if bad or not engines:
            raise OrchestratorError("Moteurs inconnus : %s" % ", ".join(bad or ["(aucun)"]))
        token = "wrk_" + secrets.token_urlsafe(32)
        with self.db.connect(immediate=True) as c:
            c.execute("INSERT INTO workers(id,label,token_hash,engines,gpu,capacity,created) VALUES(?,?,?,?,?,?,?)",
                      (worker_id, label, hash_token(token), json.dumps(list(engines)), gpu, capacity, self.now()))
        return token

    def app_for_token(self, token):
        with self.db.connect() as c:
            row = c.execute("SELECT * FROM apps WHERE token_hash=? AND enabled=1", (hash_token(token or ""),)).fetchone()
        return dict(row) if row else None

    def worker_for_token(self, token):
        with self.db.connect() as c:
            row = c.execute("SELECT * FROM workers WHERE token_hash=?", (hash_token(token or ""),)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["engines"] = json.loads(d["engines"])
        return d

    # ---- soumission --------------------------------------------------------------
    def submit(self, app, user, engine, kind="interactive", project=None, priority=0,
               payload=None, dedupe_key=None, model_version=None, max_attempts=3):
        if engine not in ENGINES:
            raise OrchestratorError("Moteur inconnu : %s" % engine)
        if kind not in KINDS:
            raise OrchestratorError("Type de tâche inconnu : %s" % kind)
        if not user:
            raise OrchestratorError("Utilisateur requis")
        raw = json.dumps(payload or {}, ensure_ascii=False)
        if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise OrchestratorError("Données de la tâche trop volumineuses : transmettre une référence de fichier")
        priority = max(-10, min(10, int(priority)))
        now = self.now()
        with self.db.connect(immediate=True) as c:
            if dedupe_key:
                existing = c.execute("SELECT * FROM tasks WHERE app_id=? AND dedupe_key=? AND status IN ('queued','running')",
                                     (app["id"], dedupe_key)).fetchone()
                if existing:
                    return dict(_task(existing), deduplicated=True)
            queued_app = c.execute("SELECT COUNT(*) FROM tasks WHERE app_id=? AND status='queued'", (app["id"],)).fetchone()[0]
            queued_user = c.execute("SELECT COUNT(*) FROM tasks WHERE app_id=? AND user_login=? AND status='queued'",
                                    (app["id"], user)).fetchone()[0]
            if queued_app >= MAX_QUEUED_PER_APP or queued_user >= MAX_QUEUED_PER_USER:
                raise Overloaded("File d'attente pleine : réessayer plus tard")
            if model_version is None:
                sel = c.execute("""SELECT s.version_id FROM model_selection s JOIN model_versions v ON v.id=s.version_id
                                   WHERE s.app_id=? AND s.engine=? AND v.status='approved'""", (app["id"], engine)).fetchone()
                model_version = sel[0] if sel else None
            ident = uuid.uuid4().hex
            c.execute("""INSERT INTO tasks(id,app_id,user_login,project_id,engine,kind,priority,model_version,payload,
                         dedupe_key,max_attempts,available_at,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (ident, app["id"], user, project, engine, kind, priority, model_version, raw, dedupe_key,
                       max_attempts, now, now))
            Database.event(c, ident, "submitted", json.dumps({"app": app["id"], "user": user, "engine": engine, "kind": kind}))
            row = c.execute("SELECT * FROM tasks WHERE id=?", (ident,)).fetchone()
        return dict(_task(row), deduplicated=False)

    # ---- lecture / annulation / relance -----------------------------------------
    def _owned(self, c, app_id, task_id):
        row = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row or row["app_id"] != app_id:
            raise NotFound("Tâche introuvable")
        return row

    def get(self, app, task_id):
        with self.db.connect() as c:
            row = self._owned(c, app["id"], task_id)
            ahead = None
            if row["status"] == "queued":
                ahead = c.execute("SELECT COUNT(*) FROM tasks WHERE status='queued' AND engine=? AND created<?",
                                  (row["engine"], row["created"])).fetchone()[0]
        d = _task(row)
        d["queue_position"] = None if ahead is None else ahead + 1
        return d

    def list(self, app, user=None, project=None, status=None, limit=50):
        sql, args = "SELECT * FROM tasks WHERE app_id=?", [app["id"]]
        for column, value in (("user_login", user), ("project_id", project), ("status", status)):
            if value:
                sql += " AND %s=?" % column
                args.append(value)
        sql += " ORDER BY created DESC LIMIT ?"
        args.append(max(1, min(200, int(limit))))
        with self.db.connect() as c:
            return [_task(r) for r in c.execute(sql, args).fetchall()]

    def cancel(self, app, task_id):
        with self.db.connect(immediate=True) as c:
            row = self._owned(c, app["id"], task_id)
            if row["status"] in FINAL:
                return _task(row)
            if row["status"] == "queued":
                c.execute("UPDATE tasks SET status='cancelled',finished=?,stage='Annulée' WHERE id=?", (self.now(), task_id))
                Database.event(c, task_id, "cancelled")
            else:  # en cours : le worker l'apprend à son prochain signal de présence
                c.execute("UPDATE tasks SET cancel_requested=1 WHERE id=?", (task_id,))
                Database.event(c, task_id, "cancel_requested")
            return _task(c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def retry(self, app, task_id):
        with self.db.connect(immediate=True) as c:
            row = self._owned(c, app["id"], task_id)
            if row["status"] not in ("failed", "cancelled"):
                raise Conflict("Seule une tâche échouée ou annulée peut être relancée")
            try:
                c.execute("""UPDATE tasks SET status='queued',error=NULL,result=NULL,attempts=0,cancel_requested=0,
                             worker_id=NULL,lease_until=NULL,started=NULL,finished=NULL,progress=0,stage='Nouvelle tentative',
                             available_at=?,created=? WHERE id=?""", (self.now(), self.now(), task_id))
            except sqlite3.IntegrityError:
                raise Conflict("Une tâche identique est déjà active")
            Database.event(c, task_id, "retried")
            return _task(c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    # ---- côté workers GPU --------------------------------------------------------
    def reap_expired(self):
        """Tâches dont le worker ne donne plus signe de vie : relance automatique ou échec."""
        now = self.now()
        with self.db.connect(immediate=True) as c:
            for row in c.execute("SELECT * FROM tasks WHERE status='running' AND lease_until<?", (now,)).fetchall():
                if row["cancel_requested"]:
                    c.execute("UPDATE tasks SET status='cancelled',finished=?,stage='Annulée',worker_id=NULL WHERE id=?", (now, row["id"]))
                    Database.event(c, row["id"], "cancelled", "lease_expired")
                elif row["attempts"] < row["max_attempts"]:
                    delay = min(300, 15 * 2 ** row["attempts"])
                    c.execute("""UPDATE tasks SET status='queued',stage='Reprise après interruption',worker_id=NULL,
                                 lease_until=NULL,available_at=? WHERE id=?""", (now + delay, row["id"]))
                    Database.event(c, row["id"], "requeued", "lease_expired")
                else:
                    c.execute("""UPDATE tasks SET status='failed',finished=?,worker_id=NULL,error=?,stage='Échec' WHERE id=?""",
                              (now, "Le worker n'a plus répondu après %d tentatives" % row["attempts"], row["id"]))
                    Database.event(c, row["id"], "failed", "lease_expired")

    def worker_heartbeat(self, worker, vram_total_mb=None, vram_used_mb=None, loaded_models=None, status="online"):
        with self.db.connect(immediate=True) as c:
            c.execute("""UPDATE workers SET last_seen=?,status=?,vram_total_mb=COALESCE(?,vram_total_mb),
                         vram_used_mb=COALESCE(?,vram_used_mb),loaded_models=COALESCE(?,loaded_models) WHERE id=?""",
                      (self.now(), status, vram_total_mb, vram_used_mb,
                       json.dumps(loaded_models) if loaded_models is not None else None, worker["id"]))

    def claim(self, worker):
        """Attribue au worker la meilleure tâche éligible, ou None."""
        self.reap_expired()
        now = self.now()
        with self.db.connect(immediate=True) as c:
            c.execute("UPDATE workers SET last_seen=?,status='online' WHERE id=?", (now, worker["id"]))
            busy = c.execute("SELECT COUNT(*) FROM tasks WHERE status='running' AND worker_id=?", (worker["id"],)).fetchone()[0]
            if busy >= worker["capacity"]:
                return None
            marks = ",".join("?" * len(worker["engines"]))
            candidates = [dict(r) for r in c.execute(
                "SELECT t.* FROM tasks t JOIN apps a ON a.id=t.app_id WHERE a.enabled=1 AND t.status='queued' "
                "AND t.available_at<=? AND t.cancel_requested=0 AND t.engine IN (%s) ORDER BY t.created LIMIT 500" % marks,
                [now] + list(worker["engines"])).fetchall()]
            if not candidates:
                return None
            by_app, by_user = {}, {}
            for r in c.execute("SELECT app_id,user_login,COUNT(*) n FROM tasks WHERE status='running' GROUP BY app_id,user_login"):
                by_app[r["app_id"]] = by_app.get(r["app_id"], 0) + r["n"]
                by_user[(r["app_id"], r["user_login"])] = r["n"]
            recent = {r["app_id"]: r["s"] for r in c.execute(
                "SELECT app_id, SUM(MIN(?,COALESCE(finished,?))-MAX(started,?)) s FROM tasks "
                "WHERE started IS NOT NULL AND COALESCE(finished,?)>? GROUP BY app_id",
                (now, now, now - RECENT_WINDOW, now, now - RECENT_WINDOW))}
            caps = {r["id"]: r["max_running"] for r in c.execute("SELECT id,max_running FROM apps")}
            task = scheduler.pick(candidates, now, by_app, by_user, caps, recent)
            if not task:
                return None
            c.execute("""UPDATE tasks SET status='running',worker_id=?,attempts=attempts+1,lease_until=?,started=?,
                         stage='Préparation',progress=0 WHERE id=?""", (worker["id"], now + LEASE_SECONDS, now, task["id"]))
            Database.event(c, task["id"], "claimed", worker["id"])
            return _task(c.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone())

    def _mine(self, c, worker, task_id):
        row = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row or row["worker_id"] != worker["id"] or row["status"] != "running":
            raise Conflict("Cette tâche n'est plus attribuée à ce worker")
        return row

    def progress(self, worker, task_id, progress=None, stage=None):
        """Signal de présence : prolonge le bail et indique si l'annulation est demandée."""
        with self.db.connect(immediate=True) as c:
            row = self._mine(c, worker, task_id)
            c.execute("UPDATE tasks SET lease_until=?,progress=COALESCE(?,progress),stage=COALESCE(?,stage) WHERE id=?",
                      (self.now() + LEASE_SECONDS, progress, stage, task_id))
            return {"cancel_requested": bool(row["cancel_requested"])}

    def complete(self, worker, task_id, result):
        raw = json.dumps(result if result is not None else {}, ensure_ascii=False)
        with self.db.connect(immediate=True) as c:
            row = self._mine(c, worker, task_id)
            status = "cancelled" if row["cancel_requested"] else "completed"
            c.execute("UPDATE tasks SET status=?,result=?,progress=1,finished=?,lease_until=NULL,stage=? WHERE id=?",
                      (status, None if status == "cancelled" else raw, self.now(),
                       "Annulée" if status == "cancelled" else "Résultat prêt", task_id))
            Database.event(c, task_id, status)

    def fail(self, worker, task_id, error, retryable=True):
        now = self.now()
        with self.db.connect(immediate=True) as c:
            row = self._mine(c, worker, task_id)
            if row["cancel_requested"]:
                c.execute("UPDATE tasks SET status='cancelled',finished=?,stage='Annulée',lease_until=NULL WHERE id=?", (now, task_id))
                Database.event(c, task_id, "cancelled")
            elif retryable and row["attempts"] < row["max_attempts"]:
                delay = min(300, 15 * 2 ** row["attempts"])
                c.execute("""UPDATE tasks SET status='queued',worker_id=NULL,lease_until=NULL,error=?,available_at=?,
                             stage='Nouvelle tentative automatique' WHERE id=?""", (str(error)[:500], now + delay, task_id))
                Database.event(c, task_id, "requeued", str(error)[:200])
            else:
                c.execute("UPDATE tasks SET status='failed',finished=?,error=?,lease_until=NULL,stage='Échec' WHERE id=?",
                          (now, str(error)[:500], task_id))
                Database.event(c, task_id, "failed", str(error)[:200])

    # ---- administration ----------------------------------------------------------
    def stats(self, window=3600):
        now = self.now()
        since = now - window
        with self.db.connect() as c:
            count = lambda sql, *a: c.execute(sql, a).fetchone()[0]
            def grouped(column):
                return [dict(r) for r in c.execute(
                    "SELECT %s AS name, SUM(status='queued') queued, SUM(status='running') running, "
                    "SUM(status='completed' AND finished>=?) completed, SUM(status='failed' AND finished>=?) failed, "
                    "AVG(CASE WHEN started IS NOT NULL AND started>=? THEN started-created END) avg_wait_s, "
                    "AVG(CASE WHEN finished>=? AND status='completed' THEN finished-started END) avg_run_s "
                    "FROM tasks GROUP BY %s" % (column, column), (since, since, since, since))]
            workers = [dict(r) for r in c.execute("SELECT id,label,engines,gpu,vram_total_mb,vram_used_mb,capacity,loaded_models,last_seen FROM workers")]
            for w in workers:
                w["engines"] = json.loads(w["engines"])
                w["loaded_models"] = json.loads(w["loaded_models"])
                w["online"] = bool(w["last_seen"] and now - w["last_seen"] <= WORKER_ONLINE_SECONDS)
            return {
                "generated_at": now, "window_seconds": window,
                "applications": count("SELECT COUNT(*) FROM apps WHERE enabled=1"),
                "active_users": count("SELECT COUNT(DISTINCT user_login) FROM tasks WHERE created>=? OR status IN ('queued','running')", since),
                "queued": count("SELECT COUNT(*) FROM tasks WHERE status='queued'"),
                "running": count("SELECT COUNT(*) FROM tasks WHERE status='running'"),
                "active_workers": sum(1 for w in workers if w["online"]),
                "workers": workers,
                "by_engine": grouped("engine"), "by_app": grouped("app_id"), "by_user": grouped("user_login"),
                "by_kind": grouped("kind"),
                "errors": [dict(r) for r in c.execute(
                    "SELECT id,app_id,user_login,engine,error,finished FROM tasks WHERE status='failed' AND finished>=? "
                    "ORDER BY finished DESC LIMIT 20", (since,))],
                "gpu_cost_usd": None,  # renseigné par la couche de coûts (phase suivante)
            }
