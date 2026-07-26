"""Cheap web research: compress + browser escalate only when thin."""

from __future__ import annotations

import asyncio

from app.fusion.web_tools import compress_for_critics, format_refs_for_prompt, research_pack_for_critics


def test_compress_keeps_craft_signals_and_caps():
    blob = (
        "Cookie policy accept all tracking partners forever. " * 20
        + "Hero section with booking CTA and sticky mobile nav for services. "
        + "Warranty trust bar and pricing from 1500. "
        + "Lorem ipsum dolor sit amet " * 40
    )
    out = compress_for_critics(blob, limit=400)
    assert len(out) <= 400
    assert "hero" in out.lower() or "cta" in out.lower() or "nav" in out.lower()


def test_format_refs_respects_budget():
    pack = {
        "refs": [
            {
                "title": "A",
                "url": "https://example.com/a",
                "snippet": "hero cta",
                "text": "Hero booking CTA sticky nav services pricing reviews FAQ " * 80,
                "fetch_backend": "jina",
            },
            {
                "title": "B",
                "url": "https://example.com/b",
                "snippet": "x",
                "text": "More services and warranty trust signals " * 80,
                "fetch_backend": "jina",
            },
        ],
        "browser_used": 0,
        "browser_available": False,
    }
    text = format_refs_for_prompt(pack, char_budget=900)
    assert len(text) <= 980
    assert "example.com/a" in text
    assert "browser daemon off" in text


def test_research_pack_escalates_browser_once(monkeypatch):
    async def fake_search(query, max_results=None):
        return {
            "ok": True,
            "degraded": False,
            "backend": "test",
            "results": [
                {"title": "Thin", "url": "https://example.com/thin", "snippet": "ok"},
                {"title": "Fat", "url": "https://example.com/fat", "snippet": "hero cta nav"},
            ],
        }

    async def fake_fetch(url, limit=2500):
        if "thin" in url:
            return {"ok": True, "degraded": False, "url": url, "text": "short", "backend": "jina"}
        fat = (
            "Hero section with clear booking CTA. Sticky mobile nav. "
            "Six services with pricing. Warranty trust bar. FAQ accordion. "
        ) * 5
        return {"ok": True, "degraded": False, "url": url, "text": fat, "backend": "jina"}

    calls = {"n": 0}

    async def fake_browser(url, max_chars=2200):
        calls["n"] += 1
        return {
            "ok": True,
            "degraded": False,
            "url": url,
            "text": "Browser hero CTA sticky nav booking form services pricing reviews",
            "backend": "browser",
        }

    monkeypatch.setattr("app.fusion.web_tools.web_search", fake_search)
    monkeypatch.setattr("app.fusion.web_tools.web_fetch", fake_fetch)
    monkeypatch.setattr("app.fusion.web_tools.browser_available", lambda: True)
    monkeypatch.setattr("app.fusion.web_tools.browser_fetch_text", fake_browser)
    monkeypatch.setattr(
        "app.fusion.web_tools._cfg",
        lambda: {
            "max_results": 3,
            "max_fetch": 3,
            "char_budget": 4200,
            "extract_chars": 850,
            "browser_max": 1,
            "browser_live": 0,
            "browser_chars": 2200,
        },
    )

    pack = asyncio.run(research_pack_for_critics("автосервис сайт"))
    assert pack["ok"] is True
    assert pack["browser_used"] == 1
    assert calls["n"] == 1
    assert any(r.get("browser_escalated") for r in pack["refs"])


def test_research_pack_standard_three_refs(monkeypatch):
    async def fake_search(query, max_results=None):
        return {
            "ok": True,
            "backend": "test",
            "results": [
                {"title": f"R{i}", "url": f"https://example.com/r{i}", "snippet": "hero cta nav"}
                for i in range(1, 5)
            ],
        }

    async def fake_fetch(url, limit=2500):
        body = (
            "Hero section with booking CTA. Sticky mobile nav. "
            "Services pricing warranty reviews FAQ. "
        ) * 4
        return {"ok": True, "url": url, "text": body, "backend": "jina"}

    monkeypatch.setattr("app.fusion.web_tools.web_search", fake_search)
    monkeypatch.setattr("app.fusion.web_tools.web_fetch", fake_fetch)
    monkeypatch.setattr("app.fusion.web_tools.browser_available", lambda: False)

    pack = asyncio.run(research_pack_for_critics("автосервис сайт"))
    assert len(pack["refs"]) == 3
    assert pack["ok"] is True


def test_research_pack_skips_browser_when_unavailable(monkeypatch):
    async def fake_search(query, max_results=None):
        return {
            "ok": True,
            "backend": "test",
            "results": [{"title": "T", "url": "https://example.com/x", "snippet": ""}],
        }

    async def fake_fetch(url, limit=2500):
        return {"ok": False, "url": url, "text": "", "backend": "httpx"}

    async def boom(*a, **k):
        raise AssertionError("browser must not be called")

    monkeypatch.setattr("app.fusion.web_tools.web_search", fake_search)
    monkeypatch.setattr("app.fusion.web_tools.web_fetch", fake_fetch)
    monkeypatch.setattr("app.fusion.web_tools.browser_available", lambda: False)
    monkeypatch.setattr("app.fusion.web_tools.browser_fetch_text", boom)

    pack = asyncio.run(research_pack_for_critics("landing page"))
    assert pack["browser_used"] == 0
    assert pack["browser_available"] is False
