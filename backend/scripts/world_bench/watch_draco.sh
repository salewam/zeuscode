#!/usr/bin/env bash
# Watchdog: monitor DRACO100 tmux job, restart if dead, log pulse.
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$ROOT/_bmad-output/implementation-artifacts/world-bench/draco"
STATUS="$ROOT/_bmad-output/implementation-artifacts/world-bench/status"
KEY="$(tr -d '\n' </tmp/zeus_bench.key)"
LOG="$OUT/watchdog.log"
PULSE="$STATUS/DRACO_PULSE.md"
mkdir -p "$OUT" "$STATUS"

start_draco() {
  tmux kill-session -t draco100 2>/dev/null || true
  sleep 1
  tmux new-session -d -s draco100 "cd '$ROOT' && \
    PYTHONUNBUFFERED=1 PYTHONPATH=backend \
    '$ROOT/.venv/bin/python' -u backend/scripts/world_bench/run_draco_zeus.py \
    --base http://127.0.0.1:8080 \
    --key '$KEY' \
    --limit 0 --max-criteria 0 \
    --judge-model gemini-3.1-pro \
    --timeout 360 --judge-timeout 120 \
    --resume \
    2>&1 | tee -a '$OUT/run_full100.log'"
  echo "$(date -u +%H:%M:%SZ) RESTARTED draco100" | tee -a "$LOG"
}

pulse() {
  local alive=0
  pgrep -f 'run_draco_zeus.py' >/dev/null && alive=1
  local n=0 mean="—"
  if [[ -f "$OUT/inference_checkpoint.jsonl" ]]; then
    n=$(wc -l < "$OUT/inference_checkpoint.jsonl" | tr -d ' ')
    mean=$("$ROOT/.venv/bin/python" - <<'PY'
import json
from pathlib import Path
p=Path("/Users/money/Desktop/Projects/ultra-mode-mvp/_bmad-output/implementation-artifacts/world-bench/draco/inference_checkpoint.jsonl")
rows=[json.loads(l) for l in p.read_text().splitlines() if l.strip()]
sc=[float(r["score_pct"]) for r in rows if r.get("score_pct") is not None]
print(f"{sum(sc)/len(sc):.1f}" if sc else "—")
PY
)
  fi
  local last
  last=$(tail -5 "$OUT/run_full100.log" 2>/dev/null | tr '\n' ' ' | cut -c1-200)
  local api=DOWN
  curl -sS -m 3 http://127.0.0.1:8080/health >/dev/null 2>&1 && api=OK
  cat >"$PULSE" <<EOF
# DRACO pulse $(date '+%Y-%m-%d %H:%M:%S %z')

- process: $([[ $alive -eq 1 ]] && echo ALIVE || echo DEAD)
- tmux: $(tmux has-session -t draco100 2>/dev/null && echo OK || echo DEAD)
- api: $api
- done: **$n / 100**
- mean: **${mean}%**
- last log: \`$last\`

EOF
  echo "$(date -u +%H:%M:%SZ) alive=$alive done=$n/100 mean=$mean api=$api" | tee -a "$LOG"
  [[ $alive -eq 1 ]]
}

echo "$(date -u +%H:%M:%SZ) watchdog start" | tee -a "$LOG"
# ensure running
pulse || start_draco

while true; do
  sleep 60
  if ! pulse; then
    echo "$(date -u +%H:%M:%SZ) DEAD → restart" | tee -a "$LOG"
    # ensure API up
    if ! curl -sS -m 3 http://127.0.0.1:8080/health >/dev/null; then
      echo "$(date -u +%H:%M:%SZ) API down — start uvicorn" | tee -a "$LOG"
      cd "$ROOT" && set -a && source .env && set +a
      nohup env PYTHONPATH=backend "$ROOT/.venv/bin/uvicorn" app.main:app \
        --app-dir backend --host 127.0.0.1 --port 8080 \
        >>"$STATUS/api_watchdog.log" 2>&1 </dev/null &
      sleep 3
    fi
    start_draco
    sleep 5
    pulse || true
  fi
  # stop watchdog when complete
  if [[ -f "$OUT/draco_zeus_full100.json" ]]; then
    echo "$(date -u +%H:%M:%SZ) FULL COMPLETE" | tee -a "$LOG"
    break
  fi
done
