"""FAST path: retry/failover instead of instant 502 on flaky cheap model."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.fusion import _monolith as mono


def test_race_first_single_model_failover(monkeypatch):
    calls: list[str] = []

    async def fake_panel_one(model: str, messages):
        calls.append(model)
        if model == "deepseek-v4-flash":
            return {
                "model": model,
                "ok": False,
                "text": "",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "latency_s": 0.1,
                "error": "timeout>45s",
            }
        return {
            "model": model,
            "ok": True,
            "text": "ok from failover",
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "latency_s": 0.2,
            "error": None,
        }

    monkeypatch.setattr(mono, "_panel_one", fake_panel_one)
    winner, partial = asyncio.run(
        mono._race_first(
            ["deepseek-v4-flash"],
            [{"role": "user", "content": "hi"}],
            timeout_s=2.0,
        )
    )
    assert winner["text"] == "ok from failover"
    assert "deepseek-v4-flash" in calls
    assert any(m != "deepseek-v4-flash" for m in calls)
    assert partial


def test_race_first_all_fail_still_502(monkeypatch):
    async def fake_panel_one(model: str, messages):
        return {
            "model": model,
            "ok": False,
            "text": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_s": 0.01,
            "error": "dead",
        }

    monkeypatch.setattr(mono, "_panel_one", fake_panel_one)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            mono._race_first(
                ["deepseek-v4-flash"],
                [{"role": "user", "content": "hi"}],
                timeout_s=1.0,
            )
        )
    assert ei.value.status_code == 502
