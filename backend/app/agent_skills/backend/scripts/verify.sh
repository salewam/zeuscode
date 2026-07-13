#!/usr/bin/env bash
# Backend skill artifact smoke-check.
# Usage: ./scripts/verify.sh /path/to/src/backend
# Exit 0 = ok, 1 = fail

set -euo pipefail

ROOT="${1:-.}"
fail=0

say() { printf '%s\n' "$*"; }
err() { say "FAIL: $*"; fail=1; }
ok() { say "OK: $*"; }

if [[ ! -d "$ROOT" ]]; then
  err "нет директории $ROOT"
  say "verify: FAILED"
  exit 1
fi

if [[ -d "$ROOT/src/backend" ]]; then
  ROOT="$ROOT/src/backend"
fi

py_count="$(find "$ROOT" -name '*.py' 2>/dev/null | wc -l | tr -d ' ')"
if [[ "$py_count" -eq 0 ]]; then
  err "нет .py файлов в $ROOT"
else
  ok "$py_count python files"
fi

if grep -RInE 'f["'\''](SELECT|INSERT|UPDATE|DELETE)|["'\''](SELECT|INSERT|UPDATE|DELETE).*\.format\(' "$ROOT" \
  --include='*.py' 2>/dev/null | head -8; then
  err "подозрение на SQL через f-string/format"
else
  ok "no obvious SQL f-string"
fi

if grep -RInE 'sk-[a-zA-Z0-9]{20,}|api[_-]?key\s*=\s*["'\''][^"'\'']{8,}|password\s*=\s*["'\''][^"'\'']+["'\'']|SECRET(_KEY)?\s*=\s*["'\''][^"'\'']{8,}["'\'']' "$ROOT" \
  --include='*.py' 2>/dev/null | head -8; then
  err "похоже на секреты / захардкоженные credentials"
else
  ok "no obvious secrets"
fi

if grep -RInE 'except\s*:' "$ROOT" --include='*.py' 2>/dev/null | head -5; then
  err "голый except: — лови конкретные исключения"
else
  ok "no bare except"
fi

if grep -RInE 'print\(.*(password|token|authorization)|return \{[^}]*["'\'']password["'\'']' "$ROOT" \
  --include='*.py' -i 2>/dev/null | head -5; then
  err "password/token в print/return — см. security DoD"
fi

if ! grep -RInE 'APIRouter|FastAPI\(' "$ROOT" --include='*.py' >/dev/null 2>&1; then
  err "нет APIRouter/FastAPI app — похоже не API-артефакт"
else
  ok "router/app signal present"
fi

# Public contract should not use response_model=dict
if grep -RInE 'response_model\s*=\s*dict\b' "$ROOT" --include='*.py' 2>/dev/null | head -5; then
  err "response_model=dict — нужен Pydantic Out"
else
  ok "no response_model=dict"
fi

# If path params look like resource ids, expect ownership or 404 pattern somewhere
if grep -RInE '@router\.(get|patch|put|delete)\(["'\''][^"'\'']*\{' "$ROOT" --include='*.py' >/dev/null 2>&1; then
  if ! grep -RInE 'user_id|HTTP_404|404|Not found|not found' "$ROOT" --include='*.py' >/dev/null 2>&1; then
    err "есть path-id роуты, но нет явного 404/ownership сигнала"
  else
    ok "ownership/404 signals present"
  fi
fi

if [[ "$fail" -ne 0 ]]; then
  say "verify: FAILED"
  exit 1
fi
say "verify: OK"
exit 0
