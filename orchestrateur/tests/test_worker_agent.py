import threading
import time
import pytest
from fastapi.testclient import TestClient
from doemo_orchestrator.api import create_app
from doemo_orchestrator.db import Database
from doemo_orchestrator.service import Orchestrator
from doemo_orchestrator.worker_agent import WorkerAgent

ADMIN = "x" * 40


@pytest.fixture
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("DOEMO_ORCH_ADMIN_TOKEN", ADMIN)
    app = create_app(Orchestrator(Database(tmp_path / "o.db")))
    admin = TestClient(app, headers={"Authorization": "Bearer " + ADMIN})
    app_token = admin.post("/v1/admin/apps", json={"id": "releves", "label": "R"}).json()["token"]
    wtoken = admin.post("/v1/admin/workers", json={"id": "gpu1", "label": "G", "engines": ["qwen", "paddleocr"], "capacity": 2}).json()["token"]
    apps = TestClient(app, headers={"Authorization": "Bearer " + app_token})
    wclient = TestClient(app, headers={"Authorization": "Bearer " + wtoken})
    return apps, wclient


def wait_status(apps, tid, status, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        t = apps.get("/v1/tasks/" + tid).json()
        if t["status"] == status:
            return t
        time.sleep(0.02)
    raise AssertionError("statut %s non atteint : %s" % (status, apps.get("/v1/tasks/" + tid).json()["status"]))


def test_agent_runs_task_and_reports_result(stack):
    apps, wclient = stack
    tid = apps.post("/v1/tasks", json={"user": "alice", "engine": "qwen", "payload": {"n": 2}}).json()["id"]
    def qwen(task, report):
        report(0.5, "lecture")
        return {"double": task["payload"]["n"] * 2}
    agent = WorkerAgent(wclient, {"qwen": qwen}, capacity=1)
    assert agent.step() is True
    done = wait_status(apps, tid, "completed")
    assert done["result"] == {"double": 4}


def test_agent_never_exceeds_capacity(stack):
    apps, wclient = stack
    for _ in range(3):
        apps.post("/v1/tasks", json={"user": "alice", "engine": "qwen"})
    release = threading.Event(); running = []
    def slow(task, report):
        running.append(task["id"]); release.wait(5); return {}
    agent = WorkerAgent(wclient, {"qwen": slow}, capacity=2)
    assert agent.step() and agent.step()
    assert agent.step() is False          # capacité atteinte : aucune 3ᵉ réclamation
    time.sleep(0.1); assert len(running) == 2
    release.set(); agent.drain()


def test_agent_applies_cancellation(stack):
    apps, wclient = stack
    tid = apps.post("/v1/tasks", json={"user": "alice", "engine": "qwen"}).json()["id"]
    started = threading.Event(); proceed = threading.Event()
    def qwen(task, report):
        started.set(); proceed.wait(5)
        report(0.9)                       # constate l'annulation et s'arrête
        return {"jamais": "publié"}
    agent = WorkerAgent(wclient, {"qwen": qwen})
    agent.step(); started.wait(2)
    apps.post("/v1/tasks/%s/cancel" % tid)
    proceed.set(); agent.drain()
    final = wait_status(apps, tid, "cancelled")
    assert final["result"] is None


def test_agent_reports_failure_and_retries(stack):
    apps, wclient = stack
    tid = apps.post("/v1/tasks", json={"user": "alice", "engine": "qwen", "max_attempts": 1}).json()["id"]
    def boom(task, report): raise RuntimeError("VRAM insuffisante")
    agent = WorkerAgent(wclient, {"qwen": boom}); agent.step(); agent.drain()
    failed = wait_status(apps, tid, "failed")
    assert "VRAM insuffisante" in failed["error"]


def test_agent_rejects_unsupported_engine(stack):
    apps, wclient = stack
    tid = apps.post("/v1/tasks", json={"user": "alice", "engine": "paddleocr", "max_attempts": 1}).json()["id"]
    agent = WorkerAgent(wclient, {"qwen": lambda t, r: {}}); agent.step(); agent.drain()
    assert "non pris en charge" in wait_status(apps, tid, "failed")["error"]
