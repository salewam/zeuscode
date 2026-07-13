#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data
export PYTHONPATH="$ROOT/backend"
exec "$ROOT/.venv/bin/uvicorn" app.main:app --app-dir "$ROOT/backend" --host "${HOST:-127.0.0.1}" --port "${PORT:-8080}" --reload
