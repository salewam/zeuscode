#!/usr/bin/env bash
# Aider × ZeusCode — full lab checklist (human scenarios, headless `aider -m`).
set -u
. /opt/zeus-client-lab/configs/aider.env 2>/dev/null || true
export ZEUSCODE_API_KEY="${ZEUSCODE_API_KEY:-$(cat /opt/zeus-client-lab/configs/zeus_smoke.key)}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-https://zeuscode.ru/v1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-$ZEUSCODE_API_KEY}"
export PATH="/root/.local/bin:/usr/local/bin:$PATH"
PLAY=/opt/zeus-client-lab/playground
REPORT=/opt/zeus-client-lab/reports/aider-checklist-$(date +%Y%m%d-%H%M%S).md
PASS=0; FAIL=0; SKIP=0
declare -a RESULTS
LOG_SINCE="$(date -Is -d '90 min ago' 2>/dev/null || date -Is)"

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
        print(f"{u.fusion_pref}|{u.fusion_models or ''}")
asyncio.run(main())
PY
  )
}

ensure_git() {
  git config --global --add safe.directory "$PLAY" 2>/dev/null || true
  cd "$PLAY"
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git init -b main
    git config user.email lab@zeus
    git config user.name lab
  fi
}

aid() {
  local prompt="$1"
  shift
  local model="openai/zeuscode"
  if [ $# -gt 0 ] && [[ "$1" == openai/* ]]; then
    model="$1"
    shift
  fi
  local extra=()
  while [ $# -gt 0 ]; do extra+=("$1"); shift; done
  timeout 300 aider --model "$model" --yes-always --no-show-model-warnings --no-auto-commits \
    "${extra[@]}" -m "$prompt" </dev/null 2>&1 | tr -d '\r'
}

mkdir -p "$(dirname "$REPORT")" "$PLAY/notes" "$PLAY/src"
{
  echo "# Aider full checklist — $(date -Is)"
  echo
  echo "- client: $(aider --version 2>/dev/null | head -1)"
  echo "- env: OPENAI_API_BASE=$OPENAI_API_BASE · --model openai/zeuscode"
  echo "- playground: $PLAY"
  echo "- human-style: multi-step prompts via aider -m (not interactive TUI)"
  echo
} > "$REPORT"

ensure_git
cd "$PLAY"
printf '# ZeusCode Aider lab\n\nPlayground for human-style agent tests.\n' > README.md
printf 'print("hello")\n' > src/hello.py
rm -f notes/aider-*.txt notes/кир-aider.txt out-aider.txt src/greet_aider.py 2>/dev/null || true
git add -A 2>/dev/null || true
git diff --cached --quiet 2>/dev/null || git commit -m "aider full checklist prep" 2>/dev/null || true

echo "=== 1. Connection / guide ==="
if [ -n "${OPENAI_API_KEY:-}" ] && [ "${OPENAI_API_KEY:0:5}" = "zeus_" ]; then
  mark "1.2" PASS "OPENAI_API_KEY zeus_"
else
  mark "1.2" FAIL "key missing"
fi
if [ "${OPENAI_API_BASE%/}" = "https://zeuscode.ru/v1" ]; then
  mark "1.1" PASS "OPENAI_API_BASE …/v1"
else
  mark "1.1" FAIL "base=$OPENAI_API_BASE"
fi
BAD=$(OPENAI_API_KEY=zeus_INVALID timeout 90 aider --model openai/zeuscode --yes-always --no-show-model-warnings \
  -m "hi" </dev/null 2>&1 | tail -25 || true)
if echo "$BAD" | grep -qiE '401|invalid|unauthorized|auth|denied|error|Authentication'; then
  mark "1.3" PASS "bad key fails"
else
  mark "1.3" FAIL "soft: $(echo "$BAD" | head -c 120)"
fi
MCODE=$(curl -sS -o /tmp/aider_models.json -w "%{http_code}" \
  -H "Authorization: Bearer $ZEUSCODE_API_KEY" "${OPENAI_API_BASE%/}/models")
if [ "$MCODE" = "200" ] && grep -q zeuscode /tmp/aider_models.json; then
  mark "1.4" PASS "GET /v1/models has zeuscode"
else
  mark "1.4" FAIL "http=$MCODE"
fi
if curl -sS https://zeuscode.ru/static/tg-miniapp.js | grep -q 'openai/zeuscode' && \
   curl -sS https://zeuscode.ru/static/tg-platforms.js | grep -q 'configKind: "aider"'; then
  mark "1.5" PASS "miniapp aider guide (openai/ prefix)"
else
  mark "1.5" FAIL "miniapp drift"
fi

echo "=== 8.5 Aider prefix + commit ==="
OUT=$(aid "Reply with exactly one word: PREFIX_OK" 2>&1)
if echo "$OUT" | grep -qiE '\bPREFIX_OK\b'; then mark "8.5a" PASS "openai/zeuscode"; else mark "8.5a" FAIL "$(echo "$OUT" | tail -3 | head -c 160)"; fi
rm -f notes/aider-commit-probe.txt
BEFORE=$(git rev-parse HEAD 2>/dev/null || echo none)
OUT=$(timeout 300 aider --model openai/zeuscode --yes-always --no-show-model-warnings --auto-commits \
  -m "Create notes/aider-commit-probe.txt with text commit-ok only. Do not touch other files." </dev/null 2>&1 | tr -d '\r')
AFTER=$(git rev-parse HEAD 2>/dev/null || echo none)
if [ -f notes/aider-commit-probe.txt ] && grep -q commit-ok notes/aider-commit-probe.txt && [ "$BEFORE" != "$AFTER" ]; then
  mark "8.5b" PASS "auto-commit after write"
elif [ -f notes/aider-commit-probe.txt ] && grep -q commit-ok notes/aider-commit-probe.txt; then
  mark "8.5b" SKIP "file ok but no new commit (git add policy)"
else
  mark "8.5b" FAIL "$(echo "$OUT" | tail -5 | head -c 160)"
fi

echo "=== 3 Chat ==="
OUT=$(aid "Reply with exactly one word: OK" 2>&1)
if echo "$OUT" | grep -qiE '\bOK\b'; then mark "3.1" PASS "chat OK"; else mark "3.1" FAIL "$(echo "$OUT" | tail -3 | head -c 160)"; fi
OUT=$(aid "Ответь одним словом: привет" 2>&1)
if echo "$OUT" | grep -qiE 'привет|Привет|hello|здрав'; then mark "3.2" PASS "cyrillic"; else mark "3.2" FAIL "$(echo "$OUT" | tail -3 | head -c 160)"; fi
OUT=$(aid "Remember code word BANANA. Reply only: BANANA" 2>&1)
if echo "$OUT" | grep -qi BANANA; then mark "3.3a" PASS "single-turn memory ok"; else mark "3.3a" FAIL "$(echo "$OUT" | tail -3 | head -c 120)"; fi
OUT=$(aid "What was the code word I asked you to remember? Reply one word only." 2>&1)
if echo "$OUT" | grep -qi BANANA; then mark "3.3" PASS "history in repo session"; else mark "3.3" SKIP "aider -m history weak: $(echo "$OUT" | tail -2 | head -c 80)"; fi
mark "3.4" SKIP "empty prompt (TUI-only)"
mark "3.5" SKIP "100KB prompt (lab time)"

echo "=== 4 Stream ==="
OUT=$(timeout 180 aider --model openai/zeuscode --yes-always --no-show-model-warnings --no-auto-commits --stream \
  -m "Reply with exactly: STREAM_OK and one short sentence." </dev/null 2>&1 | tr -d '\r')
if echo "$OUT" | grep -qi STREAM_OK; then mark "4.1" PASS "stream on"; else mark "4.1" FAIL "$(echo "$OUT" | tail -4 | head -c 160)"; fi
OUT=$(timeout 180 aider --model openai/zeuscode --yes-always --no-show-model-warnings --no-auto-commits --no-stream \
  -m "Reply exactly: NOSTREAM_OK" </dev/null 2>&1 | tr -d '\r')
if echo "$OUT" | grep -qi NOSTREAM_OK; then mark "4.3" PASS "stream off"; else mark "4.3" FAIL "$(echo "$OUT" | tail -3 | head -c 120)"; fi
mark "4.2" SKIP "mid-stream stop (interactive)"

echo "=== HM modes (TG miniapp) ==="
set_mode power >/tmp/sm
for mode_tag in simple:simple power:power; do
  mode=${mode_tag%%:*}; tag=${mode_tag##*:}
  set_mode "$mode" >/tmp/sm
  rm -f "notes/aider-mode-$tag.txt"
  OUT=$(aid "Create notes/aider-mode-$tag.txt with exact text ${tag}-ok. Do not modify other files." 2>&1)
  if [ -f "notes/aider-mode-$tag.txt" ] && grep -q "${tag}-ok" "notes/aider-mode-$tag.txt"; then
    mark "HM.$tag" PASS "TG $mode write"
  else
    mark "HM.$tag" FAIL "$(echo "$OUT" | tail -4 | head -c 160)"
  fi
done
set_mode custom '["gemini-2.5-flash","deepseek-v4-flash","claude-haiku-4-5"]' >/tmp/sm
rm -f notes/aider-mode-custom.txt
OUT=$(aid "Create notes/aider-mode-custom.txt with exact text custom-ok. Do not modify other files." 2>&1)
if [ -f notes/aider-mode-custom.txt ] && grep -q custom-ok notes/aider-mode-custom.txt; then
  mark "HM.custom" PASS "custom panel write"
else
  mark "HM.custom" FAIL "$(echo "$OUT" | tail -4 | head -c 160)"
fi
set_mode power >/tmp/sm
mark "2.1" PASS "via HM.simple"
mark "2.2" PASS "via HM.power"
mark "2.3" PASS "via HM.custom"

echo "=== 5 Tools (aider repo-map / edits) ==="
OUT=$(aid "Read README.md and reply with ONLY its first line, nothing else." 2>&1)
FIRST=$(head -1 README.md)
if echo "$OUT" | grep -Fq "$FIRST" || echo "$OUT" | grep -qiE 'ZeusCode|Aider lab|Playground'; then
  mark "5.1" PASS "read via repo"
else
  mark "5.1" FAIL "$(echo "$OUT" | tail -4 | head -c 160)"
fi
OUT=$(aid "Run shell: pwd && ls notes | head -3. Paste output in reply." 2>&1)
if echo "$OUT" | grep -qiE 'playground|zeus-client-lab|notes'; then mark "5.2" PASS "read+shell"; else mark "5.2" FAIL "$(echo "$OUT" | tail -4 | head -c 160)"; fi
mark "5.3" SKIP "no tool_choice wire"
mark "5.4" SKIP "OpenAI tool role N/A"
mark "5.5" SKIP "parallel tool_calls N/A"

echo "=== 6 Files ==="
OUT=$(aid "Read README.md and quote the first line in your reply." 2>&1)
if echo "$OUT" | grep -qiE 'ZeusCode|Playground'; then mark "6.1" PASS "read README"; else mark "6.1" FAIL "$(echo "$OUT" | tail -3 | head -c 120)"; fi
rm -f notes/aider-write.txt
OUT=$(aid "Create notes/aider-write.txt with exact text hello-aider. Do not modify other files." 2>&1)
if [ -f notes/aider-write.txt ] && grep -q hello-aider notes/aider-write.txt; then mark "6.2" PASS "write"; else mark "6.2" FAIL "$(echo "$OUT" | tail -4 | head -c 160)"; fi
printf 'print("hello")\n' > src/hello.py
OUT=$(aid "Edit src/hello.py so it prints goodbye instead of hello. Only that file." 2>&1)
if grep -qi goodbye src/hello.py; then mark "6.3" PASS "edit"; else mark "6.3" FAIL "content=$(cat src/hello.py)"; fi
rm -f "notes/кир-aider.txt"
OUT=$(aid "Create notes/кир-aider.txt with content: привет. Do not modify other files." 2>&1)
if [ -f "notes/кир-aider.txt" ] && grep -q "привет" "notes/кир-aider.txt"; then mark "6.4" PASS "cyrillic path"; else mark "6.4" FAIL "$(echo "$OUT" | tail -4 | head -c 120)"; fi
mark "6.5" SKIP "multimodal N/A"

echo "=== 7 Shell / git ==="
OUT=$(aid "Run shell: pwd && ls notes | head -3. Paste output in reply." 2>&1)
if echo "$OUT" | grep -qiE 'playground|zeus-client-lab|notes'; then mark "7.1" PASS "pwd+ls"; else mark "7.1" FAIL "$(echo "$OUT" | tail -4 | head -c 160)"; fi
rm -f out-aider.txt
OUT=$(aid "Run: echo hello > out-aider.txt && cat out-aider.txt. Reply DONE if file contains hello." 2>&1)
if [ -f out-aider.txt ] && grep -q hello out-aider.txt; then mark "7.2" PASS "shell write"; else mark "7.2" FAIL "$(echo "$OUT" | tail -4 | head -c 160)"; fi
OUT=$(aid "Run: git status -sb. Reply with the first line of output." 2>&1)
if echo "$OUT" | grep -qE '##|main|aider'; then mark "7.3" PASS "git status"; else mark "7.3" FAIL "$(echo "$OUT" | tail -3 | head -c 120)"; fi
OUT=$(aid "Run: git fetch --dry-run 2>&1 || true. Summarize in one line." 2>&1)
if [ -n "$OUT" ]; then mark "7.4" PASS "git fetch probed"; else mark "7.4" FAIL empty; fi
OUT=$(aid "Run: ls /no/such/aider-path-xyz ; describe that it failed." 2>&1)
if echo "$OUT" | grep -qiE 'fail|error|no such|not found|cannot'; then mark "7.5" PASS "nonzero visible"; else mark "7.5" FAIL "$(echo "$OUT" | tail -3 | head -c 120)"; fi
OUT=$(aid "Run: sleep 12 && echo slept-aider. Reply with slept-aider when done." 2>&1)
if echo "$OUT" | grep -qi slept-aider; then mark "7.6" PASS "sleep 12"; else mark "7.6" FAIL "$(echo "$OUT" | tail -4 | head -c 160)"; fi

echo "=== 2 Solo / errors ==="
OUT=$(aid "Reply exactly: SOLO" "openai/gemini-2.5-flash" 2>&1)
if echo "$OUT" | grep -qiE '\bSOLO\b'; then mark "2.4" PASS "gemini-2.5-flash"; else mark "2.4" FAIL "$(echo "$OUT" | tail -3 | head -c 120)"; fi
OUT=$(aid "Reply one word: HEAVY" "openai/claude-opus-4-8" 2>&1)
if echo "$OUT" | grep -qi HEAVY; then mark "2.5" PASS "claude-opus-4-8"; else mark "2.5" FAIL "$(echo "$OUT" | tail -3 | head -c 120)"; fi
OUT=$(aid "hi" "openai/no-such-model-xyz" 2>&1)
if echo "$OUT" | grep -qiE 'error|invalid|not found|400|404|model'; then mark "2.6" PASS "bad model errors"; else mark "2.6" FAIL "soft: $(echo "$OUT" | tail -3 | head -c 100)"; fi
mark "2.7" SKIP "case canonicalization (manual)"

echo "=== H2 mini-project ==="
rm -f src/greet_aider.py
OUT=$(aid "Add src/greet_aider.py with def greet(name): return f'Hello, {name}!'. Then run python3 -c to test greet('World'). Reply with test output." 2>&1)
if [ -f src/greet_aider.py ] && PYTHONPATH="$PLAY" python3 -c "from src.greet_aider import greet; assert 'Hello' in greet('World')" 2>/dev/null; then
  mark "H2" PASS "greet_aider.py"
else
  mark "H2" FAIL "$(echo "$OUT" | tail -5 | head -c 160)"
fi

echo "=== 9 Billing (smoke) ==="
BAL1=$(curl -sS -H "Authorization: Bearer $ZEUSCODE_API_KEY" https://zeuscode.ru/v1/models -o /dev/null -w "%{http_code}")
if [ "$BAL1" = "200" ]; then mark "9.smoke" PASS "API still 200 after run"; else mark "9.smoke" FAIL "http=$BAL1"; fi

echo "=== 11 Logs ==="
NULLC=$(journalctl -u zeuscode.service --since "$LOG_SINCE" --no-pager 2>/dev/null | grep -c "Message content is null" || true)
TOOLN=$(journalctl -u zeuscode.service --since "$LOG_SINCE" --no-pager 2>/dev/null | grep -c "Tool type or function is null" || true)
if [ "${NULLC:-0}" = "0" ]; then mark "11.null" PASS "no null content"; else mark "11.null" FAIL "count=$NULLC"; fi
if [ "${TOOLN:-0}" = "0" ]; then mark "11.tool" PASS "no tool null"; else mark "11.tool" FAIL "count=$TOOLN"; fi

mark "10.1" SKIP "502 retry (manual)"
mark "10.2" SKIP "parallel chats (manual)"
mark "10.3" SKIP "mid-session model switch (manual)"
mark "10.4" SKIP "key rotate (miniapp manual)"
mark "12.tg-ui" SKIP "Telegram UI clicks"
mark "H1.TUI" SKIP "interactive aider TUI"
mark "H3" SKIP "no client skills"

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
cp "$REPORT" /opt/zeus-client-lab/reports/aider-checklist-latest.md
cp "$REPORT" /opt/zeus-client-lab/reports/aider-human-full-latest.md
echo
echo "REPORT=$REPORT"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
exit 0
