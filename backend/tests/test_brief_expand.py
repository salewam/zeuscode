"""Tests for orchestrator brief unpack."""

from app.brief_expand import (
    _fallback_autoservice,
    format_expanded_brief,
    inject_api_prelock,
    needs_expand,
)


def test_needs_expand_short_landing():
    assert needs_expand("сделай сайт автосервиса") is True
    assert needs_expand("привет") is True  # short — expand may run; ask routing separate


def test_needs_expand_skips_fat_brief():
    fat = "x" * 500
    assert needs_expand("сделай сайт", brief=fat) is False


def test_autoservice_fallback_has_booking_api():
    data = _fallback_autoservice(
        "сайт для автосервиса который занимается всеми видами работ"
    )
    assert "МоторХаус" in data["brief_md"] or data["brand"]["name"] == "МоторХаус"
    assert any(a["path"] == "/api/booking" for a in data["api"])
    assert len(data["services"]) >= 5
    assert data["questions"]
    lock = inject_api_prelock(data)
    assert lock is not None
    assert "/api/booking" in lock["paths"]
    assert "phone" in lock["fields"]


def test_format_expanded_includes_questions():
    data = _fallback_autoservice("автосервис сто")
    md = format_expanded_brief(data)
    assert "Допущения" in md or "Must-have" in md or "МоторХаус" in md
    assert "Уточнения" in md
