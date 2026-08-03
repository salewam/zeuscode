#!/usr/bin/env bash
# Detached SWE full 0:10 resume until preds.json has 10 entries.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
set -a && source .env && set +a

export PATH="${ROOT}/.venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export DOCKER_HOST="${DOCKER_HOST:-unix://${HOME}/.colima/default/docker.sock}"

OUT="${OUT:-$ROOT/_bmad-output/implementation-artifacts/world-bench/swebench/mini_agent}"
LOG="$OUT/autoresume_full10.log"
PIDFILE="$OUT/autoresume_full10.pid"
mkdir -p "$OUT"
echo $$ >"$PIDFILE"

ensure_api() {
  if curl -sS -m 2 http://127.0.0.1:8080/health >/dev/null; then return 0; fi
  echo "[$(date -u +%H:%M:%S)] restarting API" | tee -a "$LOG"
  nohup env PYTHONPATH=backend \
    A6_API_KEY="$A6_API_KEY" A6_API_KEY_FALLBACK="${A6_API_KEY_FALLBACK:-}" \
    A6_BASE_URL="${A6_BASE_URL:-https://a6api.com/v1}" A6_ENABLED=true \
    A6_PRIMARY_COOLDOWN_S="${A6_PRIMARY_COOLDOWN_S:-900}" \
    A6_PROBE_MODEL="${A6_PROBE_MODEL:-claude-haiku-4-5}" \
    "$ROOT/.venv/bin/uvicorn" app.main:app --app-dir backend --host 127.0.0.1 --port 8080 \
    >>/tmp/zeus_api.log 2>&1 &
  for _ in $(seq 1 40); do
    curl -sS -m 2 http://127.0.0.1:8080/health >/dev/null && return 0
    sleep 1
  done
  return 1
}

preds_n() {
  python3 -c "import json;from pathlib import Path;p=Path('$OUT/preds.json');print(len(json.loads(p.read_text())) if p.exists() else 0)"
}

round=0
while true; do
  n="$(preds_n)"
  echo "[$(date -u +%H:%M:%S)] round=$round preds=$n/10" | tee -a "$LOG"
  if [[ "$n" -ge 10 ]]; then
    echo DONE | tee -a "$LOG"
    break
  fi
  ensure_api || { sleep 15; continue; }
  if pgrep -f 'mini-extra swebench' >/dev/null; then
    sleep 120
    continue
  fi
  round=$((round + 1))
  echo "[$(date -u +%H:%M:%S)] launch REDO=0" | tee -a "$LOG"
  MODEL=openai/claude-opus-4-6 SUBSET=full SLICE=0:10 WORKERS=1 REDO=0 \
    "$ROOT/backend/scripts/world_bench/run_swebench_mini_zeus.sh" >>"$LOG" 2>&1 || true
  echo "[$(date -u +%H:%M:%S)] mini exited preds=$(preds_n)" | tee -a "$LOG"
  docker ps -q --filter 'name=minisweagent' | xargs -r docker kill 2>/dev/null || true
  sleep 5
done
rm -f "$PIDFILE"
