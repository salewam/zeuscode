#!/usr/bin/env bash
# Claude Code × ZeusCode lab checklist (headless via `claude -p` as zeuslab).
set -u
. /opt/zeus-client-lab/configs/claude.env 2>/dev/null || true
export ZEUSCODE_API_KEY="${ZEUSCODE_API_KEY:-$(cat /opt/zeus-client-lab/configs/zeus_smoke.key)}"
export PATH="/usr/local/bin:$PATH"
PLAY=/opt/zeus-client-lab/playground
REPORT=/opt/zeus-client-lab/reports/claude-checklist-$(date +%Y%m%d-%H%M%S).md
PASS=0; FAIL=0; SKIP=0
declare -a RESULTS
RUN_USER="${CLAUDE_LAB_USER:-zeuslab}"

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

cl() {
  local prompt="$1"
  sudo -u "$RUN_USER" -H env CLAUDE_PROMPT="$prompt" bash -lc "
    export PATH=/usr/local/bin:/usr/bin:\$PATH
    cd '$PLAY'
    printf '%s\n' \"\$CLAUDE_PROMPT\" | timeout 240 claude -p --permission-mode bypassPermissions \
      --allowed-tools Bash,Write,Edit,Read,Glob,Grep 2>&1
  " | tr -d '\r'
}

cl_chat() {
  local prompt="$1"
  sudo -u "$RUN_USER" -H env CLAUDE_PROMPT="$prompt" bash -lc "
    export PATH=/usr/local/bin:/usr/bin:\$PATH
    cd '$PLAY'
    printf '%s\n' \"\$CLAUDE_PROMPT\" | timeout 120 claude -p 2>&1
  " | tr -d '\r'
}

mkdir -p "$(dirname "$REPORT")" "$PLAY/notes" "$PLAY/src"
{
  echo "# Claude Code checklist — $(date -Is)"
  echo
  echo "- client: $(claude --version 2>/dev/null | head -1)"
  echo "- run as: $RUN_USER (root cannot bypassPermissions)"
  echo "- config: ~/.claude/settings.json (miniapp Zeus gateway)"
  echo "- playground: $PLAY"
  echo
} > "$REPORT"

cd "$PLAY"
printf '# ZeusCode Claude lab\n\nPlayground.\n' > README.md
rm -f notes/claude-*.txt notes/кир-claude.txt src/greet_claude.py 2>/dev/null || true
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || (git init -b main && git config user.email lab@zeus && git config user.name lab && git commit --allow-empty -m init)

echo "=== 1. Connection / guide ==="
if [ -n "${ZEUSCODE_API_KEY:-}" ] && [ "${ZEUSCODE_API_KEY:0:5}" = "zeus_" ]; then
  mark "1.2" PASS "ZEUSCODE_API_KEY present"
else
  mark "1.2" FAIL "key missing"
fi
if grep -q 'ANTHROPIC_BASE_URL' /root/.claude/settings.json && grep -q 'zeuscode.ru' /root/.claude/settings.json && ! grep -q 'zeuscode.ru/v1' /root/.claude/settings.json; then
  mark "1.1" PASS "settings.json base without /v1"
else
  mark "1.1" FAIL "settings mismatch"
fi

echo "=== 8.2 Anthropic messages ==="
CODE=$(curl -sS -o /tmp/am.json -w "%{http_code}" -X POST https://zeuscode.ru/v1/messages \
  -H "x-api-key: $ZEUSCODE_API_KEY" -H "anthropic-version: 2023-06-01" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","max_tokens":64,"messages":[{"role":"user","content":"Reply exactly: MSG_OK"}]}')
if [ "$CODE" = "200" ] && grep -q MSG_OK /tmp/am.json; then mark "8.2a" PASS "POST /v1/messages 200"; else mark "8.2a" FAIL "http=$CODE"; fi

CODE=$(curl -sS -o /tmp/am-tools.json -w "%{http_code}" -X POST https://zeuscode.ru/v1/messages \
  -H "x-api-key: $ZEUSCODE_API_KEY" -H "anthropic-version: 2023-06-01" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","max_tokens":128,"messages":[{"role":"user","content":"Use Write tool only if needed; reply OK"}],"tools":[{"name":"Write","description":"write","input_schema":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}]}')
if [ "$CODE" = "200" ]; then mark "8.2b" PASS "messages with tools http 200"; else mark "8.2b" FAIL "http=$CODE body=$(head -c 120 /tmp/am-tools.json)"; fi

DISC=$(curl -sS "https://zeuscode.ru/v1/models?limit=1000" -H "x-api-key: $ZEUSCODE_API_KEY" -H "anthropic-version: 2023-06-01" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data') or []))" 2>/dev/null || echo 0)
if [ "${DISC:-0}" -gt 10 ]; then mark "8.2c" PASS "model discovery count=$DISC"; else mark "8.2c" FAIL "discovery=$DISC"; fi

echo "=== 3 Chat ==="
OUT=$(cl_chat "Reply with exactly one word: OK")
if echo "$OUT" | grep -qiE '\bOK\b'; then mark "3.1" PASS "chat OK"; else mark "3.1" FAIL "$OUT"; fi

echo "=== 6 Write ==="
rm -f notes/claude-write.txt
OUT=$(cl "Create notes/claude-write.txt with exact text hello-claude. Reply DONE.")
if [ -f notes/claude-write.txt ] && grep -q hello-claude notes/claude-write.txt; then
  mark "6.2" PASS "write ok"
else
  mark "6.2" FAIL "out=$(echo $OUT|head -c 160)"
fi

set_mode power >/tmp/sm
rm -f notes/claude-mode-power.txt
OUT=$(cl "Create notes/claude-mode-power.txt with text power-ok. Reply DONE.")
if [ -f notes/claude-mode-power.txt ] && grep -q power-ok notes/claude-mode-power.txt; then
  mark "HM.power" PASS "power mode write"
else
  mark "HM.power" FAIL "out=$(echo $OUT|head -c 160)"
fi

mark "12.tg-ui" SKIP "Telegram UI"
mark "TUI" SKIP "interactive Claude Code UI"

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
cp "$REPORT" /opt/zeus-client-lab/reports/claude-checklist-latest.md
echo
echo "REPORT=$REPORT"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
exit 0
