"""Choix de la prochaine tâche : priorités, vieillissement, équité.

Une tâche éligible reçoit un score ; la plus haute est servie en premier.

  score = base(kind) + 5 × priorité + âge_en_s × vieillissement(kind) − pénalité d'équité

* Les analyses interactives passent devant les lots et les entraînements (base élevée).
* Le vieillissement est plus rapide pour les lots et entraînements : ils finissent par
  passer devant des demandes interactives récentes et ne sont jamais affamés.
* La pénalité d'équité réduit le score d'une application ou d'un utilisateur qui occupe
  déjà des emplacements, pour répartir la charge sans l'interdire.
* Plafond dur : une application n'occupe jamais plus de `max_running` emplacements.
"""
from __future__ import annotations

BASE = {"interactive": 1000.0, "batch": 100.0, "training": 10.0}
AGING_PER_SECOND = {"interactive": 1.0, "batch": 3.0, "training": 3.0}
PRIORITY_WEIGHT = 5.0
APP_RUNNING_PENALTY = 40.0
USER_RUNNING_PENALTY = 80.0
RECENT_USAGE_PENALTY_PER_SECOND = 0.02  # temps de calcul récent (10 min) de l'application


def score(task, now, app_running, user_running, app_recent_seconds=0.0):
    age = max(0.0, now - task["created"])
    return (BASE[task["kind"]] + PRIORITY_WEIGHT * task["priority"]
            + age * AGING_PER_SECOND[task["kind"]]
            - APP_RUNNING_PENALTY * app_running
            - USER_RUNNING_PENALTY * user_running
            - RECENT_USAGE_PENALTY_PER_SECOND * app_recent_seconds)


def pick(candidates, now, running_by_app, running_by_user, caps, recent_by_app):
    """Retourne la meilleure tâche éligible, ou None."""
    best, best_key = None, None
    for task in candidates:
        app = task["app_id"]
        if running_by_app.get(app, 0) >= caps.get(app, 1):
            continue  # plafond de l'application atteint
        user_key = (app, task["user_login"])
        s = score(task, now, running_by_app.get(app, 0), running_by_user.get(user_key, 0),
                  recent_by_app.get(app, 0.0))
        key = (s, -task["created"])  # à score égal, la plus ancienne d'abord
        if best_key is None or key > best_key:
            best, best_key = task, key
    return best
