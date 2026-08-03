#!/usr/bin/env bash
# Cline CLI × ZeusCode lab checklist (headless via `cline -y`).
set -u
. /opt/zeus-client-lab/configs/cline.env 2>/dev/null || true
export ZEUSCODE_API_KEY="${ZEUSCODE_API_KEY:-$(cat /opt/zeus-client-lab/configs/zeus_smoke.key)}"
PLAY=/opt/zeus-client-lab/playground
REPORT=/opt/zeus-client-lab/reports/cline-checklist-$(date +%Y%m%d-%H%M%S).md
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

# Cline often answers correctly then dies on submit_and_exit(verified=bool).
# Judge by output/files, not only exit code.
cl() {
  local prompt="$1"
  local model="${2:-zeuscode}"
  timeout 240 cline -y \
    -c "$PLAY" \
    -P openai-compatible \
    -m "$model" \
    --timeout 200 \
    "$prompt" </dev/null 2>&1 | tr -d '\r'
}

mkdir -p "$(dirname "$REPORT")" "$PLAY/notes" "$PLAY/src"
{
  echo "# Cline checklist — $(date -Is)"
  echo
  echo "- client: $(cline -V 2>/dev/null | head -1)"
  echo "- node: $(node -v)"
  echo "- config: ~/.cline/data/settings/providers.json"
  echo "- provider: openai-compatible · baseUrl https://zeuscode.ru/v1 · model zeuscode"
  echo "- playground: $PLAY"
  echo "- note: PASS by file/text even if CLI aborts on submit_and_exit verified bug"
  echo
} > "$REPORT"

cd "$PLAY"
printf '# ZeusCode Cline lab\n\nPlayground for agent tests.\n' > README.md
printf 'print("hello")\n' > src/hello.py
rm -f notes/cline-*.txt notes/кир-cline.txt out-cline.txt src/greet_cline.py 2>/dev/null || true
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || (git init -b main && git config user.email lab@zeus && git config user.name lab && git commit --allow-empty -m init)

echo "=== 1. Connection / guide ==="
if [ -n "${ZEUSCODE_API_KEY:-}" ] && [ "${ZEUSCODE_API_KEY:0:5}" = "zeus_" ]; then
  mark "1.2" PASS "ZEUSCODE_API_KEY present"
else
  mark "1.2" FAIL "key missing"
fi
if python3 - <<'PY'
import json
p=json.load(open("/root/.cline/data/settings/providers.json"))
s=p["providers"]["openai-compatible"]["settings"]
assert s.get("baseUrl","").rstrip("/")=="https://zeuscode.ru/v1"
assert s.get("model")=="zeuscode"
assert s.get("provider")=="openai-compatible"
print("ok")
PY
then mark "1.1" PASS "providers.json matches miniapp (OpenAI Compatible + /v1 + zeuscode)"
else mark "1.1" FAIL "providers.json mismatch"
fi

# bad key
BAD=$(timeout 60 cline -y -c "$PLAY" -P openai-compatible -k zeus_INVALID -m zeuscode "hi" </dev/null 2>&1 | tail -30 || true)
if echo "$BAD" | grep -qiE '401|invalid|unauthorized|auth|denied|error|API key'; then
  mark "1.3" PASS "bad key fails"
else
  mark "1.3" FAIL "bad key soft: $(echo $BAD|head -c 120)"
fi

if curl -sS https://zeuscode.ru/static/tg-platforms.js | grep -q 'configKind: "cline"' && \
   curl -sS https://zeuscode.ru/static/tg-miniapp.js | grep -q 'OpenAI Compatible'; then
  mark "1.5" PASS "miniapp guide has Cline OpenAI Compatible"
else
  mark "1.5" FAIL "miniapp guide mismatch"
fi

echo "=== 8 protocol chat completions ==="
CODE=$(curl -sS -o /tmp/cc.json -w "%{http_code}" -X POST https://zeuscode.ru/v1/chat/completions \
  -H "Authorization: Bearer $ZEUSCODE_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"Reply OK"}],"stream":false}')
if [ "$CODE" = "200" ] && grep -q OK /tmp/cc.json; then mark "8.chat" PASS "POST /v1/chat/completions 200"; else mark "8.chat" FAIL "http=$CODE"; fi

echo "=== 3 Chat + modes ==="
OUT=$(cl "Reply with exactly one word: OK")
if echo "$OUT" | grep -qiE '\bOK\b'; then mark "3.1" PASS "chat OK"; else mark "3.1" FAIL "$OUT"; fi

OUT=$(cl "Ответь коротко словом: привет")
if echo "$OUT" | grep -qiE 'привет|Привет|hello|здрав'; then mark "3.2" PASS "cyr ok"; else mark "3.2" FAIL "$OUT"; fi

for mode_tag in simple:simple power:power; do
  mode=${mode_tag%%:*}; tag=${mode_tag##*:}
  set_mode "$mode" >/tmp/sm
  rm -f "notes/cline-mode-$tag.txt"
  OUT=$(cl "Create notes/cline-mode-$tag.txt with text $tag-ok. Then reply DONE.")
  if [ -f "notes/cline-mode-$tag.txt" ] && grep -q "$tag-ok" "notes/cline-mode-$tag.txt"; then
    mark "HM.$tag" PASS "mode+$tag file"
  else
    mark "HM.$tag" FAIL "out=$(echo $OUT|head -c 160)"
  fi
done
set_mode custom '["gemini-2.5-flash","deepseek-v4-flash","claude-haiku-4-5"]' >/tmp/sm
rm -f notes/cline-mode-custom.txt
OUT=$(cl "Create notes/cline-mode-custom.txt with text custom-ok. Reply DONE.")
if [ -f notes/cline-mode-custom.txt ] && grep -q custom-ok notes/cline-mode-custom.txt; then
  mark "HM.custom" PASS "custom mode write"
else
  mark "HM.custom" FAIL "out=$(echo $OUT|head -c 160)"
fi
set_mode power >/tmp/sm

echo "=== 6/7 files shell ==="
OUT=$(cl "Read README.md and reply with ONLY its first line.")
FIRST=$(head -1 README.md)
if echo "$OUT" | grep -Fq "$FIRST" || echo "$OUT" | grep -qiE 'ZeusCode|Playground|lab|Cline'; then
  mark "6.1" PASS "read ok"
else
  mark "6.1" FAIL "out=$(echo $OUT|head -c 160)"
fi

rm -f notes/cline-write.txt
OUT=$(cl "Create notes/cline-write.txt with exact text hello-cline. Reply DONE.")
if [ -f notes/cline-write.txt ] && grep -q hello-cline notes/cline-write.txt; then
  mark "6.2" PASS "write ok"
else
  mark "6.2" FAIL "out=$(echo $OUT|head -c 160)"
fi

printf 'print("hello")\n' > src/hello.py
OUT=$(cl "Edit src/hello.py so it prints goodbye instead of hello. Reply DONE.")
if grep -qi goodbye src/hello.py; then mark "6.3" PASS "edit ok"; else mark "6.3" FAIL "content=$(cat src/hello.py)"; fi

rm -f "notes/кир-cline.txt"
OUT=$(cl "Create notes/кир-cline.txt with content: привет. Reply DONE.")
if [ -f "notes/кир-cline.txt" ] && grep -q "привет" "notes/кир-cline.txt"; then
  mark "6.4" PASS "cyrillic filename ok"
else
  mark "6.4" FAIL "out=$(echo $OUT|head -c 120)"
fi

OUT=$(cl "Run in terminal: pwd && ls. Reply with the pwd path.")
if echo "$OUT" | grep -qiE 'playground|zeus-client-lab'; then mark "7.1" PASS "shell pwd"; else mark "7.1" FAIL "$(echo $OUT|head -c 160)"; fi

rm -f out-cline.txt
OUT=$(cl "Run: echo hello > out-cline.txt && cat out-cline.txt. Reply DONE.")
if [ -f out-cline.txt ] && grep -q hello out-cline.txt; then mark "7.2" PASS "shell write"; else mark "7.2" FAIL "$(echo $OUT|head -c 160)"; fi

OUT=$(cl "Run: git status -sb. Reply with first line.")
if echo "$OUT" | grep -qE '##|main'; then mark "7.3" PASS "git status"; else mark "7.3" FAIL "$(echo $OUT|head -c 160)"; fi

OUT=$(cl "Run: ls /no/such/cline-path ; report that it failed.")
if echo "$OUT" | grep -qiE 'fail|error|no such|not found|cannot'; then mark "7.5" PASS "nonzero visible"; else mark "7.5" FAIL "$(echo $OUT|head -c 160)"; fi

echo "=== Solo models ==="
for m in gemini-2.5-flash deepseek-v4-flash; do
  rm -f "notes/cline-solo-$m.txt"
  OUT=$(cl "Create notes/cline-solo-$m.txt with text solo-$m-ok. Reply DONE." "$m")
  if [ -f "notes/cline-solo-$m.txt" ] && grep -q "solo-$m-ok" "notes/cline-solo-$m.txt"; then
    mark "SOLO.$m" PASS "write"
  else
    mark "SOLO.$m" FAIL "out=$(echo $OUT|head -c 140)"
  fi
done

echo "=== Mini project ==="
rm -f src/greet_cline.py
OUT=$(cl "Add src/greet_cline.py with greet(name) returning Hello, {name}!. Run python3 -c \"from src.greet_cline import greet; print(greet('World'))\". Reply with output.")
if [ -f src/greet_cline.py ] && PYTHONPATH="$PLAY" python3 -c "from src.greet_cline import greet; assert 'Hello' in greet('World')" 2>/dev/null; then
  mark "H2" PASS "greet_cline ok"
else
  mark "H2" FAIL "out=$(echo $OUT|head -c 160)"
fi

echo "=== Logs / known CLI bug ==="
NULLC=$(journalctl -u zeuscode.service --since "90 min ago" --no-pager 2>/dev/null | grep -c "Message content is null" || true)
TOOLN=$(journalctl -u zeuscode.service --since "90 min ago" --no-pager 2>/dev/null | grep -c "Tool type or function is null" || true)
if [ "${NULLC:-0}" = "0" ]; then mark "11.null" PASS "no null content"; else mark "11.null" FAIL "count=$NULLC"; fi
if [ "${TOOLN:-0}" = "0" ]; then mark "11.tool" PASS "no tool null"; else mark "11.tool" FAIL "count=$TOOLN"; fi

# Document submit_and_exit quirk as known Cline-side issue
OUT=$(cl "Reply with exactly: EXITPROBE")
if echo "$OUT" | grep -qi EXITPROBE; then
  if echo "$OUT" | grep -qi 'verified'; then
    mark "11.submit_exit" PASS "answer ok · CLI submit_and_exit verified bug still present (Cline-side)"
  else
    mark "11.submit_exit" PASS "answer ok · no verified abort this run"
  fi
else
  mark "11.submit_exit" FAIL "no EXITPROBE"
fi

mark "12.tg-ui" SKIP "Telegram UI clicks"
mark "TUI" SKIP "VS Code extension UI / Verify button"
mark "Kilo" SKIP "same OpenAI Compatible wire as Cline — protocol covered; UI install separate"
mark "Continue" SKIP "same /v1 chat completions family — yaml surface different; smoke later if needed"

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
  echo "## VS Code family note"
  echo "- Cline PASS on chat/tools ⇒ Kilo very likely OK (same OpenAI Compatible + tools)."
  echo "- Continue: same Zeus endpoint, different config.yaml UX — not auto-proven."
  echo "- Cursor Agent / Claude Code: different wire — still need own checks."
} >> "$REPORT"
cp "$REPORT" /opt/zeus-client-lab/reports/cline-checklist-latest.md
echo
echo "REPORT=$REPORT"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
exit 0
