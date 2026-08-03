#!/usr/bin/env bash
# SWE-bench with hands: mini-swe-agent (Docker /testbed) + ZeusCode brain.
# DJARVIS browser is NOT this — coding loop is mini-swe.
#
# Usage:
#   ./backend/scripts/world_bench/run_swebench_mini_zeus.sh
#   SUBSET=full SLICE=0:5 ./backend/scripts/world_bench/run_swebench_mini_zeus.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="${OUT:-$ROOT/_bmad-output/implementation-artifacts/world-bench/swebench/mini_agent}"
KEY_FILE="${KEY_FILE:-/tmp/zeus_bench.key}"
BASE="${ZEUS_PERF_BASE:-http://127.0.0.1:8080}"
SUBSET="${SUBSET:-full}"
SPLIT="${SPLIT:-test}"
SLICE="${SLICE:-0:5}"
WORKERS="${WORKERS:-1}"
# Exercise the adaptive ZeusCode crew unless a solo comparison is explicit.
MODEL="${MODEL:-openai/zeuscode}"
PY="$ROOT/.venv/bin/python"
MINI="$ROOT/.venv/bin/mini-extra"
# Builtin name resolves inside mini-extra (avoid importing minisweagent in bash —
# import prints a version banner that corrupts paths).
CFG_DEFAULT="swebench.yaml"
CFG_ZEUS="$ROOT/backend/scripts/world_bench/mini_swe_zeus.yaml"

export DOCKER_HOST="${DOCKER_HOST:-unix://${HOME}/.colima/default/docker.sock}"
export PATH="${ROOT}/.venv/bin:${HOME}/.local/bin:/opt/homebrew/bin:$PATH"
export OPENAI_API_KEY="$(tr -d '\n' <"$KEY_FILE")"
export OPENAI_BASE_URL="${BASE%/}/v1"
export OPENAI_API_BASE="$OPENAI_BASE_URL"
# zeuscode has no litellm price row — required or agent dies after first reply
export MSWEA_COST_TRACKING="${MSWEA_COST_TRACKING:-ignore_errors}"
# bash + set -u: empty array expand is "unbound" — build argv instead.
MINI_ARGS=(
  swebench
  -c "$CFG_DEFAULT"
  -c "$CFG_ZEUS"
  -m "$MODEL"
  --subset "$SUBSET"
  --split "$SPLIT"
  --slice "$SLICE"
  -w "$WORKERS"
  --environment-class docker
  -o "$OUT"
)
if [[ "${REDO:-1}" == "1" ]]; then
  MINI_ARGS+=(--redo-existing)
fi

mkdir -p "$OUT"
echo "[mini-swe] health $BASE"
curl -sS -m 5 "$BASE/health" | head -c 200; echo
echo "[mini-swe] subset=$SUBSET split=$SPLIT slice=$SLICE model=$MODEL redo=${REDO:-1} → $OUT"

"$MINI" "${MINI_ARGS[@]}" \
  2>&1 | tee "$OUT/run_${SUBSET}_${SLICE//:/-}.log"

echo "[mini-swe] done. preds (if any): $OUT/preds.json"
if [[ -f "$OUT/preds.json" ]]; then
  echo "[mini-swe] local eval tip:"
  echo "  cd $ROOT/.cache/world_bench/SWE-bench && .venv/bin/python -m swebench.harness.run_evaluation \\"
  echo "    --dataset_name princeton-nlp/SWE-bench --predictions_path $OUT/preds.json \\"
  echo "    --max_workers 3 --run_id zeus_mini_${SUBSET}"
fi
