#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "Python virtual environment not found. Run ./setup.sh first." >&2
  exit 1
fi

LOG_DIR="$("./.venv/bin/python" ./scripts/prepare_release_instance.py --root . --sync-settings --format json | "./.venv/bin/python" -c "import json,sys; print(json.loads(sys.stdin.read())['logs_path'])")"
mkdir -p "$LOG_DIR"

./start-ui.sh > "$LOG_DIR/ui.out.log" 2> "$LOG_DIR/ui.err.log" &
UI_PID=$!
echo "$UI_PID" > "$LOG_DIR/ui.pid"

exec ./start-api.sh
