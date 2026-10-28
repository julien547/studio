import threading
import pytest
from fastapi.testclient import TestClient
from doemo_orchestrator.api import create_app
from doemo_orchestrator.db import Database
from doemo_orchestrator.service import Orchestrator

ADMIN = "x" * 40


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DOEMO_ORCH_ADMIN_TOKEN", ADMIN)
    return TestClient(create_app(Orchestrator(Database(tmp_path / "orch.db"))))


def auth(token): return {"Authorization": "Bearer " + token}


def test_end_to_end_over_http(client):
    app_token = client.post("/v1/admin/apps", json={"id": "releves", "label": "Relevé"}, headers=auth(ADMIN)).json()["token"]
    wrk_token = client.post("/v1/admin/workers", json={"id": "gpu1", "label": "A6000", "engines": ["qwen"]}, headers=auth(ADMIN)).json()["token"]
    created = client.post("/v1/tasks", json={"user": "alice", "engine": "qwen", "payload": {"image": "docs/p1.png"}},
                          headers=auth(app_token))
    assert created.status_code == 201
    tid = created.json()["id"]
    assert client.get("/v1/tasks/" + tid, headers=auth(app_token)).json()["queue_position"] == 1
    claimed = client.post("/v1/worker/claim", headers=auth(wrk_token)).json()["task"]
    assert claimed["id"] == tid and claimed["payload"]["image"] == "docs/p1.png"
    assert client.post("/v1/worker/tasks/%s/progress" % tid, json={"progress": 0.5}, headers=auth(wrk_token)).json() == {"cancel_requested": False}
    client.post("/v1/worker/tasks/%s/complete" % tid, json={"result": {"zones": []}}, headers=auth(wrk_token))
    done = client.get("/v1/tasks/" + tid, headers=auth(app_token)).json()
    assert done["status"] == "completed" and done["result"] == {"zones": []}
    overview = client.get("/v1/admin/overview", headers=auth(ADMIN)).json()
    assert overview["by_app"][0]["name"] == "releves" and overview["by_app"][0]["completed"] == 1


def test_authentication_is_separated(client):
    app_token = client.post("/v1/admin/apps", json={"id": "releves", "label": "R"}, headers=auth(ADMIN)).json()["token"]
    wrk_token = client.post("/v1/admin/workers", json={"id": "gpu1", "label": "G", "engines": ["qwen"]}, headers=auth(ADMIN)).json()["token"]
    assert client.get("/v1/tasks").status_code == 401
    assert client.get("/v1/admin/overview", headers=auth(app_token)).status_code == 401   # une application n'est pas admin
    assert client.post("/v1/worker/claim", headers=auth(app_token)).status_code == 401    # ni worker
    assert client.post("/v1/tasks", json={"user": "u", "engine": "qwen"}, headers=auth(wrk_token)).status_code == 401
    assert client.get("/v1/admin/overview", headers=auth("")).status_code == 401


def test_errors_are_json(client):
    t = client.post("/v1/admin/apps", json={"id": "releves", "label": "R"}, headers=auth(ADMIN)).json()["token"]
    r = client.post("/v1/tasks", json={"user": "u", "engine": "gpt-9"}, headers=auth(t))
    assert r.status_code == 400 and r.json()["ok"] is False
    assert client.get("/v1/tasks/inconnue", headers=auth(t)).status_code == 404


def test_no_double_assignment_under_concurrency(tmp_path):
    """8 workers se disputent 40 tâches : chacune doit être attribuée exactement une fois."""
    o = Orchestrator(Database(tmp_path / "orch.db"))
    o.create_app("releves", "R", max_running=100)
    for i in range(40):
        o.submit({"id": "releves"}, "u%d" % (i % 5), "qwen")
    workers = []
    for i in range(8):
        o.create_worker("gpu%d" % i, "G", ["qwen"], capacity=50)
    import json
    with o.db.connect() as c:
        for r in c.execute("SELECT * FROM workers"):
            d = dict(r); d["engines"] = json.loads(d["engines"]); workers.append(d)
    got, errors = [], []
    lock = threading.Lock()

    def run(w):
        try:
            while True:
                t = o.claim(w)
                if not t:
                    return
                with lock:
                    got.append(t["id"])
        except Exception as e:  # pragma: no cover
            errors.append(repr(e))

    threads = [threading.Thread(target=run, args=(w,)) for w in workers]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert not errors
    assert len(got) == 40 and len(set(got)) == 40


def test_memory_and_corrections_over_http(client):
    a = client.post("/v1/admin/apps", json={"id": "releves", "label": "R"}, headers=auth(ADMIN)).json()["token"]
    b = client.post("/v1/admin/apps", json={"id": "redessin", "label": "D"}, headers=auth(ADMIN)).json()["token"]
    assert client.put("/v1/memory/global-proposals/RIA", json={"kind": "abbreviation", "value": {"s": "robinet"}, "author": "alice"}, headers=auth(a)).status_code == 202
    assert client.get("/v1/memory", headers=auth(b)).json()["validated"] == []
    proposal = client.get("/v1/memory", headers=auth(a)).json()["my_proposals"][0]
    client.post("/v1/admin/memory/%s/validate" % proposal["id"], json={"actor": "julien"}, headers=auth(ADMIN))
    assert [e["key"] for e in client.get("/v1/memory", headers=auth(b)).json()["validated"]] == ["RIA"]
    cid = client.post("/v1/corrections", json={"engine": "paddleocr", "annotation_type": "texte", "author": "alice",
                      "payload": {"format": "ocr_lines", "lines": ["x"]}}, headers=auth(a)).json()["id"]
    assert client.get("/v1/corrections", headers=auth(b)).json()["corrections"] == []
    client.post("/v1/admin/corrections/%s/validate" % cid, json={"actor": "julien", "reuse_allowed": True}, headers=auth(ADMIN))
    assert client.get("/v1/admin/datasets/paddleocr", headers=auth(ADMIN)).json()["count"] == 1
    assert client.get("/v1/admin/datasets/paddleocr", headers=auth(a)).status_code == 401   # réservé à l'administration


def test_read_token_only_sees_overview(client, monkeypatch):
    monkeypatch.setenv("DOEMO_ORCH_READ_TOKEN", "r" * 40)
    assert client.get("/v1/admin/overview", headers=auth("r" * 40)).status_code == 200      # tableau de bord
    assert client.get("/v1/admin/overview", headers=auth(ADMIN)).status_code == 200
    assert client.get("/v1/admin/models", headers=auth("r" * 40)).status_code == 401        # rien d'autre
    assert client.post("/v1/admin/apps", json={"id": "xx", "label": "x"}, headers=auth("r" * 40)).status_code == 401
    assert client.get("/v1/admin/overview", headers=auth("trop-court")).status_code == 401


def test_read_token_ignored_when_not_configured(client, monkeypatch):
    monkeypatch.delenv("DOEMO_ORCH_READ_TOKEN", raising=False)
    assert client.get("/v1/admin/overview", headers=auth("")).status_code == 401
