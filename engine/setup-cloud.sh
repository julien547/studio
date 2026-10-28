#!/usr/bin/env bash
set -euo pipefail
cd /workspace/studio
test -f engine/pyproject.toml
python3 -m venv /workspace/.venvs/studio-pdf
/workspace/.venvs/studio-pdf/bin/python -m pip install --cache-dir /workspace/.cache/pip -r engine/requirements.lock
/workspace/.venvs/studio-pdf/bin/python -m pip install --cache-dir /workspace/.cache/pip --no-deps -e ./engine
/workspace/.venvs/studio-pdf/bin/python -m pytest -q engine/tests
/workspace/.venvs/studio-pdf/bin/doemo-pdf --help
