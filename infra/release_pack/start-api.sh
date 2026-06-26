#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "Python virtual environment not found. Run ./setup.sh first." >&2
  exit 1
fi

eval "$("./.venv/bin/python" ./scripts/prepare_release_instance.py --root . --sync-settings --format shell)"

if [ -z "${DAS_BOOTSTRAP_ADMIN_PASSWORD:-}" ]; then
  echo "Using default bootstrap admin password 'admin123'. Set DAS_BOOTSTRAP_ADMIN_PASSWORD before first start." >&2
  export DAS_BOOTSTRAP_ADMIN_PASSWORD="admin123"
fi

"./.venv/bin/python" ./api_start.py
