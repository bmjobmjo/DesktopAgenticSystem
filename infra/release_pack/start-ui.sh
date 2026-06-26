#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "Python virtual environment not found. Run ./setup.sh first." >&2
  exit 1
fi

eval "$("./.venv/bin/python" ./scripts/prepare_release_instance.py --root . --sync-settings --format shell)"

"./.venv/bin/python" ./scripts/serve_oasis_ui.py --root ./apps/ui_web/dist --host "${OASIS_UI_HOST}" --port "${OASIS_UI_PORT}"
