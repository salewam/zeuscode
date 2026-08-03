#!/usr/bin/env bash
# Run DRACO outside Cursor harness so long jobs are not aborted mid-flight.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
OUT="_bmad-output/implementation-artifacts/world-bench/draco"
STATUS="_bmad-output/implementation-artifacts/world-bench/status"
mkdir -p "$OUT" "$STATUS"
LIMIT="${1:-20}"
TAG="${2:-research_v7}"
CKPT="$OUT/inference_checkpoint_limit${LIMIT}_${TAG}.jsonl"
LOG="$OUT/run_limit${LIMIT}_${TAG}.log"
PIDFILE="$STATUS/draco_limit${LIMIT}_${TAG}.pid"
KEYFILE="${ZEUS_BENCH_KEY_FILE:-/tmp/zeus_bench.key}"

if [[ ! -f "$KEYFILE" ]]; then
  echo "missing key: $KEYFILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a
export PYTHONPATH=backend
export FUSION_RESEARCH_CREW_ENABLED=true
export WEB_RESEARCH_ENABLED=true
export PYTHONUNBUFFERED=1

if ! curl -sf -m 3 http://127.0.0.1:8080/health >/dev/null; then
  echo "API down on :8080 — start uvicorn first" >&2
  exit 1
fi

CMD=(
  .venv/bin/python -u backend/scripts/world_bench/run_draco_zeus.py
  --base http://127.0.0.1:8080
  --key "$(tr -d '\n' <"$KEYFILE")"
  --limit "$LIMIT"
  --timeout 1500
  --judge-timeout 120
  --judge-model deepseek-v4-flash
  --max-criteria 12
  --judge-workers 6
  --checkpoint "$CKPT"
)
if [[ -f "$CKPT" ]]; then
  CMD+=(--resume)
  echo "resuming from $CKPT"
fi

nohup "${CMD[@]}" >"$LOG" 2>&1 &
echo $! | tee "$PIDFILE"
echo "log=$LOG"
echo "tail -f $LOG"
