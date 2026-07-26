"""Kie Claude Messages hybrid payload (thinkingFlag / stream / token clamp)."""

from __future__ import annotations

from app.catalog import canonical_model_id, get_model
from app.upstream import build_claude_payload, _claude_messages, _claude_token_ceiling


def test_build_claude_payload_matches_kie_working_format():
    payload = build_claude_payload(
        "claude-fable-5",
        [{"role": "user", "content": "Сделай HTML сайт МоторХаус"}],
        max_tokens=4096,
    )
    assert payload["model"] == "claude-fable-5"
    assert payload["stream"] is False
    assert payload["thinkingFlag"] is True
    assert payload["max_tokens"] == 4096
    assert payload["messages"] == [
        {"role": "user", "content": "Сделай HTML сайт МоторХаус"}
    ]
    assert "system" not in payload


def test_build_claude_payload_normalizes_client_casing():
    payload = build_claude_payload(
        "Claude-fable-5",
        [{"role": "user", "content": "ping"}],
        max_tokens=4096,
    )
    assert payload["model"] == "claude-fable-5"
    assert get_model("Claude-fable-5")["id"] == "claude-fable-5"
    assert canonical_model_id("Claude-fable-5") == "claude-fable-5"


def test_build_claude_payload_keeps_system_and_plain_content():
    payload = build_claude_payload(
        "claude-opus-4-8",
        [
            {"role": "system", "content": "You are the ZeusCode Author"},
            {"role": "user", "content": [{"type": "text", "text": "revise HTML"}]},
        ],
        max_tokens=8000,
    )
    assert payload["system"] == "You are the ZeusCode Author"
    assert payload["messages"][0]["content"] == "revise HTML"
    assert payload["thinkingFlag"] is True
    assert payload["stream"] is False


def test_claude_messages_merges_roles_and_skips_empty_assistant():
    system, msgs = _claude_messages(
        [
            {"role": "assistant", "content": ""},
            {"role": "assistant", "content": "partial"},
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
        ]
    )
    assert system is None
    assert msgs[0]["role"] == "user"  # never start with assistant
    assert any(m["role"] == "assistant" and m["content"] == "partial" for m in msgs)
    # consecutive users merged
    assert any(m["role"] == "user" and "a" in m["content"] and "b" in m["content"] for m in msgs)


def test_claude_token_ceiling_clamps_fusion_65536():
    assert _claude_token_ceiling(65536) == 7680
    assert _claude_token_ceiling(4096) == 4096
    assert _claude_token_ceiling(None) == 7680
    assert _claude_token_ceiling(8192) == 7680
