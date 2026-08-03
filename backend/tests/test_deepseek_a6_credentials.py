"""DeepSeek catalog models are healthy when A6_API_KEY is set (no DEEPSEEK key)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_deepseek_not_unhealthy_with_a6_only(monkeypatch):
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: SimpleNamespace(A6_API_KEY="sk-a6-only", DEEPSEEK_API_KEY=""),
    )
    from app.fusion._monolith import _models_missing_credentials

    dead = _models_missing_credentials()
    assert "deepseek-v4-pro" not in dead
    assert "deepseek-v4-flash" not in dead
    assert "deepseek-chat" not in dead


def test_deepseek_unhealthy_without_a6_or_deepseek(monkeypatch):
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: SimpleNamespace(A6_API_KEY="", DEEPSEEK_API_KEY=""),
    )
    from app.fusion._monolith import _models_missing_credentials

    dead = _models_missing_credentials()
    assert "deepseek-v4-pro" in dead
    assert "deepseek-chat" in dead
