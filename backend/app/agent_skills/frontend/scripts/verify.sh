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

# Placeholder contacts
if grep -RInE '\+7[[:space:]]*\([[:space:]]*495[[:space:]]*\)[[:space:]]*000|8[[:space:]]*\([[:space:]]*495[[:space:]]*\)[[:space:]]*000|your@email\.com|example\.com' "$ROOT" \
  --include='*.html' --include='*.js' --include='*.css' 2>/dev/null | head -5; then
  err "placeholder_contact (000-телефон / example.com)"
else
  ok "no placeholder contacts"
fi

# Fake success in catch / offline lie
if grep -RInE 'catch[[:space:]]*\([^)]*\)[[:space:]]*\{[^}]{0,400}(Заявк|заявк|успешн|мы[[:space:]]+свяжемся)' "$ROOT" \
  --include='*.js' 2>/dev/null | head -5; then
  err "fake_form_success: success copy inside catch"
fi

# Local assets referenced but missing on disk
while IFS= read -r -d '' f; do
  while IFS= read -r ref; do
    [[ -z "$ref" ]] && continue
    # strip query
    ref="${ref%%\?*}"
    if [[ "$ref" == assets/* || "$ref" == ./assets/* ]]; then
      target="$ROOT/${ref#./}"
      if [[ ! -f "$target" ]]; then
        err "missing_asset: $ref not found under $ROOT"
      fi
    fi
  done < <(grep -oE "url\(['\"]?[^'\")]+|src=['\"][^'\"]+" "$f" 2>/dev/null | sed -E "s/^url\(['\"]?//;s/^src=['\"]//" || true)
done < <(find "$ROOT" \( -name '*.css' -o -name '*.html' \) -print0 2>/dev/null || true)

# Broken @import of tokens without file in parent design (best-effort)
if grep -RInE "@import[^;]*tokens\.css" "$ROOT" --include='*.css' 2>/dev/null | head -3; then
  if [[ ! -f "$ROOT/../design/tokens.css" && ! -f "$ROOT/tokens.css" ]]; then
    err "broken_css_import: @import tokens.css but file missing"
  else
    ok "tokens import resolves"
  fi
fi

# ZeusCode publish badge (required on shippable HTML)
if [[ -n "${ENTRY:-}" ]]; then
  if grep -qiE 'zeus-badge|сделано на zeuscode|made with zeuscode' "$ENTRY"; then
    ok "zeus badge present"
  else
    err "missing_zeus_badge: добавь еле прозрачный «Сделано на ZeusCode» (см. publish.md)"
  fi
fi

if [[ "$fail" -ne 0 ]]; then
  say "verify: FAILED"
  exit 1
fi
say "verify: OK"
exit 0
