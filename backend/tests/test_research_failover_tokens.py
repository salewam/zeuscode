"""Research model failover must accumulate burned tokens for billing."""

from __future__ import annotations

import asyncio

from app.fusion import research_crew


def test_failover_accumulates_tokens_on_total_fail():
    calls: list[str] = []

    async def upstream_call(*, model, messages, stream=False, max_tokens=None, **kw):
        calls.append(model)
        if model == "m1":
            return {
                "choices": [{"message": {"content": ""}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        return {
            "choices": [{"message": {"content": ""}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 7},
        }

    text, pt, ct, err, used = asyncio.run(
        research_crew._call_model_with_failover(
            models=["m1", "m2"],
            system="s",
            user="u",
            upstream_call=upstream_call,
            max_tokens=64,
        )
    )
    assert text == ""
    assert err in ("empty_content", "empty_content_after_reasoning")
    assert pt == 30
    assert ct == 12
    assert used == "m2"
    assert calls == ["m1", "m2"]


def test_failover_accumulates_tokens_on_success():
    async def upstream_call(*, model, messages, stream=False, max_tokens=None, **kw):
        if model == "m1":
            return {
                "choices": [{"message": {"content": ""}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 3},
            }
        return {
            "choices": [{"message": {"content": "answer ok"}}],
            "usage": {"prompt_tokens": 22, "completion_tokens": 9},
        }

    text, pt, ct, err, used = asyncio.run(
        research_crew._call_model_with_failover(
            models=["m1", "m2"],
            system="s",
            user="u",
            upstream_call=upstream_call,
            max_tokens=64,
        )
    )
    assert text == "answer ok"
    assert err is None
    assert used == "m2"
    assert pt == 33
    assert ct == 12
