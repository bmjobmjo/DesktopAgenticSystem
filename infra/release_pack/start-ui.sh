#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "Python virtual environment not found. Run ./setup.sh first." >&2
  exit 1
fi

eval "$("./.venv/bin/python" ./scripts/prepare_release_instance.py --root . --sync-settings --format shell)"

UI_HOST="${OASIS_UI_HOST:-127.0.0.1}"
UI_PORT="${OASIS_UI_PORT:-8080}"

exec ./.venv/bin/python ./scripts/serve_oasis_ui.py --root ./apps/ui_web/dist --host "$UI_HOST" --port "$UI_PORT"
