#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ ! -x ".venv/bin/python" ]; then
  "$PYTHON_BIN" -m venv .venv
fi

".venv/bin/python" -m pip install --upgrade pip setuptools wheel
".venv/bin/python" -m pip install -r ./apps/das_core/requirements.hosted.txt
".venv/bin/python" -m pip install -r ./apps/api_gateway/requirements.txt

echo "Runtime environment is ready."
