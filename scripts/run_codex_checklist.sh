#!/usr/bin/env bash
# Codex × ZeusCode lab checklist (headless via `codex exec`).
set -u
. /opt/zeus-client-lab/configs/codex.env 2>/dev/null || true
export ZEUSCODE_API_KEY="${ZEUSCODE_API_KEY:-$(cat /opt/zeus-client-lab/configs/zeus_smoke.key)}"
PLAY=/opt/zeus-client-lab/playground
REPORT=/opt/zeus-client-lab/reports/codex-checklist-$(date +%Y%m%d-%H%M%S).md
PASS=0; FAIL=0; SKIP=0
declare -a RESULTS

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

cx() {
  # non-interactive agent; writable workspace, never ask approvals (headless lab)
  local prompt="$1"
  local model="${2:-}"
  local args=(exec --skip-git-repo-check -s workspace-write -c 'approval_policy="never"')
  if [ -n "$model" ]; then args+=(-m "$model"); fi
  timeout 240 codex "${args[@]}" "$prompt" </dev/null 2>&1 | tr -d '\r'
}

mkdir -p "$(dirname "$REPORT")" "$PLAY/notes" "$PLAY/src"
{
  echo "# Codex checklist — $(date -Is)"
  echo
  echo "- client: $(codex --version 2>/dev/null | head -1)"
  echo "- config: ~/.codex/config.toml (miniapp-style zeuscode provider)"
  echo "- auth: ZEUSCODE_API_KEY · requires_openai_auth=false · Not logged in ChatGPT"
  echo "- playground: $PLAY"
  echo
} > "$REPORT"

cd "$PLAY"
printf '# ZeusCode Codex lab\n\nPlayground for agent tests.\n' > README.md
printf 'print("hello")\n' > src/hello.py
rm -f notes/codex-*.txt notes/кир-codex.txt out-codex.txt src/greet_codex.py 2>/dev/null || true

echo "=== 1. Connection / auth ==="
if [ -n "${ZEUSCODE_API_KEY:-}" ] && [ "${ZEUSCODE_API_KEY:0:5}" = "zeus_" ]; then
  mark "1.2" PASS "ZEUSCODE_API_KEY present"
else
  mark "1.2" FAIL "key missing"
fi
STATUS=$(codex login status 2>&1 || true)
if echo "$STATUS" | grep -qi "Not logged in"; then
  mark "1.chatgpt" PASS "no ChatGPT session (API key path)"
else
  mark "1.chatgpt" FAIL "status=$STATUS"
fi
if grep -q 'wire_api = "responses"' /root/.codex/config.toml && grep -q 'requires_openai_auth = false' /root/.codex/config.toml; then
  mark "1.1" PASS "config matches miniapp (responses + no openai auth)"
else
  mark "1.1" FAIL "config mismatch"
fi
# bad key
BAD=$(ZEUSCODE_API_KEY=zeus_INVALID timeout 60 codex exec --skip-git-repo-check "hi" 2>&1 | tail -20 || true)
if echo "$BAD" | grep -qiE '401|invalid|unauthorized|auth|denied|error'; then
  mark "1.3" PASS "bad key fails"
else
  mark "1.3" FAIL "bad key soft: $(echo $BAD|head -c 120)"
fi
# guide sync
if curl -sS https://zeuscode.ru/static/tg-miniapp.js | grep -q 'wire_api = "responses"' && \
   curl -sS https://zeuscode.ru/static/tg-miniapp.js | grep -q 'ZEUSCODE_API_KEY'; then
  mark "1.5" PASS "miniapp guide has responses + ZEUSCODE_API_KEY"
else
  mark "1.5" FAIL "miniapp guide mismatch"
fi

echo "=== 8.1 Responses API ==="
CODE=$(curl -sS -o /tmp/resp.json -w "%{http_code}" -X POST https://zeuscode.ru/v1/responses \
  -H "Authorization: Bearer $ZEUSCODE_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","input":"Reply OK","stream":false}')
if [ "$CODE" = "200" ] && grep -q OK /tmp/resp.json; then mark "8.1a" PASS "POST /v1/responses 200"; else mark "8.1a" FAIL "http=$CODE"; fi
# stream SSE
CODE=$(curl -sS -o /tmp/resp_s -w "%{http_code}" -N -X POST https://zeuscode.ru/v1/responses \
  -H "Authorization: Bearer $ZEUSCODE_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","input":"Count 1 2 3","stream":true}')
if [ "$CODE" = "200" ] && grep -qE 'event:|data:' /tmp/resp_s; then mark "8.1b" PASS "responses SSE frames"; else mark "8.1b" FAIL "http=$CODE"; fi

echo "=== 2/3 Chat + modes ==="
OUT=$(cx "Reply with exactly one word: OK" | tail -8)
if echo "$OUT" | grep -qiE '\bOK\b'; then mark "3.1" PASS "chat OK"; else mark "3.1" FAIL "$OUT"; fi

OUT=$(cx "Ответь коротко словом: привет" | tail -8)
if echo "$OUT" | grep -qiE 'привет|Привет|hello|здрав'; then mark "3.2" PASS "cyr ok"; else mark "3.2" FAIL "$OUT"; fi

for mode_tag in simple:simple power:power; do
  mode=${mode_tag%%:*}; tag=${mode_tag##*:}
  set_mode "$mode" >/tmp/sm
  rm -f "notes/codex-mode-$tag.txt"
  OUT=$(cx "Reply one word: MODE-$tag. Create notes/codex-mode-$tag.txt with text $tag-ok. Reply DONE.")
  if [ -f "notes/codex-mode-$tag.txt" ] && grep -q "$tag-ok" "notes/codex-mode-$tag.txt"; then
    mark "HM.$tag" PASS "mode+$tag file"
  else
    mark "HM.$tag" FAIL "out=$(echo $OUT|head -c 160)"
  fi
done
set_mode custom '["gemini-2.5-flash","deepseek-v4-flash","claude-haiku-4-5"]' >/tmp/sm
rm -f notes/codex-mode-custom.txt
OUT=$(cx "Create notes/codex-mode-custom.txt with text custom-ok. Reply DONE.")
if [ -f notes/codex-mode-custom.txt ] && grep -q custom-ok notes/codex-mode-custom.txt; then
  mark "HM.custom" PASS "custom mode write"
else
  mark "HM.custom" FAIL "out=$(echo $OUT|head -c 160)"
fi
set_mode power >/tmp/sm

echo "=== 5/6/7 Tools files shell ==="
OUT=$(cx "Read README.md and reply with ONLY its first line.")
FIRST=$(head -1 README.md)
if echo "$OUT" | grep -Fq "$FIRST" || echo "$OUT" | grep -qiE 'ZeusCode|Playground|lab'; then
  mark "6.1" PASS "read ok"
else
  mark "6.1" FAIL "out=$OUT"
fi

rm -f notes/codex-write.txt
OUT=$(cx "Create notes/codex-write.txt with exact text hello-codex. Reply DONE.")
if [ -f notes/codex-write.txt ] && grep -q hello-codex notes/codex-write.txt; then
  mark "6.2" PASS "write ok"
else
  mark "6.2" FAIL "out=$(echo $OUT|head -c 160)"
fi

printf 'print("hello")\n' > src/hello.py
OUT=$(cx "Edit src/hello.py so it prints goodbye instead of hello. Reply DONE.")
if grep -qi goodbye src/hello.py; then mark "6.3" PASS "edit ok"; else mark "6.3" FAIL "content=$(cat src/hello.py)"; fi

rm -f "notes/кир-codex.txt"
OUT=$(cx "Create notes/кир-codex.txt with content: привет. Reply DONE.")
if [ -f "notes/кир-codex.txt" ] && grep -q "привет" "notes/кир-codex.txt"; then
  mark "6.4" PASS "cyrillic ok"
else
  mark "6.4" FAIL "out=$(echo $OUT|head -c 120)"
fi

OUT=$(cx "Run in terminal: pwd && ls. Reply with the pwd path.")
if echo "$OUT" | grep -qiE 'playground|zeus-client-lab'; then mark "7.1" PASS "shell pwd"; else mark "7.1" FAIL "$OUT"; fi

rm -f out-codex.txt
OUT=$(cx "Run: echo hello > out-codex.txt && cat out-codex.txt. Reply DONE.")
if [ -f out-codex.txt ] && grep -q hello out-codex.txt; then mark "7.2" PASS "shell write"; else mark "7.2" FAIL "$OUT"; fi

OUT=$(cx "Run: git status -sb. Reply with first line.")
if echo "$OUT" | grep -qE '##|main'; then mark "7.3" PASS "git status"; else mark "7.3" FAIL "$OUT"; fi

OUT=$(cx "Run: git fetch --dry-run 2>&1 || true. Briefly report.")
if [ -n "$OUT" ]; then mark "7.4" PASS "git fetch probed"; else mark "7.4" FAIL empty; fi

OUT=$(cx "Run: ls /no/such/codex-path ; report that it failed.")
if echo "$OUT" | grep -qiE 'fail|error|no such|not found|cannot'; then mark "7.5" PASS "nonzero visible"; else mark "7.5" FAIL "$OUT"; fi

OUT=$(cx "Run: sleep 12 && echo slept-codex. Reply with slept-codex when done.")
if echo "$OUT" | grep -qi slept-codex; then mark "7.6" PASS "sleep ok"; else mark "7.6" FAIL "$OUT"; fi

echo "=== Solo models ==="
for m in gemini-2.5-flash deepseek-v4-flash; do
  rm -f "notes/codex-solo-$m.txt"
  OUT=$(cx "Create notes/codex-solo-$m.txt with text solo-$m-ok. Reply DONE." "$m")
  if [ -f "notes/codex-solo-$m.txt" ] && grep -q "solo-$m-ok" "notes/codex-solo-$m.txt"; then
    mark "SOLO.$m" PASS "write"
  else
    mark "SOLO.$m" FAIL "out=$(echo $OUT|head -c 140)"
  fi
done

echo "=== Mini project ==="
rm -f src/greet_codex.py
OUT=$(cx "Add src/greet_codex.py with greet(name) returning Hello, {name}!. Run python -c \"from src.greet_codex import greet; print(greet('World'))\". Reply with output.")
if [ -f src/greet_codex.py ] && PYTHONPATH="$PLAY" python3 -c "from src.greet_codex import greet; assert 'Hello' in greet('World')" 2>/dev/null; then
  mark "H2" PASS "greet_codex ok"
else
  mark "H2" FAIL "out=$(echo $OUT|head -c 160)"
fi

echo "=== Logs ==="
NULLC=$(journalctl -u zeuscode.service --since "45 min ago" --no-pager 2>/dev/null | grep -c "Message content is null" || true)
TOOLN=$(journalctl -u zeuscode.service --since "45 min ago" --no-pager 2>/dev/null | grep -c "Tool type or function is null" || true)
RESP502=$(journalctl -u zeuscode.service --since "45 min ago" --no-pager 2>/dev/null | grep -c "POST /v1/responses" | head -1 || true)
if [ "${NULLC:-0}" = "0" ]; then mark "11.null" PASS "no null content"; else mark "11.null" FAIL "count=$NULLC"; fi
if [ "${TOOLN:-0}" = "0" ]; then mark "11.tool" PASS "no tool null"; else mark "11.tool" FAIL "count=$TOOLN"; fi

mark "12.tg-ui" SKIP "Telegram UI clicks"
mark "TUI" SKIP "interactive codex TUI Allow prompts"

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
cp "$REPORT" /opt/zeus-client-lab/reports/codex-checklist-latest.md
echo
echo "REPORT=$REPORT"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
exit 0
