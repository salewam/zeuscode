#!/usr/bin/env bash
# Frontend skill artifact smoke-check — used by humans and Evidence Gate.
# Usage: ./scripts/verify.sh /path/to/src/frontend
set -euo pipefail

ROOT="${1:-.}"
fail=0
say() { printf '%s\n' "$*"; }
err() { say "FAIL: $*"; fail=1; }
ok() { say "OK: $*"; }

if [[ -f "$ROOT/index.html" ]]; then
  ENTRY="$ROOT/index.html"
elif [[ -f "$ROOT/src/frontend/index.html" ]]; then
  ROOT="$ROOT/src/frontend"
  ENTRY="$ROOT/index.html"
elif [[ -f "$ROOT/page.html" || -f "$ROOT/form.html" ]]; then
  ENTRY="$(ls "$ROOT"/page.html "$ROOT"/form.html 2>/dev/null | head -1)"
  ok "template entry $ENTRY"
else
  err "нет index.html в $ROOT"
  ENTRY=""
fi
[[ -n "${ENTRY:-}" && -f "$ENTRY" ]] && ok "entry $ENTRY"

if [[ -n "${ENTRY:-}" ]]; then
  if grep -RInE '<div[^>]*(onclick|onClick)=' "$ROOT" --include='*.html' --include='*.jsx' --include='*.tsx' 2>/dev/null | head -5; then
    err "div onclick — используй button/a"
  else
    ok "no div onclick"
  fi
fi

# outline without focus-visible across all css
css_has_outline=0
css_has_focus=0
while IFS= read -r -d '' css; do
  grep -Eq 'outline:\s*(none|0)' "$css" && css_has_outline=1
  grep -Eq 'focus-visible' "$css" && css_has_focus=1
done < <(find "$ROOT" -name '*.css' -print0 2>/dev/null || true)
if [[ "$css_has_outline" -eq 1 && "$css_has_focus" -eq 0 ]]; then
  err "outline:none/0 без focus-visible в CSS-наборе"
fi

# AI aesthetic — real usage (hex / Inter / css color values), not comments
if grep -RInE '#7[cC]3[aA][eE][dD]|#8[bB]5[cC][fF]6|#6366[fF]1|#4[fF]46[eE]5|font-family:[^;]*Inter|:\s*(purple|violet|indigo)\b' "$ROOT" \
  --include='*.css' --include='*.html' 2>/dev/null | head -8; then
  err "AI-aesthetic (purple/indigo/Inter/AI-hex)"
fi

if grep -RInE 'sk-[a-zA-Z0-9]{20,}|api[_-]?key\s*[:=]\s*["\x27][a-zA-Z0-9]{16,}' "$ROOT" 2>/dev/null | head -5; then
  err "похоже на секреты"
else
  ok "no obvious secrets"
fi

if [[ -n "${ENTRY:-}" ]] && grep -Eq '<input' "$ENTRY"; then
  if ! grep -Eq '<label' "$ENTRY"; then
    err "есть input, нет label в $ENTRY"
  else
    ok "labels present"
  fi
fi

if [[ "$fail" -ne 0 ]]; then
  say "verify: FAILED"
  exit 1
fi
say "verify: OK"
exit 0
