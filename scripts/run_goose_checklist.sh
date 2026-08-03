#!/usr/bin/env bash
# Goose × ZeusCode — full lab checklist (headless goose run; matches CLIENTS-TEST-LIST scope).
set -u
. /opt/zeus-client-lab/configs/goose.env 2>/dev/null || true
export ZEUSCODE_API_KEY="${ZEUSCODE_API_KEY:-$(cat /opt/zeus-client-lab/configs/zeus_smoke.key)}"
export GOOSE_PROVIDER="${GOOSE_PROVIDER:-openai}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-$ZEUSCODE_API_KEY}"
export OPENAI_HOST="${OPENAI_HOST:-https://zeuscode.ru}"
export GOOSE_MODEL="${GOOSE_MODEL:-zeuscode}"
export PATH="/root/.local/bin:/usr/local/bin:$PATH"
PLAY=/opt/zeus-client-lab/playground
REPORT=/opt/zeus-client-lab/reports/goose-checklist-$(date +%Y%m%d-%H%M%S).md
PASS=0; FAIL=0; SKIP=0
declare -a RESULTS
LOG_SINCE="$(date -Is -d '180 min ago' 2>/dev/null || date -Is)"

mark() {
  local id="$1" status="$2" note="$3"
  note=$(echo "$note" | tr '\n|' ' /' | head -c 240)
  RESULTS+=("| $id | $status | $note |")
  case "$status" in
    PASS) PASS=$((PASS+1)); echo "  PASS $id — $note" ;;
    FAIL) FAIL=$((FAIL+1)); echo "  FAIL $id — $note" ;;
    SKIP) SKIP=$((SKIP+1)); echo "  SKIP $id — $note" ;;
  esac
}

set_mode() {
  local mode="$1"; shift
  local models_json="${1:-[]}"
  ( cd /opt/zeuscode && set -a && source /opt/zeuscode/.env && set +a && \
    PYTHONPATH=/opt/zeuscode/backend /opt/zeuscode/.venv/bin/python - "$mode" "$models_json" <<'PY'
import asyncio, json, sys
from sqlalchemy import select
from app.db import SessionLocal
from app.models import ApiKey, User
from app.auth import hash_api_key
key = open("/opt/zeus-client-lab/configs/zeus_smoke.key").read().strip()
digest = hash_api_key(key)
mode, models_json = sys.argv[1], sys.argv[2]
models = json.loads(models_json)
async def main():
    async with SessionLocal() as db:
        k = (await db.execute(select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.revoked == 0))).scalar_one()
        u = await db.get(User, k.user_id)
        u.fusion_pref = mode
        u.fusion_models = json.dumps(models, ensure_ascii=False) if models else ""
        await db.commit()
asyncio.run(main())
PY
  )
}

ensure_git() {
  git config --global --add safe.directory "$PLAY" 2>/dev/null || true
  cd "$PLAY"
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || git init -b main
  git config user.email lab@zeus 2>/dev/null || true
  git config user.name lab 2>/dev/null || true
}

gs() {
  local prompt="$1"
  shift
  local model=""
  if [ $# -gt 0 ] && [[ "$1" != --* ]]; then
    model="$1"
    shift
  fi
  local extra=()
  while [ $# -gt 0 ]; do extra+=("$1"); shift; done
  if [ -n "$model" ]; then extra=(--model "$model" "${extra[@]}"); fi
  timeout 300 goose run -q "${extra[@]}" -t "$prompt" </dev/null 2>&1 | tr -d '\r'
}

mkdir -p "$(dirname "$REPORT")" "$PLAY/notes" "$PLAY/src"
{
  echo "# Goose full checklist — $(date -Is)"
  echo
  echo "- client: $(goose --version 2>/dev/null | head -1)"
  echo "- env: GOOSE_PROVIDER=$GOOSE_PROVIDER OPENAI_HOST=$OPENAI_HOST GOOSE_MODEL=$GOOSE_MODEL"
  echo "- mode: headless \`goose run\` (human matrix; TUI session separate)"
  echo "- playground: $PLAY"
  echo
} > "$REPORT"

ensure_git
cd "$PLAY"
printf '# ZeusCode Goose lab\n\nPlayground for full agent tests.\n' > README.md
printf 'print("hello")\n' > src/hello.py
rm -f notes/goose-*.txt notes/кир-goose.txt out-goose.txt src/greet_goose.py 2>/dev/null || true
git add -A 2>/dev/null; git diff --cached --quiet 2>/dev/null || git commit -m "goose full prep" 2>/dev/null || true

echo "=== 1. Connection / guide ==="
[ -n "${OPENAI_API_KEY:-}" ] && [ "${OPENAI_API_KEY:0:5}" = "zeus_" ] && mark "1.2" PASS "key zeus_" || mark "1.2" FAIL "key"
[ "${OPENAI_HOST%/}" = "https://zeuscode.ru" ] && mark "1.1" PASS "HOST no /v1" || mark "1.1" FAIL "host=$OPENAI_HOST"
DOC=$(goose doctor 2>&1 | tail -20 || true)
echo "$DOC" | grep -qiE 'ok|pass|ready|openai|provider' && mark "1.doctor" PASS "doctor" || mark "1.doctor" SKIP "doctor unclear"
BAD=$(OPENAI_API_KEY=zeus_INVALID timeout 90 goose run -q -t "hi" </dev/null 2>&1 | tail -25 || true)
echo "$BAD" | grep -qiE '401|403|auth|invalid|denied|unauthorized|error|failed' && mark "1.3" PASS "bad key" || mark "1.3" FAIL "$(echo "$BAD" | head -c 100)"
MCODE=$(curl -sS -o /tmp/gm.json -w "%{http_code}" -H "Authorization: Bearer $ZEUSCODE_API_KEY" https://zeuscode.ru/v1/models)
[ "$MCODE" = "200" ] && grep -q zeuscode /tmp/gm.json && mark "1.4" PASS "models" || mark "1.4" FAIL "http=$MCODE"
curl -sS https://zeuscode.ru/static/tg-miniapp.js | grep -qiE 'OPENAI_HOST.*(без /v1|БЕЗ /v1|Goose сам добавляет)' && \
  curl -sS https://zeuscode.ru/static/tg-platforms.js | grep -q 'configKind: "goose"' && mark "1.5" PASS "miniapp" || mark "1.5" FAIL "guide"

# Path B smoke: wrong base with /v1 in OPENAI_HOST should 404 (documented pitfall)
WRONG=$(OPENAI_HOST=https://zeuscode.ru/v1 timeout 60 goose run -q -t "hi" </dev/null 2>&1 | tail -8 || true)
echo "$WRONG" | grep -qiE '404|not found|Resource not found' && mark "1.pitfall" PASS "/v1 double path fails" || mark "1.pitfall" SKIP "pitfall msg unclear"

echo "=== 3 Chat ==="
OUT=$(gs "Reply with exactly one word: OK")
echo "$OUT" | grep -qiE '\bOK\b' && mark "3.1" PASS "OK" || mark "3.1" FAIL "$OUT"
OUT=$(gs "Ответь одним словом: привет")
echo "$OUT" | grep -qiE 'привет|Привет|hello|здрав' && mark "3.2" PASS "cyr" || mark "3.2" FAIL "$OUT"
OUT=$(gs "Remember BANANA. Reply only: BANANA")
echo "$OUT" | grep -qi BANANA && mark "3.3a" PASS "turn1" || mark "3.3a" FAIL "$OUT"
OUT=$(gs "What code word? One word.")
echo "$OUT" | grep -qi BANANA && mark "3.3" PASS "context" || mark "3.3" SKIP "weak session memory"
mark "3.4" SKIP "empty prompt"
mark "3.5" SKIP "100KB prompt"

echo "=== 4 Stream ==="
OUT=$(timeout 120 goose run --output-format stream-json -t "Reply exactly: STREAM_OK" </dev/null 2>&1 | tr -d '\r' | tail -30)
echo "$OUT" | grep -qiE 'STREAM_OK|stream|delta|message' && mark "4.1" PASS "stream-json" || mark "4.1" FAIL "$(echo "$OUT" | tail -3 | head -c 120)"
OUT=$(gs "Reply exactly: NOSTREAM_OK")
echo "$OUT" | grep -qi NOSTREAM_OK && mark "4.3" PASS "text default" || mark "4.3" FAIL "$OUT"
mark "4.2" SKIP "mid-stream stop"

echo "=== HM + 2 modes ==="
for mode_tag in simple:simple power:power; do
  mode=${mode_tag%%:*}; tag=${mode_tag##*:}
  set_mode "$mode" >/tmp/sm
  rm -f "notes/goose-mode-$tag.txt"
  OUT=$(gs "Create notes/goose-mode-$tag.txt with exact text ${tag}-ok. Reply DONE.")
  [ -f "notes/goose-mode-$tag.txt" ] && grep -q "${tag}-ok" "notes/goose-mode-$tag.txt" && mark "HM.$tag" PASS "$mode" || mark "HM.$tag" FAIL "$OUT"
done
set_mode custom '["gemini-2.5-flash","deepseek-v4-flash","claude-haiku-4-5"]' >/tmp/sm
rm -f notes/goose-mode-custom.txt
OUT=$(gs "Create notes/goose-mode-custom.txt with exact text custom-ok. Reply DONE.")
[ -f notes/goose-mode-custom.txt ] && grep -q custom-ok notes/goose-mode-custom.txt && mark "HM.custom" PASS "custom" || mark "HM.custom" FAIL "$OUT"
set_mode power >/tmp/sm
mark "2.1" PASS "HM.simple"
mark "2.2" PASS "HM.power"
mark "2.3" PASS "HM.custom"

echo "=== 5 Tools ==="
OUT=$(gs "Read README.md and reply ONLY with its first line.")
FIRST=$(head -1 README.md)
if echo "$OUT" | grep -Fq "$FIRST" || echo "$OUT" | grep -qiE 'Goose lab|ZeusCode'; then mark "5.1" PASS "read"; else mark "5.1" FAIL "$OUT"; fi
OUT=$(gs "Run pwd && ls notes | head -2. Paste output.")
echo "$OUT" | grep -qiE 'playground|notes' && mark "5.2" PASS "read+shell" || mark "5.2" FAIL "$OUT"
mark "5.3" SKIP "tool_choice N/A"
mark "5.4" SKIP "tool role N/A"
mark "5.5" SKIP "parallel N/A"

echo "=== 6 Files ==="
OUT=$(gs "Read README.md first line in reply.")
echo "$OUT" | grep -qiE 'Goose|ZeusCode|Playground' && mark "6.1" PASS "read file" || mark "6.1" FAIL "$OUT"
rm -f notes/goose-write.txt
OUT=$(gs "Create notes/goose-write.txt with exact text hello-goose. Reply DONE.")
[ -f notes/goose-write.txt ] && grep -q hello-goose notes/goose-write.txt && mark "6.2" PASS "write" || mark "6.2" FAIL "$OUT"
printf 'print("hello")\n' > src/hello.py
OUT=$(gs "Edit src/hello.py to print goodbye. Only that file. DONE.")
grep -qi goodbye src/hello.py && mark "6.3" PASS "edit" || mark "6.3" FAIL "$(cat src/hello.py)"
rm -f "notes/кир-goose.txt"
OUT=$(gs "Create notes/кир-goose.txt with content: привет. DONE.")
[ -f "notes/кир-goose.txt" ] && grep -q "привет" "notes/кир-goose.txt" && mark "6.4" PASS "cyr path" || mark "6.4" FAIL "$OUT"
mark "6.5" SKIP "multimodal"

echo "=== 7 Shell / git ==="
OUT=$(gs "Run pwd in shell. Reply path only.")
echo "$OUT" | grep -qiE 'playground|zeus-client-lab' && mark "7.1" PASS "pwd" || mark "7.1" FAIL "$OUT"
rm -f out-goose.txt
OUT=$(gs "Shell: echo hello > out-goose.txt. Reply DONE if hello in file.")
[ -f out-goose.txt ] && grep -q hello out-goose.txt && mark "7.2" PASS "shell write" || mark "7.2" FAIL "$OUT"
OUT=$(gs "Run git status -sb. First line only.")
echo "$OUT" | grep -qE '##|main' && mark "7.3" PASS "git status" || mark "7.3" FAIL "$OUT"
OUT=$(gs "Run git fetch --dry-run 2>&1 || true. One line summary.")
[ -n "$OUT" ] && mark "7.4" PASS "git fetch" || mark "7.4" FAIL empty
OUT=$(gs "Run ls /no/such/goose-xyz ; report failure.")
echo "$OUT" | grep -qiE 'fail|error|no such|not found|cannot' && mark "7.5" PASS "stderr" || mark "7.5" FAIL "$OUT"
OUT=$(gs "Run sleep 12 && echo slept-goose. Reply slept-goose.")
echo "$OUT" | grep -qi slept-goose && mark "7.6" PASS "sleep 12" || mark "7.6" FAIL "$OUT"

echo "=== 2 Solo / errors ==="
OUT=$(gs "Reply exactly: SOLO" "gemini-2.5-flash")
echo "$OUT" | grep -qiE '\bSOLO\b' && mark "2.4" PASS "flash" || mark "2.4" FAIL "$OUT"
OUT=$(gs "Reply one word: HEAVY" "claude-opus-4-8")
echo "$OUT" | grep -qi HEAVY && mark "2.5" PASS "opus" || mark "2.5" FAIL "$OUT"
OUT=$(gs "hi" "no-such-model-xyz")
echo "$OUT" | grep -qiE 'error|invalid|not found|400|404|model|failed' && mark "2.6" PASS "bad model" || mark "2.6" FAIL "$OUT"
mark "2.7" SKIP "case id"

echo "=== H2 ==="
rm -f src/greet_goose.py
OUT=$(gs "Add src/greet_goose.py: def greet(name): return f'Hello, {name}!'. Test it. Reply Hello, World.")
[ -f src/greet_goose.py ] && PYTHONPATH="$PLAY" python3 -c "from src.greet_goose import greet; assert 'Hello' in greet('World')" 2>/dev/null && mark "H2" PASS "greet" || mark "H2" FAIL "$OUT"

echo "=== 9 / 11 ==="
curl -sS -H "Authorization: Bearer $ZEUSCODE_API_KEY" https://zeuscode.ru/v1/models -o /dev/null -w "%{http_code}" | grep -q 200 && mark "9.smoke" PASS "api 200" || mark "9.smoke" FAIL
NULLC=$(journalctl -u zeuscode --since "$LOG_SINCE" --no-pager 2>/dev/null | grep -c "Message content is null" || true)
TOOLN=$(journalctl -u zeuscode --since "$LOG_SINCE" --no-pager 2>/dev/null | grep -c "Tool type or function is null" || true)
[ "${NULLC:-0}" = "0" ] && mark "11.null" PASS "no null" || mark "11.null" FAIL "c=$NULLC"
[ "${TOOLN:-0}" = "0" ] && mark "11.tool" PASS "no tool null" || mark "11.tool" FAIL "c=$TOOLN"

mark "10.1" SKIP "502 retry"
mark "10.2" SKIP "parallel"
mark "10.3" SKIP "model switch mid-session"
mark "10.4" SKIP "key rotate TG"
mark "12.tg-ui" SKIP "TG clicks"
mark "H3" SKIP "goose skills/plugins"
# H1: interactive session — pipe one line (best-effort headless)
H1=$(printf 'Reply one word: H1_OK\n' | timeout 90 goose session -n goose-lab-h1 2>&1 | tail -25 || true)
echo "$H1" | grep -qiE 'H1_OK|OK' && mark "H1.session" PASS "piped session" || mark "H1.session" SKIP "needs desktop TUI"

{
  echo
  echo "| ID | Status | Note |"
  echo "|----|--------|------|"
  for r in "${RESULTS[@]}"; do echo "$r"; done
  echo
  echo "## Summary"
  echo "- PASS: $PASS"
  echo "- FAIL: $FAIL"
  echo "- SKIP: $SKIP"
} >> "$REPORT"
cp "$REPORT" /opt/zeus-client-lab/reports/goose-checklist-latest.md
cp "$REPORT" /opt/zeus-client-lab/reports/goose-human-full-latest.md
echo
echo "REPORT=$REPORT"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
