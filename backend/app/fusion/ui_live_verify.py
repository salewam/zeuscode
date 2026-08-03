"""Live UI verify via browser-daemon (TZ §3.3).

HTML answer → temp file → navigate → screenshot → vision → optional click → re-shot.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.fusion.browser_client import (
    browser_available,
    ui_verify_loop,
    web_click,
    web_navigate,
    web_screenshot,
)
from app.fusion.vision_ui import vision_check_screenshot

log = logging.getLogger("zeus.fusion.ui_live_verify")

UpstreamCall = Callable[..., Awaitable[dict[str, Any]]]

_HTML_RE = re.compile(r"(?is)(?:```(?:html)?\s*)?(<!doctype html|<html[\s>])([\s\S]*?)(?:```)?\s*$")
_HREF_RE = re.compile(r"""(?i)https?://[^\s"'<>]+""")


def ui_live_verify_enabled() -> bool:
    try:
        from app.config import get_settings

        return bool(getattr(get_settings(), "FUSION_UI_LIVE_VERIFY", True))
    except Exception:  # noqa: BLE001
        return True


def extract_html_document(answer: str) -> str | None:
    text = (answer or "").strip()
    if not text:
        return None
    m = re.search(r"```(?:html)?\s*([\s\S]*?)```", text, re.I)
    if m:
        body = m.group(1).strip()
        if "<html" in body.lower() or "<!doctype" in body.lower() or "<body" in body.lower():
            if "<html" not in body.lower():
                body = f"<!doctype html><html><head><meta charset=utf-8></head><body>{body}</body></html>"
            return body
    if "<html" in text.lower() or "<!doctype html" in text.lower():
        # trim fences
        text = re.sub(r"^```(?:html)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return text.strip()
    return None


def extract_preview_url(answer: str, zeus: dict[str, Any] | None = None) -> str | None:
    z = zeus if isinstance(zeus, dict) else {}
    for key in ("preview_url", "ui_url", "url"):
        u = str(z.get(key) or "").strip()
        if u.startswith("http"):
            return u
    for u in _HREF_RE.findall(answer or ""):
        if "localhost" in u or "127.0.0.1" in u:
            return u.rstrip(").,;\"'")
    return None


def _write_html_temp(html: str) -> Path:
    fd, path = tempfile.mkstemp(prefix="zeus_ui_", suffix=".html")
    os.close(fd)
    p = Path(path)
    p.write_text(html, encoding="utf-8")
    return p


async def run_ui_live_verify(
    *,
    answer: str,
    user_q: str = "",
    zeus: dict[str, Any] | None = None,
    vision_model: str | None = None,
    upstream_call: UpstreamCall | None = None,
    click_selector: str = "",
) -> dict[str, Any]:
    """Verify rendered UI works. Returns ui_report for GateSignals.ui_broken."""
    if not ui_live_verify_enabled():
        return {
            "ok": False,
            "degraded": True,
            "skipped": True,
            "error": "disabled",
            "ui_broken": None,
        }
    if not browser_available():
        return {
            "ok": False,
            "degraded": True,
            "skipped": True,
            "error": "browser_unavailable",
            "ui_broken": None,
            "hint": "Start browser-daemon (DJARVIS) and set WEB_BROWSER_SOCK",
        }

    url = extract_preview_url(answer, zeus)
    html_path: Path | None = None
    if not url:
        html = extract_html_document(answer)
        if not html:
            return {
                "ok": False,
                "degraded": True,
                "skipped": True,
                "error": "no_html_or_url",
                "ui_broken": None,
            }
        html_path = _write_html_temp(html)
        url = html_path.as_uri()

    try:
        nav = await web_navigate(url)
        if not nav.get("ok"):
            # Daemon/CLI down ≠ UI broken — don't poison the answer
            return {
                "ok": False,
                "degraded": True,
                "skipped": True,
                "error": nav.get("error") or "navigate_failed",
                "url": url,
                "ui_broken": None,
            }

        shot = await web_screenshot()
        vision = await vision_check_screenshot(
            image_b64=shot.get("image_b64"),
            user_goal=user_q,
            model=vision_model,
            upstream_call=upstream_call,
        )
        click_sel = click_selector or str(
            (vision.get("ui_report") or {}).get("click") or ""
        ).strip()
        after = None
        clicked = None
        if click_sel and click_sel.lower() not in ("", "null", "none", "пусто"):
            clicked = await web_click(click_sel)
            after = await web_screenshot()
            if after.get("image_b64"):
                vision_after = await vision_check_screenshot(
                    image_b64=after.get("image_b64"),
                    user_goal=f"{user_q}\nAfter click {click_sel}",
                    model=vision_model,
                    upstream_call=upstream_call,
                )
            else:
                vision_after = {"broken": None, "degraded": True}
        else:
            vision_after = None

        broken = vision.get("broken")
        if vision_after and vision_after.get("broken") is True:
            broken = True
        # If vision degraded but navigate+screenshot ok — not force broken
        ui_broken = bool(broken) if isinstance(broken, bool) else None

        return {
            "ok": bool(shot.get("ok")),
            "degraded": not bool(shot.get("ok")) or bool(vision.get("degraded")),
            "url": url,
            "ui_broken": ui_broken,
            "click": clicked,
            "vision": vision,
            "vision_after": vision_after,
            "ui_report": {
                "url": url,
                "before_ok": bool(shot.get("ok")),
                "broken": ui_broken,
                "what": (vision.get("ui_report") or {}).get("what"),
                "click": click_sel or None,
                "works": (vision.get("ui_report") or {}).get("works"),
            },
            "loop": await ui_verify_loop(url, click_selector=click_sel) if False else None,
        }
    finally:
        if html_path is not None:
            try:
                html_path.unlink(missing_ok=True)
            except OSError:
                pass
