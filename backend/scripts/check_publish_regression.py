#!/usr/bin/env python3
"""Publish regression gate checklist (FR26).

Fail CI/release when Judge/prompts/Brief/sanitize/publish changes would drop
Zeus badge or break HTML /go/ continuity.

Usage:
  python -m backend.scripts.check_publish_regression
  # or from backend/:
  python scripts/check_publish_regression.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

SAMPLE = """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>Zeus publish gate</title></head>
<body>
  <main><h1>Gate sample</h1><p>Landing continuity check.</p></main>
</body>
</html>
"""


def main() -> int:
    from app.fusion.publish_gate import PublishRegressionError, check_publish_html
    from app.publish import inject_zeus_badge

    try:
        injected = inject_zeus_badge(SAMPLE)
        result = check_publish_html(injected, require_badge=True)
    except PublishRegressionError as exc:
        print(f"FAIL: {exc}")
        return 1
    print("PASS: publish regression gate")
    print(result)
    # Touch path for ops checklist
    checklist = ROOT / "_bmad-output/implementation-artifacts/ops/publish-regression-checklist.md"
    if checklist.exists():
        print(f"checklist: {checklist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
