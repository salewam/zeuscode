#!/usr/bin/env bash
set -u
export PATH="/root/.opencode/bin:$PATH"
KEY=$(cat /opt/zeus-client-lab/configs/zeus_smoke.key)
PLAY=/opt/zeus-client-lab/playground
REPORT=/opt/zeus-client-lab/reports/opencode-checklist-$(date +%Y%m%d-%H%M%S).md
BASE=https://zeuscode.ru/v1
MODEL=zeuscode/zeuscode
PASS=0; FAIL=0; SKIP=0
declare -a RESULTS

mark() {
  local id="$1" status="$2" note="$3"
  # sanitize note for markdown table
  note=$(echo "$note" | tr '\n|' ' /' | head -c 200)
  RESULTS+=("| $id | $status | $note |")
  case "$status" in
    PASS) PASS=$((PASS+1)); echo "  PASS $id — $note" ;;
    FAIL) FAIL=$((FAIL+1)); echo "  FAIL $id — $note" ;;
    SKIP) SKIP=$((SKIP+1)); echo "  SKIP $id — $note" ;;
  esac
}

run_agent() {
  local prompt="$1"
  timeout 180 opencode run -m "$MODEL" --auto --pure --dir "$PLAY" "$prompt" 2>&1 | tr -d '\r'
}

mkdir -p "$(dirname "$REPORT")"
{
  echo "# OpenCode checklist — $(date -Is)"
  echo
  echo "- client: OpenCode $(opencode --version)"
  echo "- playground: $PLAY"
  echo "- model: $MODEL"
  echo
} > "$REPORT"

cd "$PLAY"
rm -f notes/test.txt notes/кириллица.txt out.txt 2>/dev/null || true
printf 'print("hello")\n' > src/hello.py

echo "=== 1. Connection ==="
if opencode models 2>/dev/null | grep -q "zeuscode/zeuscode"; then
  mark "1.1" PASS "baseURL/models see zeuscode/zeuscode"
else
  mark "1.1" FAIL "models missing zeuscode"
fi

CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"ping"}],"max_tokens":8}')
if [ "$CODE" = "200" ]; then mark "1.2" PASS "valid key -> 200"; else mark "1.2" FAIL "valid key -> $CODE"; fi

CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer zeus_INVALID_KEY_TEST" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"ping"}],"max_tokens":8}')
if [ "$CODE" = "401" ]; then mark "1.3" PASS "bad key -> 401"; else mark "1.3" FAIL "bad key -> $CODE"; fi

CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -H "Authorization: Bearer $KEY" "$BASE/models")
if [ "$CODE" = "200" ] && grep -q zeuscode /tmp/zc_body; then
  mark "1.4" PASS "GET /models has zeuscode"
else
  mark "1.4" FAIL "GET /models -> $CODE"
fi

if curl -sS "https://zeuscode.ru/tg/tg-platforms.js?v=clients17" | grep -q 'zeuscode/zeuscode'; then
  mark "1.5" PASS "miniapp guide model id zeuscode/zeuscode"
else
  mark "1.5" FAIL "miniapp guide model id mismatch"
fi

echo "=== 2. Models ==="
OUT=$(timeout 90 opencode run -m "$MODEL" --auto --pure "Ответь одним словом: OK" 2>&1 | tr -d '\r' | tail -5)
if echo "$OUT" | grep -qiE '\bOK\b'; then mark "2.1" PASS "zeuscode -> $OUT"; else mark "2.1" FAIL "out=$OUT"; fi

CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"Reply with exactly: ADV"}],"max_tokens":16}')
if [ "$CODE" = "200" ]; then mark "2.2" PASS "zeuscode 200 (TG Advanced is server-side pref)"; else mark "2.2" FAIL "$CODE"; fi

mark "2.3" SKIP "TG Custom panel — miniapp UI only"

CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"gemini-2.5-flash","messages":[{"role":"user","content":"Reply with exactly: OK"}],"max_tokens":16}')
BODY=$(head -c 300 /tmp/zc_body)
if [ "$CODE" = "200" ]; then mark "2.4" PASS "gemini-2.5-flash -> 200"; else mark "2.4" FAIL "$CODE $BODY"; fi

CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"Reply with exactly: OK"}],"max_tokens":16}')
BODY=$(head -c 300 /tmp/zc_body)
if [ "$CODE" = "200" ] || [ "$CODE" = "402" ] || [ "$CODE" = "403" ] || [ "$CODE" = "429" ]; then
  mark "2.5" PASS "heavy/solo path -> $CODE"
else
  mark "2.5" FAIL "$CODE $BODY"
fi

CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"no-such-model-xyz","messages":[{"role":"user","content":"hi"}],"max_tokens":8}')
if [ "$CODE" = "400" ] || [ "$CODE" = "404" ] || [ "$CODE" = "422" ]; then
  mark "2.6" PASS "bad model -> $CODE"
else
  mark "2.6" FAIL "bad model -> $CODE"
fi

CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"ZeusCode","messages":[{"role":"user","content":"Reply: OK"}],"max_tokens":8}')
if [ "$CODE" = "200" ]; then mark "2.7" PASS "ZeusCode case -> 200"; else mark "2.7" FAIL "case -> $CODE"; fi

echo "=== 3. Simple chat ==="
OUT=$(timeout 90 opencode run -m "$MODEL" --auto --pure "Ответь одним словом: OK" 2>&1 | tr -d '\r' | tail -3)
if echo "$OUT" | grep -qiE '\bOK\b'; then mark "3.1" PASS "$OUT"; else mark "3.1" FAIL "$OUT"; fi

OUT=$(timeout 90 opencode run -m "$MODEL" --auto --pure "Ответь коротко: привет" 2>&1 | tr -d '\r' | tail -5)
if [ -n "$OUT" ] && ! echo "$OUT" | grep -qiE 'error|401|502'; then mark "3.2" PASS "cyr: $OUT"; else mark "3.2" FAIL "$OUT"; fi

OUT1=$(timeout 90 opencode run -m "$MODEL" --auto --pure --title "lab-dialog" "Запомни число 42. Ответь: запомнил" 2>&1 | tr -d '\r' | tail -3)
OUT2=$(timeout 90 opencode run -m "$MODEL" --auto --pure -c "Какое число я просил запомнить? Одним словом." 2>&1 | tr -d '\r' | tail -5)
if echo "$OUT2" | grep -q "42"; then mark "3.3" PASS "context: $OUT2"; else mark "3.3" FAIL "out1=$OUT1 out2=$OUT2"; fi

CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"   "}],"max_tokens":8}')
if [ "$CODE" != "500" ]; then mark "3.4" PASS "whitespace -> $CODE (not 500)"; else mark "3.4" FAIL "whitespace -> 500"; fi

python3 - <<'PY' > /tmp/long_prompt.json
import json
msg = "Repeat the word END after this block.\n" + ("x" * 60000)
print(json.dumps({"model":"zeuscode","messages":[{"role":"user","content":msg}],"max_tokens":16}))
PY
CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  --data-binary @/tmp/long_prompt.json)
if [ "$CODE" = "200" ] || [ "$CODE" = "400" ] || [ "$CODE" = "413" ]; then
  mark "3.5" PASS "long prompt -> $CODE"
else
  mark "3.5" FAIL "long prompt -> $CODE"
fi

echo "=== 4. Streaming ==="
CODE=$(curl -sS -o /tmp/zc_stream -w "%{http_code}" -N -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"Count from 1 to 5, one number per line."}],"stream":true,"max_tokens":64}')
if [ "$CODE" = "200" ] && grep -q "data:" /tmp/zc_stream; then
  mark "4.1" PASS "SSE data frames present"
else
  mark "4.1" FAIL "$CODE"
fi

timeout 1 curl -sS -N -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"Write a long poem about servers."}],"stream":true,"max_tokens":200}' >/tmp/zc_abort 2>/dev/null || true
CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"Reply: OK"}],"max_tokens":8}')
if [ "$CODE" = "200" ]; then mark "4.2" PASS "after mid-stream abort -> 200"; else mark "4.2" FAIL "after abort -> $CODE"; fi

CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"Reply: OK"}],"stream":false,"max_tokens":8}')
if [ "$CODE" = "200" ] && ! grep -q "^data:" /tmp/zc_body; then
  mark "4.3" PASS "non-stream JSON 200"
else
  mark "4.3" FAIL "$CODE"
fi

echo "=== 5/6/7 Tools files shell ==="
OUT=$(run_agent "Read the file README.md in the current directory and reply with ONLY the first line of its content, nothing else.")
FIRST=$(head -1 README.md)
if echo "$OUT" | grep -Fq "$FIRST" || echo "$OUT" | grep -qiE 'ZeusCode|playground|lab|client'; then
  mark "5.1" PASS "read tool ok"
  mark "6.1" PASS "README read ok"
else
  mark "5.1" FAIL "out=$OUT expect~$FIRST"
  mark "6.1" FAIL "out=$OUT"
fi

rm -f notes/test.txt
OUT=$(run_agent "Create a file notes/test.txt with exactly this content: hello-from-opencode. Then reply DONE.")
if [ -f notes/test.txt ] && grep -q "hello-from-opencode" notes/test.txt; then
  mark "5.2" PASS "write via agent"
  mark "6.2" PASS "notes/test.txt created"
else
  mark "5.2" FAIL "file missing; out=$OUT"
  mark "6.2" FAIL "out=$OUT"
fi

OUT=$(run_agent "Edit src/hello.py so it prints goodbye instead of hello. Reply DONE when done.")
if grep -qi goodbye src/hello.py; then
  mark "6.3" PASS "edit applied"
else
  mark "6.3" FAIL "hello.py content unchanged; out=$OUT"
fi

rm -f "notes/кириллица.txt"
OUT=$(run_agent "Create file notes/кириллица.txt with content: привет мир. Reply DONE.")
if [ -f "notes/кириллица.txt" ] && grep -q "привет" "notes/кириллица.txt"; then
  mark "6.4" PASS "cyrillic filename+body ok"
else
  mark "6.4" FAIL "out=$OUT"
fi
mark "6.5" SKIP "image/binary — not in OpenCode CLI smoke"

OUT=$(run_agent "Run shell command: pwd && ls -la. Reply with the pwd path only on the last line.")
if echo "$OUT" | grep -qiE 'playground|zeus-client-lab'; then
  mark "7.1" PASS "pwd/ls via tool"
else
  mark "7.1" FAIL "$OUT"
fi

rm -f out.txt
OUT=$(run_agent "Run: echo hello > out.txt && cat out.txt. Reply DONE.")
if [ -f out.txt ] && grep -q hello out.txt; then
  mark "7.2" PASS "shell write out.txt"
else
  mark "7.2" FAIL "out=$OUT"
fi

OUT=$(run_agent "Run: git status -sb. Reply with the exact first line of the output.")
if echo "$OUT" | grep -qE '##|main'; then mark "7.3" PASS "git status ok"; else mark "7.3" FAIL "$OUT"; fi

OUT=$(run_agent "Run: git fetch --dry-run 2>&1 || true; then reply with OK or the error briefly.")
if [ -n "$OUT" ]; then mark "7.4" PASS "git fetch attempted"; else mark "7.4" FAIL "empty"; fi

OUT=$(run_agent "Run: ls /no/such/path/zzz ; then report that it failed. One short sentence.")
if echo "$OUT" | grep -qiE 'fail|error|no such|not found|exit|cannot'; then
  mark "7.5" PASS "nonzero exit visible"
else
  mark "7.5" FAIL "$OUT"
fi

OUT=$(run_agent "Run: sleep 15 && echo slept. Reply with the word slept when done.")
if echo "$OUT" | grep -qi slept; then mark "7.6" PASS "sleep 15 ok"; else mark "7.6" FAIL "$OUT"; fi

TOOLS='[{"type":"function","function":{"name":"get_time","description":"time","parameters":{"type":"object","properties":{}}}}]'
CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"zeuscode\",\"messages\":[{\"role\":\"user\",\"content\":\"What time? Use get_time tool.\"}],\"tools\":$TOOLS,\"tool_choice\":\"auto\",\"max_tokens\":64}")
if [ "$CODE" = "200" ]; then mark "5.3" PASS "tools+tool_choice -> 200"; else mark "5.3" FAIL "$CODE"; fi

CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[
    {"role":"user","content":"call tool"},
    {"role":"assistant","content":null,"tool_calls":[{"id":"c1","type":"function","function":{"name":"get_time","arguments":"{}"}}]},
    {"role":"tool","tool_call_id":"c1","content":"12:00"},
    {"role":"user","content":"Reply OK"}
  ],"max_tokens":16}')
if [ "$CODE" = "200" ]; then mark "5.4" PASS "role=tool history -> 200"; else mark "5.4" FAIL "$CODE"; fi

CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[
    {"role":"user","content":"x"},
    {"role":"assistant","tool_calls":[
      {"id":"a","type":"function","function":{"name":"get_time","arguments":"{}"}},
      {"id":"b","type":"function","function":{"name":"get_time","arguments":"{}"}}
    ]},
    {"role":"tool","tool_call_id":"a","content":"1"},
    {"role":"tool","tool_call_id":"b","content":"2"},
    {"role":"user","content":"Reply OK"}
  ],"max_tokens":16}')
if [ "$CODE" = "200" ]; then mark "5.5" PASS "parallel tool_calls -> 200"; else mark "5.5" FAIL "$CODE"; fi

CODE=$(curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"hi"}],"tools":[{"type":null,"function":null}],"max_tokens":16}')
if [ "$CODE" = "200" ]; then mark "5.6" PASS "null tool schema -> 200"; else mark "5.6" FAIL "$CODE"; fi

echo "=== 8. Special protocols ==="
mark "8.x" SKIP "OpenCode uses OpenAI chat; responses/anthropic N/A"

echo "=== 9. Billing ==="
# Discover spent column via postgres
SCHEMA=$(docker exec zeuscode-postgres psql -U fusion -d fusion -tAc \
  "SELECT column_name FROM information_schema.columns WHERE table_name='api_keys' ORDER BY 1;" 2>/dev/null || true)
SPENT_BEFORE=$(docker exec zeuscode-postgres psql -U fusion -d fusion -tAc \
  "SELECT coalesce(total_spent_rub, spent_rub, 0) FROM api_keys WHERE key LIKE 'zeus_jzWQphq%' OR key_prefix='zeus_jzWQphq' LIMIT 1;" 2>/dev/null | tr -d ' ' || echo "")
if [ -z "$SPENT_BEFORE" ]; then
  SPENT_BEFORE=$(docker exec zeuscode-postgres psql -U fusion -d fusion -tAc \
    "SELECT id::text||':'||coalesce(budget_rub::text,'') FROM api_keys ORDER BY id DESC LIMIT 3;" 2>/dev/null || echo "")
  mark "9.1" SKIP "billing schema unclear; cols= $(echo $SCHEMA | head -c 120)"
else
  curl -sS -o /tmp/zc_body -w "%{http_code}" -X POST "$BASE/chat/completions" \
    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d '{"model":"zeuscode","messages":[{"role":"user","content":"Reply: BILL"}],"max_tokens":8}' >/tmp/c_bill
  sleep 2
  SPENT_AFTER=$(docker exec zeuscode-postgres psql -U fusion -d fusion -tAc \
    "SELECT coalesce(total_spent_rub, spent_rub, 0) FROM api_keys WHERE key LIKE 'zeus_jzWQphq%' OR key_prefix='zeus_jzWQphq' LIMIT 1;" 2>/dev/null | tr -d ' ')
  mark "9.1" PASS "spent probe before=$SPENT_BEFORE after=$SPENT_AFTER"
fi
mark "9.2" SKIP "budget=0 — do not burn smoke key"
mark "9.3" SKIP "burst rate-limit — separate run"

echo "=== 10. Resilience ==="
mark "10.1" SKIP "forced 502 — not on prod"
(curl -sS -o /tmp/p1 -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"Reply: A"}],"max_tokens":8}' > /tmp/c1) &
(curl -sS -o /tmp/p2 -w "%{http_code}" -X POST "$BASE/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"Reply: B"}],"max_tokens":8}' > /tmp/c2) &
wait
C1=$(cat /tmp/c1); C2=$(cat /tmp/c2)
if [ "$C1" = "200" ] && [ "$C2" = "200" ]; then mark "10.2" PASS "parallel both 200"; else mark "10.2" FAIL "c1=$C1 c2=$C2"; fi

OUT=$(timeout 90 opencode run -m "$MODEL" --auto --pure --title "switch" "Say ONE" 2>&1 | tail -2)
OUT=$(timeout 90 opencode run -m "$MODEL" --auto --pure -c "Reply: TWO" 2>&1 | tail -3)
if [ -n "$OUT" ]; then mark "10.3" PASS "continue session ok"; else mark "10.3" FAIL "empty"; fi
mark "10.4" SKIP "key rotate — miniapp manual"

echo "=== 11. Logs ==="
LOG_HIT=$(docker logs --since 30m zeuscode-api 2>&1 | grep -c "Tool type or function is null" || true)
ERR502=$(docker logs --since 30m zeuscode-api 2>&1 | grep -c ' 502 ' || true)
if [ "${LOG_HIT:-0}" = "0" ]; then mark "11.1" PASS "no Tool type null in 30m"; else mark "11.1" FAIL "count=$LOG_HIT"; fi
if [ "${ERR502:-0}" -lt 20 ]; then mark "11.2" PASS "502 noise last 30m=$ERR502"; else mark "11.2" FAIL "502 count=$ERR502"; fi
if docker logs --since 30m zeuscode-api 2>&1 | grep -q prompt_preview; then
  mark "11.3" PASS "prompt_preview in logs"
else
  mark "11.3" SKIP "prompt_preview not in sample"
fi

echo "=== 12. Miniapp ==="
mark "12.x" SKIP "miniapp UI — one manual pass per lab session"

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

cp "$REPORT" /opt/zeus-client-lab/reports/opencode-checklist-latest.md
echo
echo "REPORT=$REPORT"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
exit "$FAIL"
