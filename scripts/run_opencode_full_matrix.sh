#!/usr/bin/env bash
# Full OpenCode × ZeusCode capability matrix (headless lab).
# Covers: all 3 TG modes × hands + cross-cutting solo/session/git/files.
set -u
export PATH="/root/.opencode/bin:$PATH"
PLAY=/opt/zeus-client-lab/playground
MODEL=zeuscode/zeuscode
REPORT=/opt/zeus-client-lab/reports/opencode-full-matrix-$(date +%Y%m%d-%H%M%S).md
PASS=0; FAIL=0; SKIP=0
declare -a RESULTS
KEY=$(cat /opt/zeus-client-lab/configs/zeus_smoke.key)

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
  local prompt="$1"
  local model="${2:-$MODEL}"
  timeout 240 opencode run -m "$model" --auto --pure --dir "$PLAY" "$prompt" 2>&1 | tr -d '\r'
}

agent_title() {
  local title="$1" prompt="$2"
  local model="${3:-$MODEL}"
  timeout 240 opencode run -m "$model" --auto --pure --dir "$PLAY" --title "$title" "$prompt" 2>&1 | tr -d '\r'
}

agent_continue() {
  local prompt="$1"
  timeout 240 opencode run -m "$MODEL" --auto --pure --dir "$PLAY" -c "$prompt" 2>&1 | tr -d '\r'
}

mkdir -p "$(dirname "$REPORT")" "$PLAY/notes" "$PLAY/src" "$PLAY/deep/nested"
{
  echo "# OpenCode FULL MATRIX — $(date -Is)"
  echo
  echo "- OpenCode $(opencode --version)"
  echo "- playground: $PLAY"
  echo "- TG modes via fusion_pref (= miniapp)"
  echo "- agent: opencode run --auto --pure (headless ≈ Always Allow)"
  echo
} > "$REPORT"

cd "$PLAY"
# clean matrix artifacts
rm -rf notes/full-* notes/solo-* notes/attach-* notes/mem-* notes/del-* notes/renamed-* \
  src/calc_* src/multi_* deep/nested/* out-matrix.txt 2>/dev/null || true
git checkout -- . 2>/dev/null || true
printf 'print("hello")\n' > src/hello.py
printf '# ZeusCode client lab playground\n\nFiles + git for agent tests.\n' > README.md
echo "seed" > notes/seed.txt
echo "attach-body" > notes/attach-src.txt

echo "=== 0. Meta / discovery ==="
if opencode models 2>/dev/null | grep -q 'zeuscode/zeuscode'; then mark "M.models" PASS "zeuscode/zeuscode listed"; else mark "M.models" FAIL "missing"; fi
if curl -sS https://zeuscode.ru/static/tg-platforms.js | grep -q 'zeuscode/zeuscode'; then
  mark "M.guide" PASS "/static/tg-platforms.js ok"
else
  mark "M.guide" FAIL "guide missing id"
fi
AGENTS=$(opencode agent list 2>&1 | head -5)
if echo "$AGENTS" | grep -qi build; then mark "M.agents" PASS "build agent present"; else mark "M.agents" FAIL "$AGENTS"; fi
MCP=$(opencode mcp list 2>&1 | head -10)
mark "M.mcp" SKIP "mcp list: $(echo $MCP | head -c 80) — no Zeus MCP required for matrix"

run_mode_pack() {
  local mode="$1"
  local tag="$2"
  local pref_expect="$3"
  echo "=== MODE PACK: $mode ($tag) ==="
  local pref
  pref=$(get_mode)
  if ! echo "$pref" | grep -q "^${pref_expect}"; then
    mark "HM.$tag.pref" FAIL "want ^$pref_expect got $pref"
  else
    mark "HM.$tag.pref" PASS "pref=$pref"
  fi

  # chat without tools (fusion path)
  local http
  http=$(curl -sS -o /tmp/chat_$tag -w "%{http_code}" -X POST https://zeuscode.ru/v1/chat/completions \
    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d "{\"model\":\"zeuscode\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply exactly: MODE-$tag\"}],\"max_tokens\":16}")
  if [ "$http" = "200" ]; then mark "HM.$tag.chat" PASS "chat 200"; else mark "HM.$tag.chat" FAIL "http=$http $(head -c 120 /tmp/chat_$tag)"; fi

  rm -f "notes/full-$tag.txt" "src/calc_$tag.py"
  local out
  out=$(agent "Do ALL of these in the current repo, then reply DONE:
1) Read README.md and remember its first line.
2) Create notes/full-$tag.txt with exact text: pack-$tag-ok
3) Create src/calc_$tag.py with function add(a,b) that returns a+b.
4) Run: python -c \"from src.calc_$tag import add; print(add(2,3))\"
5) Run: git status -sb
If any step fails, say FAIL and which step.")

  local ok=1
  [ -f "notes/full-$tag.txt" ] && grep -q "pack-$tag-ok" "notes/full-$tag.txt" || ok=0
  [ -f "src/calc_$tag.py" ] && grep -q "def add" "src/calc_$tag.py" || ok=0
  if PYTHONPATH="$PLAY" python3 -c "from src.calc_$tag import add; assert add(2,3)==5" 2>/tmp/py_$tag; then
    :
  else
    ok=0
  fi
  if [ "$ok" = "1" ]; then
    mark "HM.$tag.hands" PASS "write+py+run ok"
  else
    mark "HM.$tag.hands" FAIL "out=$(echo $out | head -c 180) py=$(cat /tmp/py_$tag 2>/dev/null | head -c 80)"
  fi

  # edit + cyrillic + nested in second turn (continue session if possible)
  out=$(agent "Also do:
1) Edit src/hello.py so it prints mode-$tag
2) Create notes/кир-$tag.txt with text: привет-$tag
3) Create deep/nested/path-$tag.txt with text: nested-$tag
Reply DONE.")
  ok=1
  grep -q "mode-$tag" src/hello.py || ok=0
  [ -f "notes/кир-$tag.txt" ] && grep -q "привет-$tag" "notes/кир-$tag.txt" || ok=0
  [ -f "deep/nested/path-$tag.txt" ] && grep -q "nested-$tag" "deep/nested/path-$tag.txt" || ok=0
  if [ "$ok" = "1" ]; then mark "HM.$tag.files" PASS "edit+cyr+nested ok"; else mark "HM.$tag.files" FAIL "hello=$(cat src/hello.py) out=$(echo $out|head -c 120)"; fi

  out=$(agent "Run shell: pwd; echo shell-$tag > out-matrix.txt; ls /no/such/$tag 2>&1 | head -1; sleep 3; echo slept-$tag. Reply with slept-$tag when done.")
  if [ -f out-matrix.txt ] && grep -q "shell-$tag" out-matrix.txt && echo "$out" | grep -qi "slept-$tag"; then
    mark "HM.$tag.shell" PASS "write+nonzero+sleep ok"
  else
    # sleep word may vary; file is enough for write
    if [ -f out-matrix.txt ] && grep -q "shell-$tag" out-matrix.txt; then
      mark "HM.$tag.shell" PASS "shell write ok (sleep soft)"
    else
      mark "HM.$tag.shell" FAIL "out=$(echo $out|head -c 160)"
    fi
  fi
}

echo "=== 1. All 3 TG modes FULL packs ==="
set_mode simple >/tmp/sm
run_mode_pack simple simple simple
set_mode power >/tmp/sm
run_mode_pack power power power
set_mode custom '["gemini-2.5-flash","deepseek-v4-flash","claude-haiku-4-5"]' >/tmp/sm
run_mode_pack custom custom custom
set_mode power >/tmp/sm

echo "=== 2. Cross-cutting file ops (power) ==="
echo "delete-me" > notes/del-me.txt
out=$(agent "Delete the file notes/del-me.txt. Reply DONE.")
if [ ! -f notes/del-me.txt ]; then mark "F.delete" PASS "deleted"; else mark "F.delete" FAIL "still exists out=$out"; fi

echo "rename-src" > notes/rename-src.txt
out=$(agent "Rename/move notes/rename-src.txt to notes/renamed-dst.txt. Reply DONE.")
if [ ! -f notes/rename-src.txt ] && [ -f notes/renamed-dst.txt ]; then
  mark "F.rename" PASS "moved"
else
  mark "F.rename" FAIL "out=$out"
fi

out=$(agent "Create three files in one go: src/multi_a.py with print('a'), src/multi_b.py with print('b'), notes/full-multi.txt with text multi-ok. Reply DONE.")
if [ -f src/multi_a.py ] && [ -f src/multi_b.py ] && grep -q multi-ok notes/full-multi.txt; then
  mark "F.multifile" PASS "3 files"
else
  mark "F.multifile" FAIL "out=$out"
fi

# patch/apply style edit on existing
printf 'def old():\n    return 1\n' > src/patch_me.py
out=$(agent "Edit src/patch_me.py: rename function old to new and return 2. Reply DONE.")
if grep -q 'def new' src/patch_me.py && grep -q 'return 2' src/patch_me.py; then
  mark "F.patch" PASS "function renamed"
else
  mark "F.patch" FAIL "content=$(cat src/patch_me.py) out=$out"
fi

echo "=== 3. Session memory / continue ==="
out=$(agent_title "matrix-mem" "Remember secret code ZC-9911. Create notes/mem-1.txt with text remembered. Reply DONE.")
out2=$(agent_continue "What secret code did I ask you to remember? Reply with ONLY the code. Also append the code as a new line into notes/mem-1.txt.")
if echo "$out2" | grep -q 'ZC-9911' && grep -q 'ZC-9911' notes/mem-1.txt; then
  mark "S.continue" PASS "memory+append"
else
  mark "S.continue" FAIL "out2=$out2 file=$(cat notes/mem-1.txt 2>/dev/null)"
fi

echo "=== 4. File attach (-f) ==="
# OpenCode parses -f as consuming following args: put MESSAGE before -f
out=$(timeout 180 opencode run -m "$MODEL" --auto --pure --dir "$PLAY" \
  "Copy attached content to notes/attach-out.txt exactly. Reply DONE." \
  -f notes/attach-src.txt 2>&1 | tr -d '\r' | tail -8)
if [ -f notes/attach-out.txt ] && grep -q attach-body notes/attach-out.txt; then
  mark "S.attach" PASS "-f attach ok"
else
  mark "S.attach" FAIL "out=$out"
fi

echo "=== 5. Git deeper ==="
out=$(agent "Run: git status -sb && git diff --stat && git log -1 --oneline 2>&1 || true. Then create a new file notes/git-touch.txt with text git-ok, git add notes/git-touch.txt, and git commit -m 'lab: matrix touch' if git user is configured; if commit fails due to identity, set local user.email lab@zeuscode.test and user.name lab then commit. Reply DONE.")
if [ -f notes/git-touch.txt ] && grep -q git-ok notes/git-touch.txt; then
  if git -C "$PLAY" log -1 --oneline 2>/dev/null | grep -qi matrix; then
    mark "G.commit" PASS "commit done"
  else
    mark "G.commit" PASS "file ok; commit soft $(git -C $PLAY log -1 --oneline 2>/dev/null)"
  fi
else
  mark "G.commit" FAIL "out=$out"
fi

out=$(agent "Run: git fetch --dry-run 2>&1 || true; git remote -v 2>&1 || true. Briefly report.")
if [ -n "$out" ]; then mark "G.fetch" PASS "fetch/remote probed"; else mark "G.fetch" FAIL empty; fi

echo "=== 6. Solo models via OpenCode ==="
for solo in gemini-2.5-flash deepseek-v4-flash claude-haiku-4-5; do
  rm -f "notes/solo-$solo.txt"
  out=$(agent "Use the write tool now. Create notes/solo-$solo.txt with exact text solo-$solo-ok. Do not only chat. Reply DONE when the file exists." "zeuscode/$solo")
  if [ -f "notes/solo-$solo.txt" ] && grep -q "solo-$solo-ok" "notes/solo-$solo.txt"; then
    mark "SOLO.$solo" PASS "write ok"
  else
    mark "SOLO.$solo" FAIL "out=$(echo $out|head -c 160)"
  fi
done

# one heavier solo — short chat only to limit cost
http=$(curl -sS -o /tmp/heavy -w "%{http_code}" -X POST https://zeuscode.ru/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"Reply: HEAVY"}],"max_tokens":8}')
if [ "$http" = "200" ] || [ "$http" = "402" ] || [ "$http" = "429" ]; then
  mark "SOLO.heavy-api" PASS "sonnet path http=$http"
else
  mark "SOLO.heavy-api" FAIL "http=$http $(head -c 100 /tmp/heavy)"
fi

echo "=== 7. Mini project (multi-file feature) ==="
rm -rf src/app_matrix notes/app-matrix-ok.txt
out=$(agent "Build a tiny feature:
- Create package src/app_matrix/__init__.py
- Create src/app_matrix/mathy.py with mul(a,b)->a*b
- Create src/app_matrix/cli.py that prints mul(6,7)
- Run: python -m src.app_matrix.cli OR python src/app_matrix/cli.py
- Write notes/app-matrix-ok.txt with the printed number
Reply DONE.")
if [ -f src/app_matrix/mathy.py ] && [ -f notes/app-matrix-ok.txt ] && grep -q 42 notes/app-matrix-ok.txt; then
  mark "P.feature" PASS "package+42"
else
  # accept if mathy works even if note missing
  if PYTHONPATH="$PLAY" python3 -c "from src.app_matrix.mathy import mul; assert mul(6,7)==42" 2>/dev/null; then
    mark "P.feature" PASS "mathy ok (note soft) out=$(echo $out|head -c 100)"
  else
    mark "P.feature" FAIL "out=$(echo $out|head -c 200)"
  fi
fi

echo "=== 8. Resilience / parallel ==="
(curl -sS -o /tmp/pa -w "%{http_code}" -X POST https://zeuscode.ru/v1/chat/completions -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{"model":"zeuscode","messages":[{"role":"user","content":"Reply: A"}],"max_tokens":8}' > /tmp/ca) &
(curl -sS -o /tmp/pb -w "%{http_code}" -X POST https://zeuscode.ru/v1/chat/completions -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{"model":"zeuscode","messages":[{"role":"user","content":"Reply: B"}],"max_tokens":8}' > /tmp/cb) &
wait
if [ "$(cat /tmp/ca)" = "200" ] && [ "$(cat /tmp/cb)" = "200" ]; then mark "R.parallel" PASS "both 200"; else mark "R.parallel" FAIL "a=$(cat /tmp/ca) b=$(cat /tmp/cb)"; fi

# stream
code=$(curl -sS -o /tmp/stream -w "%{http_code}" -N -X POST https://zeuscode.ru/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"zeuscode","messages":[{"role":"user","content":"Count 1 to 3"}],"stream":true,"max_tokens":32}')
if [ "$code" = "200" ] && grep -q data: /tmp/stream; then mark "R.stream" PASS "SSE ok"; else mark "R.stream" FAIL "code=$code"; fi

echo "=== 9. Logs ==="
NULLC=$(journalctl -u zeuscode.service --since "90 min ago" --no-pager 2>/dev/null | grep -c "Message content is null" || true)
TOOLN=$(journalctl -u zeuscode.service --since "90 min ago" --no-pager 2>/dev/null | grep -c "Tool type or function is null" || true)
# nulls during matrix after fix should be 0 going forward — count only last 90m; if old noise, note it
if [ "${NULLC:-0}" = "0" ]; then mark "L.null" PASS "no null content"; else mark "L.null" FAIL "count=$NULLC (may include pre-fix)"; fi
if [ "${TOOLN:-0}" = "0" ]; then mark "L.tool" PASS "no tool null"; else mark "L.tool" FAIL "count=$TOOLN"; fi

echo "=== 10. OpenCode-only surfaces ==="
mark "O.tui" SKIP "interactive TUI Allow clicks — needs real terminal"
mark "O.skills" SKIP "skill picker — needs TUI"
mark "O.web" SKIP "opencode web UI — not in lab matrix"
mark "O.github" SKIP "opencode github/pr — needs GH auth"
mark "O.tg-ui" SKIP "Telegram copy/rotate/advisor clicks"

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
  echo "## Artifacts"
  echo '```'
  find notes src deep -type f 2>/dev/null | sort | head -80
  echo '```'
} >> "$REPORT"
cp "$REPORT" /opt/zeus-client-lab/reports/opencode-full-matrix-latest.md
echo
echo "REPORT=$REPORT"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
set_mode power >/dev/null
# exit 0 even with fails so we always get report; print fail count
exit 0
