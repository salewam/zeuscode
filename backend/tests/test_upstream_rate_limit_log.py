"""Upstream 429 must log UPSTREAM_RATE_LIMIT and surface status 429."""

from __future__ import annotations

import logging

import pytest

from app.upstream import UpstreamError, _is_rate_limit, _raise_upstream_http_error


def test_is_rate_limit_detects_429_and_body():
    assert _is_rate_limit(429, {"msg": "ok"}) is True
    assert _is_rate_limit(200, {"error": "Rate limit exceeded"}) is True
    assert _is_rate_limit(500, {"error": "boom"}) is False


def test_raise_upstream_rate_limit_logs_and_status(caplog):
    with caplog.at_level(logging.ERROR, logger="zeus.upstream"):
        with pytest.raises(UpstreamError) as ei:
            _raise_upstream_http_error(
                "https://a6api.com/v1/chat/completions",
                429,
                {"msg": "Too Many Requests"},
            )
    assert ei.value.status_code == 429
    assert "RATE LIMIT" in str(ei.value)
    assert any("UPSTREAM_RATE_LIMIT" in r.message for r in caplog.records)
