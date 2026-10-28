"""Agent worker : tourne à côté d'un GPU, réclame du travail à l'orchestrateur et le fait exécuter.

L'agent ne connaît que l'API centrale (jeton de worker). Les moteurs sont des « adaptateurs »
(fonctions `run(task, report) -> résultat`) ; aucun accès à la base, aucune clé fournisseur.
Il renouvelle le bail pendant l'exécution, applique l'annulation demandée par l'application
et ne réclame jamais plus de tâches que sa capacité.
"""
from __future__ import annotations

import threading
import time


class Cancelled(Exception):
    """Levée par un adaptateur qui constate que l'annulation a été demandée."""


class WorkerAgent:
    def __init__(self, client, adapters, capacity=1, poll_seconds=2.0, beat_seconds=15.0, vram_probe=None):
        self.client = client            # httpx.Client déjà configuré (base_url + jeton de worker)
        self.adapters = adapters        # {"qwen": fonction, ...}
        self.capacity = capacity
        self.poll = poll_seconds
        self.beat = beat_seconds
        self.vram_probe = vram_probe or (lambda: {})
        self.stop = threading.Event()
        self._slots = threading.Semaphore(capacity)
        self._threads = []

    # -- présence --------------------------------------------------------------
    def heartbeat(self):
        self.client.post("/v1/worker/heartbeat", json=self.vram_probe())

    # -- exécution d'une tâche ---------------------------------------------------
    def execute(self, task):
        tid = task["id"]
        state = {"cancel": False}
        done = threading.Event()

        def keepalive():
            while not done.wait(self.beat):
                try:
                    r = self.client.post("/v1/worker/tasks/%s/progress" % tid, json={})
                    if r.status_code == 200 and r.json().get("cancel_requested"):
                        state["cancel"] = True
                except Exception:
                    pass  # un incident réseau bref ne doit pas interrompre le calcul

        pulse = threading.Thread(target=keepalive, daemon=True)
        pulse.start()

        def report(progress=None, stage=None):
            r = self.client.post("/v1/worker/tasks/%s/progress" % tid, json={"progress": progress, "stage": stage})
            if r.status_code == 200 and r.json().get("cancel_requested"):
                state["cancel"] = True
            if state["cancel"]:
                raise Cancelled()

        try:
            adapter = self.adapters.get(task["engine"])
            if adapter is None:
                raise RuntimeError("Moteur non pris en charge par ce worker : %s" % task["engine"])
            result = adapter(task, report)
            if state["cancel"]:
                raise Cancelled()
            self.client.post("/v1/worker/tasks/%s/complete" % tid, json={"result": result})
        except Cancelled:
            # une annulation est acquittée comme un échec non rejouable : l'orchestrateur la clôt « annulée »
            self.client.post("/v1/worker/tasks/%s/fail" % tid, json={"error": "annulée", "retryable": False})
        except Exception as exc:  # noqa: BLE001 — le détail technique ne remonte pas aux applications
            self.client.post("/v1/worker/tasks/%s/fail" % tid,
                             json={"error": ("%s: %s" % (type(exc).__name__, exc))[:500], "retryable": True})
        finally:
            done.set()
            pulse.join(timeout=1)
            self._slots.release()

    # -- boucle ------------------------------------------------------------------
    def step(self):
        """Une itération : réclame une tâche si un emplacement est libre. Retourne True si du travail a été lancé."""
        if not self._slots.acquire(blocking=False):
            return False
        try:
            response = self.client.post("/v1/worker/claim")
            task = response.json().get("task") if response.status_code == 200 else None
        except Exception:
            task = None
        if not task:
            self._slots.release()
            return False
        thread = threading.Thread(target=self.execute, args=(task,), daemon=True)
        self._threads.append(thread)
        thread.start()
        return True

    def run_forever(self):
        last_beat = 0.0
        while not self.stop.is_set():
            now = time.monotonic()
            if now - last_beat >= self.beat:
                try:
                    self.heartbeat()
                except Exception:
                    pass
                last_beat = now
            if not self.step():
                self.stop.wait(self.poll)

    def drain(self, timeout=30):
        for t in list(self._threads):
            t.join(timeout)
