"""Base persistante de l'orchestrateur IA (SQLite, WAL).

Seul le service de l'orchestrateur ouvre cette base : les applications et les workers GPU
passent par l'API HTTPS. Une base unique suffit donc, même avec plusieurs GPU distants.
Le schéma n'utilise que du SQL standard pour pouvoir passer à PostgreSQL plus tard.
"""
from __future__ import annotations

import contextlib
import hashlib
import sqlite3
import time
from pathlib import Path

ENGINES = ("qwen", "paddleocr", "rtmdet", "murs")
KINDS = ("interactive", "batch", "training")
ACTIVE = ("queued", "running")
FINAL = ("completed", "failed", "cancelled")

SCHEMA = """
CREATE TABLE IF NOT EXISTS apps(
  id TEXT PRIMARY KEY, label TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
  max_running INTEGER NOT NULL DEFAULT 2, enabled INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS workers(
  id TEXT PRIMARY KEY, label TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
  engines TEXT NOT NULL, gpu TEXT, vram_total_mb INTEGER, vram_used_mb INTEGER,
  capacity INTEGER NOT NULL DEFAULT 1, loaded_models TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'offline', last_seen REAL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tasks(
  id TEXT PRIMARY KEY, app_id TEXT NOT NULL REFERENCES apps(id),
  user_login TEXT NOT NULL, project_id TEXT, engine TEXT NOT NULL,
  kind TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 0, model_version TEXT,
  status TEXT NOT NULL DEFAULT 'queued', progress REAL NOT NULL DEFAULT 0, stage TEXT,
  payload TEXT NOT NULL DEFAULT '{}', result TEXT, error TEXT, dedupe_key TEXT,
  attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
  worker_id TEXT, lease_until REAL, cancel_requested INTEGER NOT NULL DEFAULT 0,
  available_at REAL NOT NULL, created REAL NOT NULL, started REAL, finished REAL);
CREATE INDEX IF NOT EXISTS tasks_queue ON tasks(status, engine, available_at);
CREATE INDEX IF NOT EXISTS tasks_owner ON tasks(app_id, user_login, status);
-- Protection contre les doublons : une seule tâche active par (application, clé).
CREATE UNIQUE INDEX IF NOT EXISTS tasks_dedupe ON tasks(app_id, dedupe_key)
  WHERE dedupe_key IS NOT NULL AND status IN ('queued','running');
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, at REAL NOT NULL,
  kind TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS model_versions(
  id TEXT PRIMARY KEY, engine TEXT NOT NULL, name TEXT NOT NULL, artifact_uri TEXT NOT NULL,
  sha256 TEXT NOT NULL, dataset_ref TEXT, config TEXT NOT NULL DEFAULT '{}', metrics TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'candidate', created_by TEXT, created REAL NOT NULL,
  approved_by TEXT, approved_at REAL);
CREATE TABLE IF NOT EXISTS model_selection(
  app_id TEXT NOT NULL, engine TEXT NOT NULL, version_id TEXT NOT NULL REFERENCES model_versions(id),
  previous_version_id TEXT, set_by TEXT, set_at REAL NOT NULL, PRIMARY KEY(app_id, engine));
CREATE TABLE IF NOT EXISTS memory_entries(
  id TEXT PRIMARY KEY, scope TEXT NOT NULL CHECK(scope IN ('global','app')), app_id TEXT,
  kind TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','validated','retired')),
  author TEXT NOT NULL, created REAL NOT NULL, validated_by TEXT, validated_at REAL);
CREATE UNIQUE INDEX IF NOT EXISTS memory_unique ON memory_entries(scope, COALESCE(app_id,''), key)
  WHERE status!='retired';
CREATE TABLE IF NOT EXISTS corrections(
  id TEXT PRIMARY KEY, app_id TEXT NOT NULL, project_id TEXT, engine TEXT NOT NULL,
  annotation_type TEXT NOT NULL, model_version TEXT, author TEXT NOT NULL, created REAL NOT NULL,
  payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','validated','rejected')),
  reuse_allowed INTEGER NOT NULL DEFAULT 0, validated_by TEXT, validated_at REAL);
CREATE INDEX IF NOT EXISTS corrections_dataset ON corrections(engine, status, reuse_allowed);
"""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Database:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._memory = sqlite3.connect(":memory:", check_same_thread=False) if self.path == ":memory:" else None
        # executescript valide lui-même : on le lance hors du gestionnaire de transactions.
        conn = self._memory or sqlite3.connect(self.path, timeout=30)
        try:
            conn.executescript(SCHEMA)
        finally:
            if not self._memory:
                conn.close()

    @contextlib.contextmanager
    def connect(self, immediate: bool = False):
        conn = self._memory or sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        if not self._memory:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            if not self._memory:
                conn.close()

    @staticmethod
    def event(conn, task_id, kind, detail=None):
        conn.execute("INSERT INTO events(task_id,at,kind,detail) VALUES(?,?,?,?)",
                     (task_id, time.time(), kind, detail))
