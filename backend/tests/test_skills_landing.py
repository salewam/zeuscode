"""Skills pack wires landing-ship into prompts."""

from app.skills import build_role_system, get_depth, load_skill_pack


def test_light_frontend_gets_landing_ship_ref():
    load_skill_pack.cache_clear()
    sys = build_role_system("frontend", brief=None, intent="ui", mode="light")
    assert "landing-ship" in sys.lower() or "Shippable landing" in sys or "000-00-00" in sys
    assert "fake_form_success" in sys or "catch" in sys.lower() or "offline" in sys.lower()


def test_standard_backend_gets_landing_api():
    load_skill_pack.cache_clear()
    sys = build_role_system("backend", brief=None, intent="feature", mode="standard")
    assert "booking" in sys.lower() or "landing-api" in sys.lower() or "/api/" in sys


def test_light_depth_has_refs():
    d = get_depth("light")
    assert "landing-ship.md" in (d.get("refs") or ())
    assert d.get("include_examples") is True


def test_design_standard_mentions_media_honesty():
    load_skill_pack.cache_clear()
    sys = build_role_system("design", brief=None, intent="ui", mode="standard")
    assert "Media" in sys or "media" in sys.lower()
    assert "000" in sys or "landing-ship" in sys.lower() or "assets" in sys.lower()
