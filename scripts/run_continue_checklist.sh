#!/usr/bin/env bash
# Continue CLI (cn) × ZeusCode lab checklist — config as miniapp ~/.continue/config.yaml
set -u
. /opt/zeus-client-lab/configs/continue.env 2>/dev/null || true
export ZEUSCODE_API_KEY="${ZEUSCODE_API_KEY:-$(cat /opt/zeus-client-lab/configs/zeus_smoke.key)}"
PLAY=/opt/zeus-client-lab/playground
CFG=/root/.continue/config.yaml
REPORT=/opt/zeus-client-lab/reports/continue-checklist-$(date +%Y%m%d-%H%M%S).md
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

cnx() {
  local prompt="$1"
  timeout 240 cn -p --auto --silent --config "$CFG" "$prompt" </dev/null 2>&1 | tr -d '\r'
}

# rewrite config model id (zeuscode or solo)
set_model() {
  local model="$1"
  KEY=$(cat /opt/zeus-client-lab/configs/zeus_smoke.key)
  cat > "$CFG" <<EOF
name: ZeusCode
version: 1.0.0
schema: v1
models:
  - name: ZeusCode
    provider: openai
    model: ${model}
    apiBase: https://zeuscode.ru/v1
    apiKey: ${KEY}
    useResponsesApi: false
    capabilities:
      - tool_use
    roles:
      - chat
      - edit
      - apply
EOF
}

mkdir -p "$(dirname "$REPORT")" "$PLAY/notes" "$PLAY/src"
{
  echo "# Continue checklist — $(date -Is)"
  echo
  echo "- client: cn $(cn -v 2>/dev/null | head -1)"
  echo "- config: $CFG (miniapp-style openai + apiBase …/v1 + zeuscode)"
  echo "- playground: $PLAY"
  echo
} > "$REPORT"

cd "$PLAY"
printf '# ZeusCode Continue lab\n\nPlayground for agent tests.\n' > README.md
printf 'print("hello")\n' > src/hello.py
rm -f notes/cn-*.txt notes/кир-cn.txt out-cn.txt src/greet_cn.py 2>/dev/null || true
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || (git init -b main && git config user.email lab@zeus && git config user.name lab && git commit --allow-empty -m init)
set_model zeuscode

echo "=== 1. Connection / guide ==="
if [ -n "${ZEUSCODE_API_KEY:-}" ] && [ "${ZEUSCODE_API_KEY:0:5}" = "zeus_" ]; then
  mark "1.2" PASS "ZEUSCODE_API_KEY present"
else
  mark "1.2" FAIL "key missing"
fi
if grep -q 'apiBase: https://zeuscode.ru/v1' "$CFG" && grep -q 'model: zeuscode' "$CFG" && grep -q 'provider: openai' "$CFG" && grep -q 'useResponsesApi: false' "$CFG"; then
  mark "1.1" PASS "config.yaml matches miniapp"
else
  mark "1.1" FAIL "config mismatch"
fi

BAD=$(timeout 60 cn -p --auto --config <(sed "s/apiKey: .*/apiKey: zeus_INVALID/" "$CFG") "hi" </dev/null 2>&1 | tail -30 || true)
if echo "$BAD" | grep -qiE '401|invalid|unauthorized|auth|denied|error|API key|Incorrect'; then
  mark "1.3" PASS "bad key fails"
else
  mark "1.3" FAIL "bad key soft: $(echo $BAD|head -c 120)"
fi

if curl -sS https://zeuscode.ru/static/tg-miniapp.js | grep -q 'apiBase:' && \
   curl -sS https://zeuscode.ru/static/tg-platforms.js | grep -q 'configKind: "continue"'; then
  mark "1.5" PASS "miniapp guide has Continue apiBase"
else
  mark "1.5" FAIL "miniapp guide mismatch"
fi

echo "=== 8 chat completions ==="
CODE=$(curl -sS -o /tmp/cc.json -w "%{http_code}" -X POST https://zeuscode.ru/v1/chat/completions \
  -H "Authorization: Bearer $ZEUSCODE_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"Reply OK"}],"stream":false}')
if [ "$CODE" = "200" ] && grep -q OK /tmp/cc.json; then mark "8.chat" PASS "POST /v1/chat/completions 200"; else mark "8.chat" FAIL "http=$CODE"; fi

echo "=== 3 Chat + modes ==="
OUT=$(cnx "Reply with exactly one word: OK")
if echo "$OUT" | grep -qiE '\bOK\b'; then mark "3.1" PASS "chat OK"; else mark "3.1" FAIL "$OUT"; fi

OUT=$(cnx "Ответь коротко словом: привет")
if echo "$OUT" | grep -qiE 'привет|Привет|hello|здрав'; then mark "3.2" PASS "cyr ok"; else mark "3.2" FAIL "$OUT"; fi

for mode_tag in simple:simple power:power; do
  mode=${mode_tag%%:*}; tag=${mode_tag##*:}
  set_mode "$mode" >/tmp/sm
  rm -f "notes/cn-mode-$tag.txt"
  OUT=$(cnx "Create notes/cn-mode-$tag.txt with text $tag-ok. Reply DONE.")
  if [ -f "notes/cn-mode-$tag.txt" ] && grep -q "$tag-ok" "notes/cn-mode-$tag.txt"; then
    mark "HM.$tag" PASS "mode+$tag file"
  else
    mark "HM.$tag" FAIL "out=$(echo $OUT|head -c 160)"
  fi
done
set_mode custom '["gemini-2.5-flash","deepseek-v4-flash","claude-haiku-4-5"]' >/tmp/sm
rm -f notes/cn-mode-custom.txt
OUT=$(cnx "Create notes/cn-mode-custom.txt with text custom-ok. Reply DONE.")
if [ -f notes/cn-mode-custom.txt ] && grep -q custom-ok notes/cn-mode-custom.txt; then
  mark "HM.custom" PASS "custom mode write"
else
  mark "HM.custom" FAIL "out=$(echo $OUT|head -c 160)"
fi
set_mode power >/tmp/sm

echo "=== 6/7 files shell ==="
OUT=$(cnx "Read README.md and reply with ONLY its first line.")
FIRST=$(head -1 README.md)
if echo "$OUT" | grep -Fq "$FIRST" || echo "$OUT" | grep -qiE 'ZeusCode|Playground|lab|Continue'; then
  mark "6.1" PASS "read ok"
else
  mark "6.1" FAIL "out=$(echo $OUT|head -c 160)"
fi

rm -f notes/cn-write.txt
OUT=$(cnx "Create notes/cn-write.txt with exact text hello-continue. Reply DONE.")
if [ -f notes/cn-write.txt ] && grep -q hello-continue notes/cn-write.txt; then
  mark "6.2" PASS "write ok"
else
  mark "6.2" FAIL "out=$(echo $OUT|head -c 160)"
fi

printf 'print("hello")\n' > src/hello.py
OUT=$(cnx "Edit src/hello.py so it prints goodbye instead of hello. Reply DONE.")
if grep -qi goodbye src/hello.py; then mark "6.3" PASS "edit ok"; else mark "6.3" FAIL "content=$(cat src/hello.py)"; fi

rm -f "notes/кир-cn.txt"
OUT=$(cnx "Create notes/кир-cn.txt with content: привет. Reply DONE.")
if [ -f "notes/кир-cn.txt" ] && grep -q "привет" "notes/кир-cn.txt"; then
  mark "6.4" PASS "cyrillic filename ok"
else
  mark "6.4" FAIL "out=$(echo $OUT|head -c 120)"
fi

OUT=$(cnx "Run in terminal: pwd && ls. Reply with the pwd path.")
if echo "$OUT" | grep -qiE 'playground|zeus-client-lab'; then mark "7.1" PASS "shell pwd"; else mark "7.1" FAIL "$(echo $OUT|head -c 160)"; fi

rm -f out-cn.txt
OUT=$(cnx "Run: echo hello > out-cn.txt && cat out-cn.txt. Reply DONE.")
if [ -f out-cn.txt ] && grep -q hello out-cn.txt; then mark "7.2" PASS "shell write"; else mark "7.2" FAIL "$(echo $OUT|head -c 160)"; fi

OUT=$(cnx "Run: git status -sb. Reply with first line.")
if echo "$OUT" | grep -qE '##|main'; then mark "7.3" PASS "git status"; else mark "7.3" FAIL "$(echo $OUT|head -c 160)"; fi

OUT=$(cnx "Run: ls /no/such/continue-path ; report that it failed.")
if echo "$OUT" | grep -qiE 'fail|error|no such|not found|cannot'; then mark "7.5" PASS "nonzero visible"; else mark "7.5" FAIL "$(echo $OUT|head -c 160)"; fi

echo "=== Solo models ==="
for m in gemini-2.5-flash deepseek-v4-flash; do
  set_model "$m"
  rm -f "notes/cn-solo-$m.txt"
  OUT=$(cnx "Create notes/cn-solo-$m.txt with text solo-$m-ok. Reply DONE.")
  if [ -f "notes/cn-solo-$m.txt" ] && grep -q "solo-$m-ok" "notes/cn-solo-$m.txt"; then
    mark "SOLO.$m" PASS "write"
  else
    mark "SOLO.$m" FAIL "out=$(echo $OUT|head -c 140)"
  fi
done
set_model zeuscode

echo "=== Mini project ==="
rm -f src/greet_cn.py
OUT=$(cnx "Add src/greet_cn.py with greet(name) returning Hello, {name}!. Run python3 -c \"from src.greet_cn import greet; print(greet('World'))\". Reply with output.")
if [ -f src/greet_cn.py ] && PYTHONPATH="$PLAY" python3 -c "from src.greet_cn import greet; assert 'Hello' in greet('World')" 2>/dev/null; then
  mark "H2" PASS "greet_cn ok"
else
  mark "H2" FAIL "out=$(echo $OUT|head -c 160)"
fi

echo "=== Logs ==="
NULLC=$(journalctl -u zeuscode.service --since "90 min ago" --no-pager 2>/dev/null | grep -c "Message content is null" || true)
TOOLN=$(journalctl -u zeuscode.service --since "90 min ago" --no-pager 2>/dev/null | grep -c "Tool type or function is null" || true)
if [ "${NULLC:-0}" = "0" ]; then mark "11.null" PASS "no null content"; else mark "11.null" FAIL "count=$NULLC"; fi
if [ "${TOOLN:-0}" = "0" ]; then mark "11.tool" PASS "no tool null"; else mark "11.tool" FAIL "count=$TOOLN"; fi

mark "12.tg-ui" SKIP "Telegram UI clicks"
mark "TUI" SKIP "VS Code Continue panel UI"

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
cp "$REPORT" /opt/zeus-client-lab/reports/continue-checklist-latest.md
echo
echo "REPORT=$REPORT"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
exit 0
