import pytest
from doemo_orchestrator.db import Database
from doemo_orchestrator import service as svc
from doemo_orchestrator.service import Orchestrator


class Clock:
    def __init__(self): self.t = 1_000_000.0
    def __call__(self): return self.t
    def tick(self, s): self.t += s


@pytest.fixture
def env():
    clock = Clock()
    o = Orchestrator(Database(":memory:"), clock)
    apps = {}
    for name, cap in (("releves", 4), ("redessin", 4), ("training", 1)):
        o.create_app(name, name, max_running=cap)
        apps[name] = {"id": name}
    o.create_worker("gpu1", "GPU 1", ["qwen", "paddleocr", "rtmdet"], capacity=1)
    return o, apps, clock


def worker_of(o, wid="gpu1"):
    with o.db.connect() as c:
        row = c.execute("SELECT * FROM workers WHERE id=?", (wid,)).fetchone()
    import json
    d = dict(row); d["engines"] = json.loads(d["engines"]); return d


def test_tokens_are_hashed_and_verified():
    o = Orchestrator(Database(":memory:"))
    token = o.create_app("a", "A")
    assert o.app_for_token(token)["id"] == "a"
    assert o.app_for_token("app_wrong") is None
    with o.db.connect() as c:
        assert token not in c.execute("SELECT token_hash FROM apps").fetchone()[0]


def test_interactive_before_batch_before_training(env):
    o, apps, clock = env
    o.submit(apps["training"], "u", "qwen", kind="training")
    o.submit(apps["releves"], "u", "qwen", kind="batch")
    o.submit(apps["releves"], "u", "qwen", kind="interactive")
    w = worker_of(o)
    order = []
    for _ in range(3):
        t = o.claim(w); order.append(t["kind"]); o.complete(w, t["id"], {})
    assert order == ["interactive", "batch", "training"]


def test_batch_is_not_starved_by_fresh_interactive(env):
    o, apps, clock = env
    old = o.submit(apps["releves"], "u", "qwen", kind="batch")
    clock.tick(400)  # un lot qui attend depuis 400 s dépasse une demande interactive neuve
    o.submit(apps["redessin"], "v", "qwen", kind="interactive")
    assert o.claim(worker_of(o))["id"] == old["id"]


def test_fair_share_between_apps_and_users(env):
    o, apps, clock = env
    # Un seul utilisateur d'une application remplit la file, un autre arrive après.
    for _ in range(5):
        o.submit(apps["releves"], "alice", "qwen"); clock.tick(0.1)
    o.create_worker("gpu2", "GPU 2", ["qwen"], capacity=2)
    w2 = worker_of(o, "gpu2")
    first = o.claim(w2)  # alice occupe déjà un emplacement
    other = o.submit(apps["redessin"], "bob", "qwen")
    second = o.claim(w2)
    assert first["user_login"] == "alice" and second["id"] == other["id"]


def test_app_cap_is_enforced(env):
    o, apps, clock = env
    o.create_worker("gpu3", "GPU 3", ["qwen"], capacity=5)
    w = worker_of(o, "gpu3")
    for _ in range(3):
        o.submit(apps["training"], "u", "qwen", kind="training")
    assert o.claim(w) is not None
    assert o.claim(w) is None  # max_running = 1 pour « training »


def test_dedupe_returns_same_task_while_active(env):
    o, apps, _ = env
    a = o.submit(apps["releves"], "u", "qwen", dedupe_key="doc1:p1")
    b = o.submit(apps["releves"], "u", "qwen", dedupe_key="doc1:p1")
    assert b["id"] == a["id"] and b["deduplicated"] and not a["deduplicated"]
    # une autre application peut utiliser la même clé
    c = o.submit(apps["redessin"], "u", "qwen", dedupe_key="doc1:p1")
    assert c["id"] != a["id"]


def test_dedupe_allows_new_task_after_completion(env):
    o, apps, _ = env
    a = o.submit(apps["releves"], "u", "qwen", dedupe_key="k")
    w = worker_of(o); o.complete(w, o.claim(w)["id"], {"ok": 1})
    b = o.submit(apps["releves"], "u", "qwen", dedupe_key="k")
    assert b["id"] != a["id"]


def test_engine_matching(env):
    o, apps, _ = env
    o.submit(apps["releves"], "u", "murs")
    assert o.claim(worker_of(o)) is None  # le worker n'a pas le moteur « murs »


def test_cancel_queued_and_running(env):
    o, apps, _ = env
    q = o.submit(apps["releves"], "u", "qwen")
    assert o.cancel(apps["releves"], q["id"])["status"] == "cancelled"
    r = o.submit(apps["releves"], "u", "qwen")
    w = worker_of(o); claimed = o.claim(w)
    assert o.cancel(apps["releves"], r["id"])["cancel_requested"] is True
    assert o.progress(w, claimed["id"], 0.5)["cancel_requested"] is True
    o.complete(w, claimed["id"], {"ignored": True})
    final = o.get(apps["releves"], r["id"])
    assert final["status"] == "cancelled" and final["result"] is None


def test_lease_expiry_requeues_then_fails(env):
    o, apps, clock = env
    t = o.submit(apps["releves"], "u", "qwen", max_attempts=2)
    w = worker_of(o)
    assert o.claim(w)["attempts"] == 1
    clock.tick(svc.LEASE_SECONDS + 1)          # le worker disparaît
    assert o.claim(w) is None                   # remis en file avec délai d'attente
    assert o.get(apps["releves"], t["id"])["status"] == "queued"
    clock.tick(60)
    assert o.claim(w)["attempts"] == 2
    clock.tick(svc.LEASE_SECONDS + 1)
    o.reap_expired()
    final = o.get(apps["releves"], t["id"])
    assert final["status"] == "failed" and "n'a plus répondu" in final["error"]


def test_retry_failed_task(env):
    o, apps, _ = env
    t = o.submit(apps["releves"], "u", "qwen", max_attempts=1)
    w = worker_of(o); o.fail(w, o.claim(w)["id"], "boom")
    assert o.get(apps["releves"], t["id"])["status"] == "failed"
    assert o.retry(apps["releves"], t["id"])["status"] == "queued"
    with pytest.raises(svc.Conflict):
        o.retry(apps["releves"], t["id"])


def test_retryable_failure_backs_off(env):
    o, apps, clock = env
    t = o.submit(apps["releves"], "u", "qwen")
    w = worker_of(o); o.fail(w, o.claim(w)["id"], "GPU saturé", retryable=True)
    assert o.claim(w) is None
    clock.tick(31)
    assert o.claim(w)["id"] == t["id"]


def test_apps_cannot_see_each_others_tasks(env):
    o, apps, _ = env
    t = o.submit(apps["releves"], "u", "qwen")
    with pytest.raises(svc.NotFound):
        o.get(apps["redessin"], t["id"])
    with pytest.raises(svc.NotFound):
        o.cancel(apps["redessin"], t["id"])
    assert o.list(apps["redessin"]) == []


def test_worker_cannot_finish_other_workers_task(env):
    o, apps, _ = env
    o.create_worker("gpu9", "GPU 9", ["qwen"])
    o.submit(apps["releves"], "u", "qwen")
    t = o.claim(worker_of(o))
    with pytest.raises(svc.Conflict):
        o.complete(worker_of(o, "gpu9"), t["id"], {})


def test_overload_protection(env, monkeypatch):
    o, apps, _ = env
    monkeypatch.setattr(svc, "MAX_QUEUED_PER_USER", 3)
    for _ in range(3):
        o.submit(apps["releves"], "u", "qwen")
    with pytest.raises(svc.Overloaded):
        o.submit(apps["releves"], "u", "qwen")
    o.submit(apps["releves"], "autre", "qwen")  # un autre utilisateur n'est pas bloqué


def test_validation(env):
    o, apps, _ = env
    for kwargs in ({"engine": "gpt"}, {"engine": "qwen", "kind": "x"}, {"engine": "qwen", "payload": {"x": "a" * 300_000}}):
        with pytest.raises(svc.OrchestratorError):
            o.submit(apps["releves"], "u", **kwargs)


def test_stats(env):
    o, apps, clock = env
    o.submit(apps["releves"], "alice", "qwen"); o.submit(apps["redessin"], "bob", "paddleocr")
    w = worker_of(o); o.worker_heartbeat(w, vram_total_mb=49140, vram_used_mb=20000, loaded_models=["qwen:9b"])
    t = o.claim(w); clock.tick(5); o.complete(w, t["id"], {})
    s = o.stats()
    assert s["queued"] == 1 and s["running"] == 0 and s["active_workers"] == 1
    assert s["applications"] == 3 and s["active_users"] == 2
    assert {e["name"] for e in s["by_engine"]} == {"qwen", "paddleocr"}
    assert s["workers"][0]["loaded_models"] == ["qwen:9b"]


# ---- registre de modèles -----------------------------------------------------
from doemo_orchestrator import registry

SHA = "a" * 64


def test_registry_flow_selection_and_rollback(env):
    o, apps, _ = env
    v1 = registry.register(o, "qwen", "qwen-base", "qwen/v1", SHA, "admin")
    v2 = registry.register(o, "qwen", "qwen-lora-1", "qwen/v2", "b" * 64, "admin", metrics={"f1": 0.9})
    with pytest.raises(svc.Conflict):               # une candidate n'est pas utilisable
        registry.select(o, "releves", "qwen", v1["id"], "admin")
    registry.approve(o, v1["id"], "julien"); registry.approve(o, v2["id"], "julien")
    registry.select(o, "releves", "qwen", v1["id"], "julien")
    registry.select(o, "releves", "qwen", v2["id"], "julien")
    t = o.submit(apps["releves"], "u", "qwen")            # la tâche porte la version approuvée de l'application
    assert t["model_version"] == v2["id"]
    assert o.submit(apps["redessin"], "u", "qwen")["model_version"] is None   # autre application : pas de sélection
    registry.rollback(o, "releves", "qwen", "julien")
    assert o.submit(apps["releves"], "u", "qwen", priority=1)["model_version"] == v1["id"]
    with pytest.raises(svc.Conflict):
        registry.retire(o, v1["id"])                     # encore utilisée


def test_registry_validation(env):
    o, _, _ = env
    for kw in ({"sha256": "zz"}, {"artifact_uri": "../etc/passwd"}, {"artifact_uri": "/abs/path"}, {"engine": "inconnu"}):
        args = dict(engine="qwen", name="n", artifact_uri="qwen/v1", sha256=SHA, created_by="a"); args.update(kw)
        with pytest.raises(svc.OrchestratorError):
            registry.register(o, **args)
    with pytest.raises(svc.NotFound):
        registry.approve(o, "inexistante", "julien")
