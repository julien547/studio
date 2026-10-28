"""API centrale HTTPS de l'orchestrateur.

Trois audiences, trois jetons distincts :
  * application (releves, redessin, entrainement…) : soumet et suit SES tâches ;
  * worker GPU : réclame des tâches et rend les résultats, sans voir le reste ;
  * administration : tableau de bord, applications, workers, registre des modèles.
Les applications ne parlent jamais aux environnements Python des modèles.
"""
from __future__ import annotations

import hmac
import os
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import memory, registry
from .db import Database
from .service import Orchestrator, OrchestratorError


class NewTask(BaseModel):
    user: str = Field(min_length=1, max_length=120)
    engine: str
    kind: str = "interactive"
    project: Optional[str] = Field(default=None, max_length=120)
    priority: int = 0
    payload: Dict[str, Any] = {}
    dedupe_key: Optional[str] = Field(default=None, max_length=200)
    model_version: Optional[str] = None
    max_attempts: int = Field(default=3, ge=1, le=10)


class Heartbeat(BaseModel):
    vram_total_mb: Optional[int] = None
    vram_used_mb: Optional[int] = None
    loaded_models: Optional[List[str]] = None


class Progress(BaseModel):
    progress: Optional[float] = Field(default=None, ge=0, le=1)
    stage: Optional[str] = Field(default=None, max_length=200)


class Complete(BaseModel):
    result: Dict[str, Any] = {}


class Failure(BaseModel):
    error: str = Field(max_length=500)
    retryable: bool = True


class NewApp(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_-]{2,40}$")
    label: str
    max_running: int = Field(default=2, ge=1, le=64)


class NewWorker(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_-]{2,40}$")
    label: str
    engines: List[str]
    capacity: int = Field(default=1, ge=1, le=64)
    gpu: Optional[str] = None


class NewModel(BaseModel):
    engine: str
    name: str
    artifact_uri: str
    sha256: str
    created_by: str
    dataset_ref: Optional[str] = None
    config: Dict[str, Any] = {}
    metrics: Dict[str, Any] = {}


class Selection(BaseModel):
    version_id: str
    set_by: str


class Actor(BaseModel):
    actor: str


class MemoryWrite(BaseModel):
    kind: str
    value: Dict[str, Any]
    author: str


class AdminMemoryWrite(BaseModel):
    kind: str
    key: str
    value: Dict[str, Any]
    author: str


class NewCorrection(BaseModel):
    engine: str
    annotation_type: str
    author: str
    payload: Dict[str, Any]
    project: Optional[str] = None
    model_version: Optional[str] = None


class Decision(BaseModel):
    actor: str
    reuse_allowed: bool = False


def create_app(orchestrator: Orchestrator = None, db_path: str = None) -> FastAPI:
    orch = orchestrator or Orchestrator(Database(db_path or os.environ.get("DOEMO_ORCH_DB", "/var/lib/doemo-studio/orchestrateur/orch.db")))
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, title="DOEMO Orchestrateur IA")

    @app.exception_handler(OrchestratorError)
    async def _error(_: Request, exc: OrchestratorError):
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=exc.status)

    def bearer(value: str) -> str:
        return value[7:] if value.startswith("Bearer ") else ""

    def current_app(authorization: str = Header(default="")):
        found = orch.app_for_token(bearer(authorization))
        if not found:
            raise HTTPException(401, "Authentification requise")
        return found

    def current_worker(authorization: str = Header(default="")):
        found = orch.worker_for_token(bearer(authorization))
        if not found:
            raise HTTPException(401, "Authentification requise")
        return found

    def admin(authorization: str = Header(default="")):
        expected = os.environ.get("DOEMO_ORCH_ADMIN_TOKEN", "")
        if len(expected) < 32 or not hmac.compare_digest(bearer(authorization), expected):
            raise HTTPException(401, "Authentification requise")

    # ---- applications ------------------------------------------------------------
    @app.post("/v1/tasks", status_code=201)
    def submit(body: NewTask, who=Depends(current_app)):
        return orch.submit(who, body.user, body.engine, body.kind, body.project, body.priority,
                           body.payload, body.dedupe_key, body.model_version, body.max_attempts)

    @app.get("/v1/tasks")
    def tasks(user: Optional[str] = None, project: Optional[str] = None, status: Optional[str] = None,
              limit: int = 50, who=Depends(current_app)):
        return {"tasks": orch.list(who, user, project, status, limit)}

    @app.get("/v1/tasks/{task_id}")
    def task(task_id: str, who=Depends(current_app)):
        return orch.get(who, task_id)

    @app.post("/v1/tasks/{task_id}/cancel")
    def cancel(task_id: str, who=Depends(current_app)):
        return orch.cancel(who, task_id)

    @app.post("/v1/tasks/{task_id}/retry")
    def retry(task_id: str, who=Depends(current_app)):
        return orch.retry(who, task_id)

    @app.get("/v1/models")
    def models(engine: Optional[str] = None, who=Depends(current_app)):
        return {"approved": registry.list_versions(orch, engine, approved_only=True),
                "selected": registry.selections(orch, who["id"])}

    # ---- mémoire commune et corrections (côté application) -------------------------
    @app.get("/v1/memory")
    def read_memory(who=Depends(current_app)):
        return memory.read_for_app(orch, who["id"])

    @app.put("/v1/memory/app/{key}")
    def put_app_memory(key: str, body: MemoryWrite, who=Depends(current_app)):
        return memory.put_app(orch, who["id"], body.kind, key, body.value, body.author)

    @app.put("/v1/memory/global-proposals/{key}", status_code=202)
    def propose(key: str, body: MemoryWrite, who=Depends(current_app)):
        return memory.propose_global(orch, who["id"], body.kind, key, body.value, body.author)

    @app.post("/v1/corrections", status_code=201)
    def new_correction(body: NewCorrection, who=Depends(current_app)):
        return {"id": memory.submit_correction(orch, who["id"], body.engine, body.annotation_type, body.author,
                                               body.payload, body.project, body.model_version)}

    @app.get("/v1/corrections")
    def my_corrections(status: Optional[str] = None, who=Depends(current_app)):
        return {"corrections": memory.list_corrections(orch, who["id"], status)}

    # ---- workers GPU -------------------------------------------------------------
    @app.post("/v1/worker/heartbeat")
    def heartbeat(body: Heartbeat, who=Depends(current_worker)):
        orch.worker_heartbeat(who, body.vram_total_mb, body.vram_used_mb, body.loaded_models)
        return {"ok": True}

    @app.post("/v1/worker/claim")
    def claim(who=Depends(current_worker)):
        task = orch.claim(who)
        if task and task["model_version"]:
            task["model"] = next((v for v in registry.list_versions(orch, approved_only=True)
                                  if v["id"] == task["model_version"]), None)
        return {"task": task}

    @app.post("/v1/worker/tasks/{task_id}/progress")
    def progress(task_id: str, body: Progress, who=Depends(current_worker)):
        return orch.progress(who, task_id, body.progress, body.stage)

    @app.post("/v1/worker/tasks/{task_id}/complete")
    def complete(task_id: str, body: Complete, who=Depends(current_worker)):
        orch.complete(who, task_id, body.result)
        return {"ok": True}

    @app.post("/v1/worker/tasks/{task_id}/fail")
    def fail(task_id: str, body: Failure, who=Depends(current_worker)):
        orch.fail(who, task_id, body.error, body.retryable)
        return {"ok": True}

    # ---- administration (tableau de bord, registre) ------------------------------
    @app.get("/v1/admin/overview", dependencies=[Depends(admin)])
    def overview(window: int = 3600):
        return orch.stats(max(60, min(86400 * 30, window)))

    @app.post("/v1/admin/apps", status_code=201, dependencies=[Depends(admin)])
    def new_app(body: NewApp):
        return {"id": body.id, "token": orch.create_app(body.id, body.label, body.max_running),
                "note": "Ce jeton n'est affiché qu'une fois."}

    @app.post("/v1/admin/workers", status_code=201, dependencies=[Depends(admin)])
    def new_worker(body: NewWorker):
        return {"id": body.id, "token": orch.create_worker(body.id, body.label, body.engines, body.capacity, body.gpu),
                "note": "Ce jeton n'est affiché qu'une fois."}

    @app.get("/v1/admin/models", dependencies=[Depends(admin)])
    def all_models(engine: Optional[str] = None):
        return {"versions": registry.list_versions(orch, engine)}

    @app.post("/v1/admin/models", status_code=201, dependencies=[Depends(admin)])
    def register_model(body: NewModel):
        return registry.register(orch, body.engine, body.name, body.artifact_uri, body.sha256, body.created_by,
                                 body.dataset_ref, body.config, body.metrics)

    @app.post("/v1/admin/models/{version_id}/approve", dependencies=[Depends(admin)])
    def approve_model(version_id: str, body: Actor):
        return registry.approve(orch, version_id, body.actor)

    @app.post("/v1/admin/apps/{app_id}/models/{engine}", dependencies=[Depends(admin)])
    def select_model(app_id: str, engine: str, body: Selection):
        registry.select(orch, app_id, engine, body.version_id, body.set_by)
        return {"ok": True}

    @app.post("/v1/admin/apps/{app_id}/models/{engine}/rollback", dependencies=[Depends(admin)])
    def rollback_model(app_id: str, engine: str, body: Actor):
        registry.rollback(orch, app_id, engine, body.actor)
        return {"ok": True}

    # ---- administration : mémoire globale, validation des corrections, jeux de données
    @app.put("/v1/admin/memory/global", dependencies=[Depends(admin)])
    def admin_set_global(body: AdminMemoryWrite):
        return memory.set_global(orch, body.kind, body.key, body.value, body.author)

    @app.post("/v1/admin/memory/{entry_id}/validate", dependencies=[Depends(admin)])
    def admin_validate_global(entry_id: str, body: Actor):
        return memory.validate_global(orch, entry_id, body.actor)

    @app.post("/v1/admin/corrections/{correction_id}/validate", dependencies=[Depends(admin)])
    def admin_validate_correction(correction_id: str, body: Decision):
        memory.validate_correction(orch, correction_id, body.actor, body.reuse_allowed)
        return {"ok": True}

    @app.post("/v1/admin/corrections/{correction_id}/reject", dependencies=[Depends(admin)])
    def admin_reject_correction(correction_id: str, body: Actor):
        memory.reject_correction(orch, correction_id, body.actor)
        return {"ok": True}

    @app.get("/v1/admin/datasets/{engine}", dependencies=[Depends(admin)])
    def admin_dataset(engine: str):
        return memory.export_dataset(orch, engine)

    return app
