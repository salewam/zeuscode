"""Publish regression gate helpers (FR26) — no routers import from fusion."""

from __future__ import annotations

import re
from typing import Any


class PublishRegressionError(ValueError):
    """Raised when HTML would break public /go/ continuity."""


_BADGE_RE = re.compile(r"zeus-badge|сделано на zeuscode|made with zeuscode", re.I)


def check_publish_html(html: str, *, require_badge: bool = True) -> dict[str, Any]:
    """Offline/CI check: full HTML landing still has Zeus badge after inject."""
    from app.publish import inject_zeus_badge

    raw = html or ""
    if len(raw.strip()) < 20:
        raise PublishRegressionError("html too short for publish")
    injected = inject_zeus_badge(raw)
    has_html = bool(re.search(r"<html[\s>]|<!doctype\s+html", injected, re.I))
    # Accept fragment pages that still render as documents after badge inject
    has_bodyish = bool(re.search(r"</body>|</html>|<div|<section|<main", injected, re.I))
    has_badge = bool(_BADGE_RE.search(injected))
    ok = (has_html or has_bodyish) and (has_badge if require_badge else True)
    result = {
        "ok": ok,
        "has_html_shell": has_html or has_bodyish,
        "has_zeus_badge": has_badge,
        "chars": len(injected),
    }
    if not ok:
        raise PublishRegressionError(
            f"publish regression failed: badge={has_badge} shell={has_html or has_bodyish}"
        )
    return result


def gate_publish_html(html: str, *, enabled: bool = True) -> str:
    """Return badge-injected HTML; raise if gate enabled and check fails."""
    from app.publish import inject_zeus_badge

    injected = inject_zeus_badge(html or "")
    if enabled:
        check_publish_html(injected, require_badge=True)
    return injected


def check_prompt_adapt_contract(messages: list[dict[str, Any]] | None) -> dict[str, Any]:
    """FR-32 / Story 3.5: adapt may touch system/hint only — user goals must remain."""
    user_texts = [
        str(m.get("content") or "")
        for m in (messages or [])
        if (m.get("role") or "").lower() == "user"
    ]
    sys_texts = [
        str(m.get("content") or "")
        for m in (messages or [])
        if (m.get("role") or "").lower() == "system"
    ]
    banned = ("[Zeus adapt]", "Zeus adapt")
    leaked = any(any(b in u for b in banned) for u in user_texts)
    has_hint = any(any(b in s for b in banned) for s in sys_texts)
    if leaked:
        raise PublishRegressionError("prompt adapt leaked into user messages")
    return {"ok": True, "adapt_in_system": has_hint, "user_untouched": True}


def check_release_not_anti_bias(onestack: dict[str, Any] | None) -> dict[str, Any]:
    """Story 3.3: anti_bias_fail blocks release/PR publish."""
    os_ = onestack if isinstance(onestack, dict) else {}
    if os_.get("anti_bias_fail") or os_.get("release_blocked"):
        raise PublishRegressionError("anti_bias_fail: release blocked (FR-13)")
    return {"ok": True}
