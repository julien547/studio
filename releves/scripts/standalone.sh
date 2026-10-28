#!/usr/bin/env bash
set -euo pipefail
umask 0077
repo=$(cd "$(dirname "$0")/../.." && pwd)
python=${DOEMO_RELEVES_PYTHON:-/workspace/.venvs/studio-releves/bin/python}
export DOEMO_RELEVES_DATA=${DOEMO_RELEVES_DATA:-/var/lib/doemo-studio/releves}
export DOEMO_RELEVES_DIST=${DOEMO_RELEVES_DIST:-$repo/releves/dist}
port=${DOEMO_STUDIO_PORT:-8082}
export DOEMO_PUBLIC_ORIGIN=${DOEMO_PUBLIC_ORIGIN:-http://127.0.0.1:$port}
if ! test -f "$DOEMO_RELEVES_DIST/index.html"; then
  echo 'Construire le frontend : npm --prefix releves/web run build' >&2
  exit 1
fi
# Complete schema migrations before the queue worker starts.
"$python" -c 'import os; from doemo_releves.store import Store; Store(os.environ["DOEMO_RELEVES_DATA"])'
"$python" -m doemo_releves.queue &
worker_pid=$!
cleanup(){ kill "$worker_pid" 2>/dev/null || true; wait "$worker_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
"$python" -m uvicorn doemo_releves.auth:standalone --factory --host 127.0.0.1 --port "$port" --no-access-log
