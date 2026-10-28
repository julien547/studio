#!/usr/bin/env bash
set -euo pipefail
export PIP_CACHE_DIR=/tmp/doemo-pip-cache
export UV_CACHE_DIR=/tmp/doemo-uv-cache
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$script_dir/inventory.py" --require-runpod
mkdir -p /tmp/doemo-pip-cache /tmp/doemo-uv-cache
# Logs stay on the persistent volume; never overwrite archives or existing venvs.
mkdir -p /workspace/doemo-studio/exports/bootstrap-logs
log_file="/workspace/doemo-studio/exports/bootstrap-logs/$(date -u +%Y%m%dT%H%M%S)-$$.jsonl"
python3 "$script_dir/restore.py" --apply --include-service | tee "$log_file"
python3 "$script_dir/audit.py"
# Service runtime is separate from the three model venvs. Install it once after code review.
: "${DOEMO_MODELS_CONFIG:?Set local model configuration}"
: "${DOEMO_OVH_PUBLIC_KEY:?Set OVH public verification key path}"
export DOEMO_ENGINE_RUNNER="$script_dir/engine_runner.py"
exec /opt/doemo-service-venv/bin/python -m uvicorn doemo_reconstruction.ai_service.worker:app_factory --factory --host 0.0.0.0 --port 8009 --workers 1 --limit-concurrency 8
