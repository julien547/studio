"""Simulation de l'ORDONNANCEUR (pas du GPU) avec le vrai code de l'orchestrateur et une horloge simulée.

⚠️ Les durées de calcul ci-dessous sont des HYPOTHÈSES, pas des mesures. Ce banc répond à une seule
question : « avec ces durées, la file reste-t-elle équitable et les dessinateurs attendent-ils peu ? »
Les vraies durées, la VRAM et le gain de la concurrence vLLM se mesurent sur le pod (étape 7).
"""
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from doemo_orchestrator.db import Database  # noqa: E402
from doemo_orchestrator.service import Orchestrator  # noqa: E402

SERVICE = {"qwen": 20.0, "paddleocr": 6.0, "rtmdet": 4.0}   # secondes — HYPOTHÈSE
DURATION = 900.0                                             # 15 minutes simulées
TICK = 0.5


class Clock:
    t = 1_000_000.0
    def __call__(self): return self.t


def run(drafters, capacity, slowdown, batch_jobs=20, seed=7):
    rnd = random.Random(seed)
    clock = Clock(); o = Orchestrator(Database(":memory:"), clock)
    o.create_app("releves", "Relevé", max_running=8); o.create_app("lots", "Lots", max_running=2)
    o.create_worker("gpu1", "GPU", ["qwen", "paddleocr", "rtmdet"], capacity=capacity)
    with o.db.connect() as c:
        w = dict(c.execute("SELECT * FROM workers").fetchone()); w["engines"] = json.loads(w["engines"])
    # chaque dessinateur lance une analyse (Qwen + OCR + détection) toutes les ~60 s
    arrivals = []
    for d in range(drafters):
        t = rnd.uniform(0, 30)
        while t < DURATION - 60:
            for engine in ("qwen", "paddleocr", "rtmdet"):
                arrivals.append((t, "releves", "dessinateur%d" % d, engine, "interactive"))
            t += rnd.uniform(45, 75)
    for i in range(batch_jobs):   # un lot d'une autre application, déposé au début
        arrivals.append((5 + i * 0.1, "lots", "traitement", rnd.choice(list(SERVICE)), "batch"))
    arrivals.sort()
    start = clock.t; running = []   # (fin, id)
    ia = 0
    while clock.t - start < DURATION * 2:       # on laisse le temps de vider la file
        now = clock.t - start
        while ia < len(arrivals) and arrivals[ia][0] <= now:
            _, app, user, engine, kind = arrivals[ia]; o.submit({"id": app}, user, engine, kind); ia += 1
        for fin, tid in [r for r in running if r[0] <= clock.t]:
            o.complete(w, tid, {}); running.remove((fin, tid))
        while True:
            t = o.claim(w)
            if not t: break
            running.append((clock.t + SERVICE[t["engine"]] * slowdown, t["id"]))
        if ia >= len(arrivals) and not running and o.stats()["queued"] == 0: break
        clock.t += TICK
    with o.db.connect() as c:
        rows = [dict(r) for r in c.execute("SELECT app_id,kind,started-created AS wait,finished-created AS total FROM tasks WHERE status='completed'")]
    inter = sorted(r["wait"] for r in rows if r["kind"] == "interactive")
    batch = [r["total"] for r in rows if r["kind"] == "batch"]
    pct = lambda xs, p: xs[min(len(xs) - 1, int(len(xs) * p))] if xs else 0
    return {"dessinateurs": drafters, "tâches interactives": len(inter),
            "attente médiane (s)": round(statistics.median(inter), 1) if inter else 0,
            "attente p95 (s)": round(pct(inter, .95), 1), "attente max (s)": round(max(inter), 1) if inter else 0,
            "lot terminé après (s)": round(max(batch), 1) if batch else 0}


if __name__ == "__main__":
    scenarios = [("État actuel : 1 GPU, 1 tâche à la fois", 1, 1.0),
                 ("Concurrence : 1 GPU, 4 tâches en parallèle, chacune 2× plus lente (HYPOTHÈSE)", 4, 2.0)]
    for title, capacity, slowdown in scenarios:
        print("\n### " + title)
        print("| dessinateurs | tâches interactives | attente médiane (s) | attente p95 (s) | attente max (s) | lot terminé après (s) |")
        print("|---|---|---|---|---|---|")
        for n in (1, 3, 5, 10):
            r = run(n, capacity, slowdown)
            print("| %d | %d | %s | %s | %s | %s |" % (r["dessinateurs"], r["tâches interactives"], r["attente médiane (s)"],
                  r["attente p95 (s)"], r["attente max (s)"], r["lot terminé après (s)"]))
