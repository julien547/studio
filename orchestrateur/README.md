# Orchestrateur IA DOEMO

File de tâches centrale pour Qwen, PaddleOCR, RTMDet et IA Murs : priorités, équité entre
applications et utilisateurs, plafonds, doublons, annulation, relance, registre de modèles versionné.

Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) pour l'architecture, l'état d'avancement et les décisions en attente.

```sh
python3 -m venv .venv && .venv/bin/pip install -e . pytest httpx
.venv/bin/python -m pytest -q
```

Variables : `DOEMO_ORCH_DB` (base SQLite), `DOEMO_ORCH_ADMIN_TOKEN` (≥ 32 caractères, jeton d'administration).
