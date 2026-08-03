"""Kie family payload contracts — Zeus standard for every user-facing model call."""

from __future__ import annotations

from app.upstream import (
    build_claude_payload,
    build_gemini_payload,
    build_openai_chat_payload,
    build_responses_payload,
)


def test_claude_payload_matches_kie_support_and_docs():
    payload = build_claude_payload(
        "claude-fable-5",
        [{"role": "user", "content": "Сделай HTML"}],
        max_tokens=4096,
    )
    assert payload == {
        "model": "claude-fable-5",
        "messages": [{"role": "user", "content": "Сделай HTML"}],
        "thinkingFlag": True,
        "stream": False,
        "max_tokens": 4096,
    }


def test_claude_never_sends_unclamped_65k():
    payload = build_claude_payload(
        "claude-opus-4-8",
        [{"role": "user", "content": "x"}],
        max_tokens=65536,
    )
    assert payload["max_tokens"] == 7680
    assert payload["stream"] is False
    assert "thinkingFlag" in payload


def test_gemini_payload_forces_non_stream_parts():
    payload = build_gemini_payload(
        [{"role": "user", "content": "hello"}],
        max_tokens=2048,
    )
    assert payload["stream"] is False
    assert payload["include_thoughts"] is False
    assert payload["reasoning_effort"] == "low"
    assert payload["messages"][0]["content"] == [{"type": "text", "text": "hello"}]
    assert payload["max_tokens"] == 2048
    assert "thinkingFlag" not in payload


def test_gemini_tool_history_never_sends_null_or_empty_content():
    """Kie gemini-3.1-pro: null/\"\" assistant content → 400 Message content is null."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "run",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        }
    ]
    payload = build_gemini_payload(
        [
            {"role": "user", "content": "write a file"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command":"mkdir -p notes"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "(no output)"},
        ],
        tools=tools,
        tool_choice="auto",
    )
    asst = next(m for m in payload["messages"] if m.get("role") == "assistant")
    assert asst.get("tool_calls")
    assert asst["content"] == [{"type": "text", "text": "."}]


def test_openai_chat_payload_no_claude_flags():
    payload = build_openai_chat_payload([{"role": "user", "content": "hi"}])
    assert payload["stream"] is False
    assert payload["reasoning_effort"] == "low"
    assert "thinkingFlag" not in payload
    assert "include_thoughts" not in payload


def test_responses_payload_uses_input_not_messages():
    payload = build_responses_payload(
        "gpt-5.6-sol",
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "build site"},
        ],
    )
    assert payload["stream"] is False
    assert payload["reasoning"] == {"effort": "low"}
    assert "messages" not in payload
    assert "thinkingFlag" not in payload
    assert payload["input"][0]["role"] == "system"
    assert payload["input"][0]["content"][0]["type"] == "input_text"
    assert payload["input"][1]["role"] == "user"
    assert payload["input"][1]["content"][0] == {
        "type": "input_text",
        "text": "build site",
    }
