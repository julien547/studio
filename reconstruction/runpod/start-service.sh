#!/usr/bin/env bash
set -euo pipefail
# Include this foreground command in the EXISTING image supervisor. Never restore
# environments, install packages, download weights, or start/stop a Pod here.
service_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
: "${RUNPOD_POD_ID:?RUNPOD_POD_ID must come from the current RunPod container}"
export DOEMO_MODELS_CONFIG="${DOEMO_MODELS_CONFIG:-/workspace/doemo-studio/config/models.json}"
export DOEMO_OVH_PUBLIC_KEY="${DOEMO_OVH_PUBLIC_KEY:-/workspace/doemo-studio/config/ovh-worker-public.pem}"
export DOEMO_RUNPOD_RESULTS="${DOEMO_RUNPOD_RESULTS:-/workspace/doemo-studio/exports/ai-jobs}"
export DOEMO_ENGINE_RUNNER="$service_root/runpod/engine_runner.py"
exec /opt/doemo-service-venv/bin/python "$service_root/runpod/serve_test.py" "$@"
