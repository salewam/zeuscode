#!/usr/bin/env bash
# Maximal world-bench against ZeusCode power path.
# Requires: API :8080, /tmp/zeus_bench.key, Colima docker for SWE/TB.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$ROOT/_bmad-output/implementation-artifacts/world-bench"
KEY="$(tr -d '\n' </tmp/zeus_bench.key)"
export DOCKER_HOST="unix://${HOME}/.colima/default/docker.sock"
export PATH="${HOME}/.local/bin:/opt/homebrew/bin:$PATH"
export OPENAI_API_KEY="$KEY"
export ZEUS_PERF_BASE="${ZEUS_PERF_BASE:-http://127.0.0.1:8080}"
export ZEUS_PERF_KEY="$KEY"
PY="$ROOT/.venv/bin/python"
mkdir -p "$OUT"/{draco,livecodebench,swebench,terminal,status}
cd "$ROOT"

echo "[all] health"
curl -sS -m 5 "$ZEUS_PERF_BASE/health" | head -c 200; echo
colima status 2>&1 | head -3 || { echo "Colima down — starting"; colima start --cpu 4 --memory 8; }

# 1) DRACO full-ish (100 tasks, 25 criteria, expensive)
echo "[all] DRACO limit=100 → background"
nohup env PYTHONPATH=backend "$PY" backend/scripts/world_bench/run_draco_zeus.py \
  --base "$ZEUS_PERF_BASE" --key "$KEY" \
  --limit 0 --max-criteria 25 --judge-model gemini-3.1-pro --timeout 300 \
  >"$OUT/draco/run_full.log" 2>&1 &
echo $! >"$OUT/status/draco.pid"

# 2) LiveCodeBench n=40
echo "[all] LiveCodeBench n=40 → background"
nohup env PYTHONPATH=backend "$PY" backend/scripts/world_bench/run_livecodebench_zeus.py \
  --base "$ZEUS_PERF_BASE" --key "$KEY" --limit 40 --timeout 180 \
  >"$OUT/livecodebench/run_n40.log" 2>&1 &
echo $! >"$OUT/status/lcb.pid"

# 3) SWE-bench Lite n=10
echo "[all] SWE-bench Lite n=10 → background"
nohup env PYTHONPATH=backend DOCKER_HOST="$DOCKER_HOST" "$PY" \
  backend/scripts/world_bench/run_swebench_zeus.py \
  --base "$ZEUS_PERF_BASE" --key "$KEY" --limit 10 --max-workers 3 \
  --run-id zeus_swe_lite10 \
  >"$OUT/swebench/run_n10.log" 2>&1 &
echo $! >"$OUT/status/swe.pid"

# 4) Terminal-Bench n=10
echo "[all] Terminal-Bench n=10 → background"
nohup env DOCKER_HOST="$DOCKER_HOST" OPENAI_API_KEY="$KEY" PATH="$PATH" \
  tb run \
  --dataset 'terminal-bench-core==0.1.1' \
  --agent terminus-2 \
  --model openai/zeuscode \
  --agent-kwarg api_base=http://127.0.0.1:8080/v1 \
  --n-tasks 10 --n-concurrent 1 \
  --output-path "$OUT/terminal/runs" \
  --run-id zeus_tb_n10 \
  --cleanup \
  >"$OUT/terminal/run_n10.log" 2>&1 &
echo $! >"$OUT/status/tb.pid"

# 5) Internal power suite (our structure oracle) ×3
echo "[all] Zeus power_cases live ×3 → background"
nohup env PYTHONPATH=backend "$PY" backend/scripts/bench_zeuscode_power.py \
  --live --base "$ZEUS_PERF_BASE" --key "$KEY" --runs 3 --timeout 300 \
  --out "$OUT/status/live_power_suite.json" \
  >"$OUT/status/live_power_suite.log" 2>&1 &
echo $! >"$OUT/status/power.pid"

cat >"$OUT/status/LAUNCHED.md" <<EOF
# Maximal launch $(date -u +%Y-%m-%dT%H:%M:%SZ)

PIDs:
- DRACO: $(cat "$OUT/status/draco.pid")
- LCB: $(cat "$OUT/status/lcb.pid")
- SWE: $(cat "$OUT/status/swe.pid")
- TB: $(cat "$OUT/status/tb.pid")
- power_cases: $(cat "$OUT/status/power.pid")

Logs under \`$OUT/*/run_*.log\` and \`$OUT/status/\`.
EOF
echo "[all] launched — see $OUT/status/LAUNCHED.md"
