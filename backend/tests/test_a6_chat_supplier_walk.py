"""chat_a6: dead-supplier walk on primary → failover to 70% key."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app import a6_health, upstream
from app.config import get_settings


@pytest.fixture(autouse=True)
def _reset():
    a6_health.reset_for_tests()
    get_settings.cache_clear()
    yield
    a6_health.reset_for_tests()
    get_settings.cache_clear()


class _Resp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}"

    def json(self):
        return self._payload


def _ok_payload(text: str = "ok") -> dict:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }


def test_chat_a6_marks_dead_and_fails_over(monkeypatch):
    monkeypatch.setenv("A6_API_KEY", "sk-primary")
    monkeypatch.setenv("A6_API_KEY_FALLBACK", "sk-fallback")
    monkeypatch.setenv("A6_TOP_SUPPLIERS", "2")
    monkeypatch.setenv("A6_FALLBACK_TOP_SUPPLIERS", "1")
    monkeypatch.setenv("A6_GROUP_ATTEMPTS", "1")
    monkeypatch.setenv("A6_PRIMARY_COOLDOWN_S", "900")
    monkeypatch.setenv("A6_DEAD_SUPPLIER_TTL_S", "7200")
    get_settings.cache_clear()

    async def fake_groups(*, pricing_base, model, timeout=30.0):
        return ["supplier-A", "supplier-B", "supplier-C"]

    monkeypatch.setattr(a6_health, "get_enable_groups", fake_groups)

    calls: list[tuple[str, str | None]] = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            auth = (headers or {}).get("Authorization") or ""
            key = "primary" if "sk-primary" in auth else "fallback"
            group = (json or {}).get("group")
            calls.append((key, group))
            # Primary A/B always fail; fallback C works.
            if key == "fallback":
                return _Resp(200, _ok_payload("ok-fallback"))
            return _Resp(503, {"error": {"message": "down", "code": "unavailable"}})

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    data = asyncio.run(
        upstream.chat_a6(
            "claude-sonnet-4-6",
            [{"role": "user", "content": "hi"}],
            max_tokens=16,
        )
    )
    assert upstream.extract_text(data) == "ok-fallback"
    assert data["_zeus_upstream"]["a6_key"] == "fallback"
    # Primary tried two live suppliers then failover.
    assert ("primary", "supplier-A") in calls
    assert ("primary", "supplier-B") in calls
    assert any(k == "fallback" for k, _ in calls)
    assert a6_health.is_supplier_dead(
        "claude-sonnet-4-6", "supplier-A", key_lane="primary"
    )
    assert a6_health.is_supplier_dead(
        "claude-sonnet-4-6", "supplier-B", key_lane="primary"
    )
    assert a6_health.should_try_primary("claude-sonnet-4-6") is False
    # Next primary walk should skip A/B and pick C.
    nxt = a6_health.live_supplier_groups(
        ["supplier-A", "supplier-B", "supplier-C"],
        model="claude-sonnet-4-6",
        key_lane="primary",
        limit=2,
    )
    assert nxt == ["supplier-C"]


def test_chat_a6_three_suppliers_then_70pct(monkeypatch):
    """Exactly 3 live suppliers fail on 30% → model cools → 70% succeeds."""
    monkeypatch.setenv("A6_API_KEY", "sk-primary")
    monkeypatch.setenv("A6_API_KEY_FALLBACK", "sk-fallback")
    monkeypatch.setenv("A6_TOP_SUPPLIERS", "3")
    monkeypatch.setenv("A6_FALLBACK_TOP_SUPPLIERS", "2")
    monkeypatch.setenv("A6_GROUP_ATTEMPTS", "1")
    monkeypatch.setenv("A6_PRIMARY_COOLDOWN_S", "900")
    monkeypatch.setenv("A6_DEAD_SUPPLIER_TTL_S", "7200")
    get_settings.cache_clear()

    async def fake_groups(*, pricing_base, model, timeout=30.0):
        return ["s1", "s2", "s3", "s4"]

    monkeypatch.setattr(a6_health, "get_enable_groups", fake_groups)

    calls: list[tuple[str, str | None]] = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            auth = (headers or {}).get("Authorization") or ""
            key = "primary" if "sk-primary" in auth else "fallback"
            group = (json or {}).get("group")
            calls.append((key, group))
            if key == "fallback" and group == "s1":
                return _Resp(200, _ok_payload("from-70"))
            return _Resp(503, {"error": {"message": "down", "code": "unavailable"}})

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    data = asyncio.run(
        upstream.chat_a6(
            "gemini-3.1-pro-preview",
            [{"role": "user", "content": "ping"}],
            max_tokens=8,
        )
    )
    assert upstream.extract_text(data) == "from-70"
    assert data["_zeus_upstream"]["a6_key"] == "fallback"
    primary_groups = [g for k, g in calls if k == "primary"]
    assert primary_groups == ["s1", "s2", "s3"]
    for g in ("s1", "s2", "s3"):
        assert a6_health.is_supplier_dead(
            "gemini-3.1-pro-preview", g, key_lane="primary"
        )
    assert a6_health.should_try_primary("gemini-3.1-pro-preview") is False
    # Next cheap walk skips the three corpses and picks s4.
    nxt = a6_health.live_supplier_groups(
        ["s1", "s2", "s3", "s4"],
        model="gemini-3.1-pro-preview",
        key_lane="primary",
        limit=3,
    )
    assert nxt == ["s4"]


def test_chat_a6_permanent_400_does_not_mark_dead(monkeypatch):
    monkeypatch.setenv("A6_API_KEY", "sk-primary")
    monkeypatch.setenv("A6_API_KEY_FALLBACK", "sk-fallback")
    monkeypatch.setenv("A6_TOP_SUPPLIERS", "2")
    monkeypatch.setenv("A6_FALLBACK_TOP_SUPPLIERS", "1")
    monkeypatch.setenv("A6_GROUP_ATTEMPTS", "1")
    monkeypatch.setenv("A6_PRIMARY_COOLDOWN_S", "900")
    get_settings.cache_clear()

    async def fake_groups(*, pricing_base, model, timeout=30.0):
        return ["bad-group", "good-group"]

    monkeypatch.setattr(a6_health, "get_enable_groups", fake_groups)

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            group = (json or {}).get("group")
            if group == "bad-group":
                return _Resp(
                    400,
                    {
                        "error": {
                            "message": "Unknown model",
                            "code": "invalid_request_error",
                        }
                    },
                )
            return _Resp(200, _ok_payload("ok-good"))

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    data = asyncio.run(
        upstream.chat_a6(
            "claude-sonnet-4-6",
            [{"role": "user", "content": "hi"}],
            max_tokens=8,
        )
    )
    assert upstream.extract_text(data) == "ok-good"
    assert not a6_health.is_supplier_dead(
        "claude-sonnet-4-6", "bad-group", key_lane="primary"
    )
    # Still on primary — 400 on one group is not a full-lane failure.
    assert a6_health.should_try_primary("claude-sonnet-4-6") is True


def test_a6_fail_kind_classifies():
    assert upstream._a6_fail_kind(503, None) == "transient"
    assert upstream._a6_fail_kind(400, None) == "permanent"
    assert upstream._a6_fail_kind(404, None) == "permanent"
    assert (
        upstream._a6_fail_kind(502, upstream.UpstreamError("A6 empty upstream", 502))
        == "transient"
    )
