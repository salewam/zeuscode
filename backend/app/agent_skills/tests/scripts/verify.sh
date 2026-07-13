#!/usr/bin/env bash
# Tests skill artifact smoke-check.
set -euo pipefail
ROOT="${1:-.}"
fail=0
say(){ printf '%s\n' "$*"; }
err(){ say "FAIL: $*"; fail=1; }
ok(){ say "OK: $*"; }

[[ -d "$ROOT/src/tests" ]] && ROOT="$ROOT/src/tests"
py=$(find "$ROOT" -name '*.py' 2>/dev/null | wc -l | tr -d ' ')
[[ "$py" -eq 0 ]] && err "нет .py в $ROOT" || ok "$py python files"

if grep -RInE 'f["'\''](SELECT|INSERT|UPDATE|DELETE)|["'\''](SELECT|INSERT|UPDATE|DELETE).*\.format\(' "$ROOT" --include='*.py' 2>/dev/null | head -8; then
  err "SQL f-string/format в тестах"
else ok "no SQL f-string"; fi

if grep -RInE '@pytest\.mark\.skip|pytest\.skip\(' "$ROOT" --include='*.py' 2>/dev/null | head -5; then
  err "skip запрещён"
else ok "no skip"; fi

if grep -RInE 'sk-[a-zA-Z0-9]{20,}' "$ROOT" --include='*.py' 2>/dev/null | head -5; then
  err "секреты в тестах"
else ok "no secrets"; fi

if ! grep -RInE '^def test_|^async def test_|^[[:space:]]+def test_|^[[:space:]]+async def test_' "$ROOT" --include='*.py' >/dev/null 2>&1; then
  err "нет def test_"
else ok "test functions present"; fi

if ! grep -RInE 'assert |assertEqual' "$ROOT" --include='*.py' >/dev/null 2>&1; then
  err "нет assert"
else ok "asserts present"; fi

[[ "$fail" -ne 0 ]] && { say "verify: FAILED"; exit 1; }
say "verify: OK"
exit 0
