#!/usr/bin/env bash
# Design skill artifact smoke-check.
# Usage: ./scripts/verify.sh /path/to/src/design

set -euo pipefail

ROOT="${1:-.}"
fail=0

say() { printf '%s\n' "$*"; }
err() { say "FAIL: $*"; fail=1; }
ok() { say "OK: $*"; }

if [[ -d "$ROOT/src/design" ]]; then
  ROOT="$ROOT/src/design"
fi

if [[ ! -d "$ROOT" ]]; then
  err "нет директории $ROOT"
  say "verify: FAILED"
  exit 1
fi

if ! find "$ROOT" -type f \( -name '*.css' -o -name '*.md' \) 2>/dev/null | grep -q .; then
  err "нет .css/.md артефактов в $ROOT"
else
  ok "design artifacts present"
fi

if grep -RInE --include='*.css' --include='*.md' '#7c3aed|#4f46e5|#6366f1|\bInter\b' "$ROOT" \
  2>/dev/null | head -8; then
  err "AI aesthetic tokens detected"
else
  ok "no banned AI tokens"
fi

if ! grep -RInE --include='*.css' --include='*.md' -- \
  '--color-|--space-|--radius-|--focus|--ink|--accent|--muted|--surface|--font' "$ROOT" \
  >/dev/null 2>&1; then
  err "нет CSS tokens"
else
  ok "tokens present"
fi

if [[ "$fail" -ne 0 ]]; then
  say "verify: FAILED"
  exit 1
fi

say "verify: OK"
exit 0
