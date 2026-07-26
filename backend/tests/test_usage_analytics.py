"""Product usage analytics — JSONL + preview helpers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


def test_prompt_preview_takes_last_user():
    from app.usage_analytics import prompt_preview_from_messages

    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "  hello   world  " + ("x" * 400)},
    ]
    prev = prompt_preview_from_messages(msgs, limit=20)
    assert prev.startswith("hello world")
    assert len(prev) <= 20


def test_log_product_event_writes_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app import usage_analytics as ua

    monkeypatch.setattr(ua, "usage_dir", lambda: tmp_path)
    monkeypatch.setattr(ua, "analytics_enabled", lambda: True)

    asyncio.run(
        ua.log_product_event(
            None,
            event="chat_done",
            user_id=7,
            key_prefix="zeus_ab",
            model="zeus/fusion",
            stream=True,
            prompt_preview="hi",
            path="FAST",
            leader="gemini-3.1-pro",
            status_code=200,
            latency_ms=123,
            meta={"mode": "fusion"},
        )
    )
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    row = json.loads(files[0].read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["event"] == "chat_done"
    assert row["user_id"] == 7
    assert row["path"] == "FAST"
    assert row["leader"] == "gemini-3.1-pro"
    assert row["meta"]["mode"] == "fusion"


def test_extract_result_fields_from_onestack():
    from app.usage_analytics import extract_result_fields

    data = {
        "onestack": {
            "path": "CASCADE",
            "leader": "gemini-3.1-pro",
            "routed_by": "policy",
            "trace_id": "abc",
            "policy_path": "CASCADE",
        },
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        "onestack_billing": {"charged_rub": 1.5},
    }
    f = extract_result_fields(data)
    assert f["path"] == "CASCADE"
    assert f["leader"] == "gemini-3.1-pro"
    assert f["prompt_tokens"] == 10
    assert f["cost_rub"] == 1.5
