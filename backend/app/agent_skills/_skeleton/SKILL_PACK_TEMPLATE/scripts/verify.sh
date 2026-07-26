#!/usr/bin/env bash
# Minimal verify skeleton — replace checks on first real product.
set -euo pipefail
ROOT="${1:-.}"
echo "verify: ROOT=$ROOT"
# TODO: check required files exist
# TODO: smoke (python -m py_compile / playwright / file magic)
echo "verify: OK (skeleton — tighten on tests)"
exit 0
