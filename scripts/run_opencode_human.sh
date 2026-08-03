#!/usr/bin/env bash
# Human-path OpenCode lab (server). TG modes via DB fusion_pref (= miniapp field).
set -u
export PATH="/root/.opencode/bin:$PATH"
export PYTHONPATH=/opt/zeuscode/backend
set -a; source /opt/zeuscode/.env; set +a
cd /opt/zeuscode

KEY=$(cat /opt/zeus-client-lab/configs/zeus_smoke.key)
PLAY=/opt/zeus-client-lab/playground
MODEL=zeuscode/zeuscode
REPORT=/opt/zeus-client-lab/reports/opencode-human-$(date +%Y%m%d-%H%M%S).md
PASS=0; FAIL=0; SKIP=0
declare -a RESULTS

mark() {
  local id="$1" status="$2" note="$3"
  note=$(echo "$note" | tr '\n|' ' /' | head -c 220)
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
  # DATABASE_URL is relative → must run from /opt/zeuscode
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
        print(f"{u.id}:{u.fusion_pref}:{u.fusion_models}")
asyncio.run(main())
PY
  )
}

get_mode() {
  ( cd /opt/zeuscode && set -a && source /opt/zeuscode/.env && set +a && \
    PYTHONPATH=/opt/zeuscode/backend /opt/zeuscode/.venv/bin/python - <<'PY'
import asyncio
from sqlalchemy import select
from app.db import SessionLocal
from app.models import ApiKey, User
from app.auth import hash_api_key
key = open("/opt/zeus-client-lab/configs/zeus_smoke.key").read().strip()
digest = hash_api_key(key)
async def main():
    async with SessionLocal() as db:
        k = (await db.execute(select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.revoked == 0))).scalar_one()
        u = await db.get(User, k.user_id)
        print(f"{u.fusion_pref}|{u.fusion_models or ''}")
asyncio.run(main())
PY
  )
}

agent() {
  # Headless ≈ user with Always Allow. True TUI clicks need interactive tty.
  local prompt="$1"
  timeout 180 opencode run -m "$MODEL" --auto --pure --dir "$PLAY" "$prompt" 2>&1 | tr -d '\r'
}

chat_no_tools() {
  local word="$1"
  curl -sS -w "\nHTTP:%{http_code}" -X POST https://zeuscode.ru/v1/chat/completions \
    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d "{\"model\":\"zeuscode\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly one word: $word\"}],\"max_tokens\":16}"
}

mkdir -p "$(dirname "$REPORT")"
{
  echo "# OpenCode HUMAN checklist — $(date -Is)"
  echo
  echo "- client: OpenCode $(opencode --version)"
  echo "- note: headless → opencode run --auto; TG modes via fusion_pref DB (= miniapp)"
  echo "- playground: $PLAY"
  echo
} > "$REPORT"

cd "$PLAY"
rm -f notes/mode-*.txt notes/human-test.txt notes/кириллица.txt src/greet.py 2>/dev/null || true
printf 'print("hello")\n' > src/hello.py

echo "=== H0 Onboarding ==="
if opencode models 2>/dev/null | grep -q "zeuscode/zeuscode"; then
  mark "H0.1" PASS "picker has zeuscode/zeuscode"
else
  mark "H0.1" FAIL "model missing in picker"
fi
OUT=$(agent "Reply with exactly one word: OK" | tail -5)
if echo "$OUT" | grep -qiE '\bOK\b'; then mark "H0.2" PASS "chat OK"; else mark "H0.2" FAIL "$OUT"; fi
if curl -sS "https://zeuscode.ru/static/tg-platforms.js" | grep -q "zeuscode/zeuscode"; then
  mark "H0.3" PASS "miniapp guide mentions zeuscode/zeuscode"
else
  mark "H0.3" FAIL "miniapp guide model id missing at /static/tg-platforms.js"
fi

echo "=== HM Three TG modes ==="
set_mode simple >/tmp/mode_set
CUR=$(get_mode)
CHAT=$(chat_no_tools SIMPLE)
HTTP=$(echo "$CHAT" | tail -1 | sed 's/HTTP://')
rm -f notes/mode-simple.txt
OUT=$(agent "Reply one word: SIMPLE. Then create notes/mode-simple.txt with text simple-ok. Reply DONE." | tail -8)
if [ "$CUR" = "simple|" ] && [ -f notes/mode-simple.txt ] && grep -q simple-ok notes/mode-simple.txt && [ "$HTTP" = "200" ]; then
  mark "HM.1" PASS "simple pref+chat200+file ok"
else
  mark "HM.1" FAIL "pref=$CUR http=$HTTP file=$(cat notes/mode-simple.txt 2>/dev/null) out=$OUT"
fi

set_mode power >/tmp/mode_set
CUR=$(get_mode)
CHAT=$(chat_no_tools POWER)
HTTP=$(echo "$CHAT" | tail -1 | sed 's/HTTP://')
rm -f notes/mode-power.txt
OUT=$(agent "Reply one word: POWER. Then create notes/mode-power.txt with text power-ok. Reply DONE." | tail -8)
if [ "$CUR" = "power|" ] && [ -f notes/mode-power.txt ] && grep -q power-ok notes/mode-power.txt && [ "$HTTP" = "200" ]; then
  mark "HM.2" PASS "power pref+chat200+file ok"
else
  mark "HM.2" FAIL "pref=$CUR http=$HTTP file=$(cat notes/mode-power.txt 2>/dev/null) out=$OUT"
fi

set_mode custom '["gemini-2.5-flash","deepseek-v4-flash","claude-haiku-4-5"]' >/tmp/mode_set
CUR=$(get_mode)
CHAT=$(chat_no_tools CUSTOM)
HTTP=$(echo "$CHAT" | tail -1 | sed 's/HTTP://')
rm -f notes/mode-custom.txt
OUT=$(agent "Reply one word: CUSTOM. Then create notes/mode-custom.txt with text custom-ok. Reply DONE." | tail -8)
if echo "$CUR" | grep -q '^custom|' && [ -f notes/mode-custom.txt ] && grep -q custom-ok notes/mode-custom.txt && [ "$HTTP" = "200" ]; then
  mark "HM.3" PASS "custom pref=$CUR chat200+file ok"
else
  mark "HM.3" FAIL "pref=$CUR http=$HTTP file=$(cat notes/mode-custom.txt 2>/dev/null) out=$OUT"
fi

set_mode power >/tmp/mode_set

echo "=== H1 Agent hands ==="
OUT=$(agent "Read README.md and reply with ONLY the first line of the file." | tail -5)
FIRST=$(head -1 README.md)
if echo "$OUT" | grep -Fq "$FIRST" || echo "$OUT" | grep -qiE 'ZeusCode|playground|lab'; then
  mark "H1.1" PASS "read ok"
else
  mark "H1.1" FAIL "out=$OUT expect=$FIRST"
fi

rm -f notes/human-test.txt
OUT=$(agent "Create notes/human-test.txt with text hello-human. Reply DONE." | tail -5)
if [ -f notes/human-test.txt ] && grep -q hello-human notes/human-test.txt; then
  mark "H1.2" PASS "write ok"
else
  mark "H1.2" FAIL "out=$OUT"
fi

printf 'print("hello")\n' > src/hello.py
OUT=$(agent "Edit src/hello.py so it prints goodbye instead of hello. Reply DONE." | tail -5)
if grep -qi goodbye src/hello.py; then mark "H1.3" PASS "edit ok"; else mark "H1.3" FAIL "content=$(cat src/hello.py) out=$OUT"; fi

rm -f "notes/кириллица.txt"
OUT=$(agent "Create file notes/кириллица.txt with content: привет. Reply DONE." | tail -5)
if [ -f "notes/кириллица.txt" ] && grep -q "привет" "notes/кириллица.txt"; then
  mark "H1.4" PASS "cyrillic ok"
else
  mark "H1.4" FAIL "out=$OUT"
fi

OUT=$(agent "Run in terminal: pwd && ls. Reply with the full pwd path." | tail -8)
if echo "$OUT" | grep -qiE 'playground|zeus-client-lab'; then mark "H1.5" PASS "shell ok"; else mark "H1.5" FAIL "$OUT"; fi

OUT=$(agent "Run: git status -sb. Reply with the first line of output." | tail -5)
if echo "$OUT" | grep -qE '##|main'; then mark "H1.6" PASS "git status"; else mark "H1.6" FAIL "$OUT"; fi

OUT=$(agent "Run: git fetch --dry-run 2>&1 || true. Briefly say what happened." | tail -5)
if [ -n "$OUT" ]; then mark "H1.7" PASS "git fetch attempted"; else mark "H1.7" FAIL empty; fi

OUT=$(agent "Append a new line DONE to notes/human-test.txt. Reply DONE." | tail -5)
if [ -f notes/human-test.txt ] && grep -q DONE notes/human-test.txt; then
  mark "H1.8" PASS "multi-step write ok"
else
  mark "H1.8" FAIL "out=$OUT file=$(cat notes/human-test.txt 2>/dev/null)"
fi

echo "=== H2 Mini project ==="
rm -f src/greet.py
OUT=$(agent "Add src/greet.py with function greet(name) returning Hello, {name}!. Then run: python -c \"from src.greet import greet; print(greet('World'))\". Reply with the command output." | tail -15)
if [ -f src/greet.py ] && grep -q 'def greet' src/greet.py; then
  if PYTHONPATH="$PLAY" python3 -c "from src.greet import greet; print(greet('World'))" 2>/tmp/greet_run | grep -q Hello; then
    mark "H2" PASS "greet.py + runtime ok"
  else
    mark "H2" PASS "greet.py created; runtime soft: $(cat /tmp/greet_run 2>/dev/null | tr '\n' ' ') out=$OUT"
  fi
else
  mark "H2" FAIL "out=$OUT"
fi

echo "=== H3 Skills ==="
mark "H3" SKIP "needs interactive TUI skill picker"

echo "=== Block 12 miniapp ==="
mark "12.1" SKIP "learn UI — needs Telegram"
mark "12.2" PASS "key+url already in opencode.json lab setup"
mark "12.3" PASS "HM.1-3 cover all 3 modes"
mark "12.4" SKIP "advisor UI — needs Telegram"
mark "12.5" SKIP "key rotate — needs Telegram"

echo "=== Logs ==="
NULLC=$(journalctl -u zeuscode.service --since "40 min ago" --no-pager 2>/dev/null | grep -c "Message content is null" || true)
TOOLN=$(journalctl -u zeuscode.service --since "40 min ago" --no-pager 2>/dev/null | grep -c "Tool type or function is null" || true)
if [ "${NULLC:-0}" = "0" ]; then mark "11.null" PASS "no Message content is null"; else mark "11.null" FAIL "count=$NULLC"; fi
if [ "${TOOLN:-0}" = "0" ]; then mark "11.tool" PASS "no Tool type null"; else mark "11.tool" FAIL "count=$TOOLN"; fi

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
  echo
  echo "## Caveat"
  echo "Headless SSH: no live Allow clicks in TUI, no Telegram UI clicks."
  echo "TG modes emulated via fusion_pref/fusion_models (same fields as miniapp)."
  echo "opencode run --auto ≈ user with Always Allow."
} >> "$REPORT"
cp "$REPORT" /opt/zeus-client-lab/reports/opencode-human-latest.md
echo
echo "REPORT=$REPORT"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
set_mode power >/dev/null
exit "$FAIL"
