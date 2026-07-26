"""DJARVIS browser adapter public API (socket/cli) — unit, no daemon required."""

from __future__ import annotations

import asyncio

from app.fusion import browser_client
from app.fusion.web_tools import web_search_via_google


def test_web_navigate_bad_url():
    out = asyncio.run(browser_client.web_navigate("not-a-url"))
    assert out["ok"] is False
    assert out["degraded"] is True
    assert out["error"] == "bad_url"


def test_web_navigate_unavailable(monkeypatch):
    monkeypatch.setattr(browser_client, "browser_available", lambda: False)
    out = asyncio.run(browser_client.web_navigate("https://example.com"))
    assert out["ok"] is False
    assert out["error"] == "unavailable"


def test_browser_fetch_text_chains_navigate_get_text(monkeypatch):
    async def fake_nav(url: str):
        return {"ok": True, "url": url, "final_url": url, "backend": "browser"}

    async def fake_gt(*, selector: str = "", max_chars: int = 2500):
        raw = "Hero CTA services booking " * 20
        return {
            "ok": True,
            "text": raw[:max_chars],
            "url": "https://ex.com",
            "backend": "browser",
        }

    monkeypatch.setattr(browser_client, "web_navigate", fake_nav)
    monkeypatch.setattr(browser_client, "web_get_text", fake_gt)
    out = asyncio.run(browser_client.browser_fetch_text("https://ex.com", max_chars=80))
    assert out["ok"] is True
    assert out["backend"] == "browser"
    assert "Hero" in out["text"]
    assert len(out["text"]) <= 80


def test_web_search_via_google_degrades_without_browser(monkeypatch):
    monkeypatch.setattr("app.fusion.web_tools.browser_available", lambda: False)
    out = asyncio.run(web_search_via_google("auto repair shop"))
    assert out["ok"] is False
    assert out["degraded"] is True
    assert out["backend"] == "google_browser"
