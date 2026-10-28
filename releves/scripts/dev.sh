#!/usr/bin/env bash
set -euo pipefail
umask 0077
repo=$(cd "$(dirname "$0")/../.." && pwd)
venv=${DOEMO_RELEVES_VENV:-/workspace/.venvs/studio-releves}
export DOEMO_RELEVES_DATA=${DOEMO_RELEVES_DATA:-/workspace/studio-releves-data}
run_dir=${DOEMO_RELEVES_RUN:-/workspace/.local/share/studio-releves/run}
public_dir=${DOEMO_RELEVES_PUBLIC:-/workspace/.local/share/studio-releves/web}
export DOEMO_RELEVES_SOCKET="$run_dir/backend.sock"
export DOEMO_RELEVES_DIST="$repo/releves/dist"
php_bin=${DOEMO_PHP:-/workspace/.local/bin/php}
port=${DOEMO_RELEVES_PORT:-8081}
mkdir -p "$run_dir" "$public_dir/releves"
if test -e "$DOEMO_RELEVES_SOCKET"; then
  echo 'Le socket existe déjà. Vérifier le service en cours avant de le supprimer ou redémarrer.' >&2
  exit 1
fi
for file in index.html style.css login.js favicon.svg logo-studio.png api entrainement; do ln -sfn "$repo/$file" "$public_dir/$file"; done
ln -sfn "$repo/releves/index.php" "$public_dir/releves/index.php"
ln -sfn "$repo/releves/dist/assets" "$public_dir/releves/assets"
"$venv/bin/uvicorn" doemo_releves.api:app_factory --factory --uds "$DOEMO_RELEVES_SOCKET" --no-access-log &
backend_pid=$!
cleanup(){ kill "$backend_pid" 2>/dev/null || true; wait "$backend_pid" 2>/dev/null || true; rm -f "$DOEMO_RELEVES_SOCKET"; }
trap cleanup EXIT INT TERM
for attempt in $(seq 1 50); do test -S "$DOEMO_RELEVES_SOCKET" && break; kill -0 "$backend_pid"; sleep .1; done
test -S "$DOEMO_RELEVES_SOCKET"
chmod 600 "$DOEMO_RELEVES_SOCKET"
"$php_bin" -d upload_max_filesize=520M -d post_max_size=535M -d memory_limit=768M -d max_execution_time=240 -S "127.0.0.1:$port" -t "$public_dir" "$repo/releves/dev-router.php"
