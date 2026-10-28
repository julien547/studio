#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
venv=${DOEMO_RELEVES_VENV:-/workspace/.venvs/studio-releves}
python3 -m venv "$venv"
"$venv/bin/python" -m pip install -r "$repo/releves/backend/requirements.lock"
"$venv/bin/python" -m pip install --no-deps -e "$repo/releves/backend"
"$venv/bin/python" -m pip check
cd "$repo/releves/web"
npm ci
npm run build
