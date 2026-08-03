"""Per-model A6 cheap/fallback + dead-supplier memory + live walks."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from app import a6_health


@pytest.fixture(autouse=True)
def _reset_a6_health():
    a6_health.reset_for_tests()
    yield
    a6_health.reset_for_tests()


def test_per_model_cooldown_does_not_block_other_models():
    a6_health.mark_model_down("claude-opus-4-6", 900, reason="test")
    assert a6_health.should_try_primary("claude-opus-4-6") is False
    assert a6_health.should_try_primary("claude-haiku-4-5") is True
    assert a6_health.should_try_primary("gpt-5.4") is True


def test_cooldown_expires():
    a6_health.mark_model_down("gpt-5.4", 1.0, reason="short")
    assert a6_health.should_try_primary("gpt-5.4") is False
    time.sleep(1.1)
    assert a6_health.should_try_primary("gpt-5.4") is True


def test_mark_model_up_clears():
    a6_health.mark_model_down("gemini-3.1-pro", 900, reason="x")
    a6_health.mark_model_up("gemini-3.1-pro", reason="ok")
    assert a6_health.should_try_primary("gemini-3.1-pro") is True


def test_top_supplier_groups_only_first_n():
    top = a6_health.top_supplier_groups(
        ["supplier-A", "supplier-B", "supplier-C", "supplier-D", "default"],
        limit=3,
    )
    assert top == ["supplier-A", "supplier-B", "supplier-C"]
    assert a6_health.groups_for_primary_walk(
        ["supplier-A", "supplier-B", "supplier-A"], limit=2
    ) == ["supplier-A", "supplier-B"]


def test_dead_supplier_skipped_picks_new_ones():
    priced = ["supplier-A", "supplier-B", "supplier-C", "supplier-D", "supplier-E"]
    a6_health.mark_supplier_dead(
        "claude-opus-4-6", "supplier-A", key_lane="primary", ttl_s=7200, reason="t"
    )
    a6_health.mark_supplier_dead(
        "claude-opus-4-6", "supplier-B", key_lane="primary", ttl_s=7200, reason="t"
    )
    live = a6_health.live_supplier_groups(
        priced, model="claude-opus-4-6", key_lane="primary", limit=3
    )
    assert live == ["supplier-C", "supplier-D", "supplier-E"]
    # Fallback lane is independent — A/B still live there.
    live_fb = a6_health.live_supplier_groups(
        priced, model="claude-opus-4-6", key_lane="fallback", limit=3
    )
    assert live_fb == ["supplier-A", "supplier-B", "supplier-C"]


def test_dead_supplier_lanes_independent():
    a6_health.mark_supplier_dead(
        "gpt-5.4", "supplier-X", key_lane="primary", ttl_s=7200
    )
    a6_health.mark_supplier_dead(
        "gpt-5.4", "supplier-Y", key_lane="fallback", ttl_s=7200
    )
    assert a6_health.is_supplier_dead("gpt-5.4", "supplier-X", key_lane="primary")
    assert not a6_health.is_supplier_dead("gpt-5.4", "supplier-X", key_lane="fallback")
    assert a6_health.is_supplier_dead("gpt-5.4", "supplier-Y", key_lane="fallback")
    assert not a6_health.is_supplier_dead("gpt-5.4", "supplier-Y", key_lane="primary")


def test_preferred_sticky_after_live():
    priced = ["supplier-A", "supplier-B", "supplier-C"]
    a6_health.mark_supplier_live("grok-4.3", "supplier-B", key_lane="primary")
    live = a6_health.live_supplier_groups(
        priced, model="grok-4.3", key_lane="primary", limit=2
    )
    assert live[0] == "supplier-B"
    assert "supplier-A" in live


def test_preferred_cleared_when_marked_dead():
    a6_health.mark_supplier_live("grok-4.3", "supplier-B", key_lane="primary")
    a6_health.mark_supplier_dead(
        "grok-4.3", "supplier-B", key_lane="primary", ttl_s=7200
    )
    assert a6_health.preferred_primary_supplier("grok-4.3") is None


def test_snapshot_includes_dead_suppliers():
    a6_health.mark_supplier_dead(
        "deepseek-v4-pro", "supplier-Z", key_lane="fallback", ttl_s=7200
    )
    snap = a6_health.snapshot()
    assert any(
        d["model"] == "deepseek-v4-pro"
        and d["key"] == "fallback"
        and d["group"] == "supplier-Z"
        for d in snap["dead_suppliers"]
    )


def test_get_enable_groups_from_pricing(monkeypatch):
    class _Resp:
        status_code = 200
        content = b"{}"

        def json(self):
            return {
                "data": [
                    {
                        "model_name": "claude-opus-4-6",
                        "enable_groups": ["supplier-X", "supplier-Y"],
                    },
                    {
                        "model_name": "claude-haiku-4-5",
                        "enable_groups": ["supplier-H"],
                    },
                ]
            }

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            assert url.endswith("/api/pricing")
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    groups = asyncio.run(
        a6_health.get_enable_groups(
            pricing_base="https://a6api.com/v1", model="claude-opus-4-6"
        )
    )
    assert groups == ["supplier-X", "supplier-Y"]
    groups2 = asyncio.run(
        a6_health.get_enable_groups(
            pricing_base="https://a6api.com/v1", model="claude-haiku-4-5"
        )
    )
    assert groups2 == ["supplier-H"]


def test_decide_try_primary_no_haiku_probe():
    """Recovery is time-based per model — no side-effect ping."""
    a6_health.mark_model_down("claude-opus-4-6", 900, reason="x")
    ok = asyncio.run(
        a6_health.decide_try_primary(
            base="https://a6api.com/v1",
            key="sk-x",
            probe_model="claude-haiku-4-5",
            cooldown_s=900,
            model="claude-opus-4-6",
        )
    )
    assert ok is False
    ok2 = asyncio.run(
        a6_health.decide_try_primary(
            base="https://a6api.com/v1",
            key="sk-x",
            probe_model="claude-haiku-4-5",
            cooldown_s=900,
            model="gpt-5.4",
        )
    )
    assert ok2 is True
