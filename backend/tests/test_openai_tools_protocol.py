"""OpenCode/Cline tools protocol — Zeus must not strip tool_calls."""

from __future__ import annotations

from app.openai_tools import (
    claude_messages_with_tools,
    normalize_openai_tools,
    normalize_tool_calls,
    openai_from_claude_content,
    openai_tools_to_claude,
    prepare_agent_messages,
    request_wants_tools,
)
from app.routers.chat import _sse_from_completion
from app.upstream import build_claude_payload, build_gemini_payload


SAMPLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    }
]


def test_request_wants_tools():
    assert request_wants_tools(SAMPLE_TOOLS) is True
    assert request_wants_tools([]) is False
    assert request_wants_tools(None) is False


def test_prepare_agent_messages_keeps_tool_rounds():
    msgs = prepare_agent_messages(
        [
            {"role": "user", "content": "list files"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "bash", "arguments": '{"command":"ls"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "a.txt\nb.txt"},
        ]
    )
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "bash"
    assert msgs[2]["role"] == "tool"
    assert msgs[2]["tool_call_id"] == "call_1"


def test_gemini_payload_includes_tools():
    payload = build_gemini_payload(
        [{"role": "user", "content": "run ls"}],
        tools=SAMPLE_TOOLS,
        tool_choice="auto",
    )
    assert payload["stream"] is False
    assert payload["tools"] == SAMPLE_TOOLS
    assert payload["tool_choice"] == "auto"
    assert payload["messages"][0]["content"][0]["type"] == "text"


def test_normalize_repairs_null_type_and_flat_tools():
    broken = [
        {"type": None, "function": {"name": "bash", "description": "x", "parameters": {"type": "object"}}},
        {"type": "function", "function": None},
        {"name": "read_file", "description": "read", "parameters": {"type": "object", "properties": {}}},
        None,
        {"type": "function", "function": {"name": "", "parameters": {}}},
    ]
    out = normalize_openai_tools(broken)
    names = [t["function"]["name"] for t in out]
    assert names == ["bash", "read_file"]
    assert all(t["type"] == "function" and isinstance(t["function"], dict) for t in out)


def test_gemini_payload_drops_null_tools_not_502_shape():
    payload = build_gemini_payload(
        [{"role": "user", "content": "OK"}],
        tools=[
            {"type": None, "function": None},
            {"type": "function", "function": {"name": "noop", "parameters": {"type": "object"}}},
        ],
        tool_choice={"type": "function", "function": {"name": "noop"}},
    )
    assert payload["tools"][0]["type"] == "function"
    assert payload["tools"][0]["function"]["name"] == "noop"
    assert payload["tool_choice"]["function"]["name"] == "noop"


def test_normalize_tool_calls_repairs_null_type():
    cleaned = normalize_tool_calls(
        [
            {"id": "c1", "type": None, "function": {"name": "bash", "arguments": {"command": "ls"}}},
            {"name": "read", "arguments": "{}"},
            {"type": "function", "function": None},
        ]
    )
    assert cleaned[0]["type"] == "function"
    assert cleaned[0]["function"]["name"] == "bash"
    assert isinstance(cleaned[0]["function"]["arguments"], str)
    assert cleaned[1]["function"]["name"] == "read"
    assert len(cleaned) == 2


def test_claude_payload_converts_openai_tools():
    payload = build_claude_payload(
        "claude-opus-4-8",
        [{"role": "user", "content": "run ls"}],
        max_tokens=4096,
        tools=SAMPLE_TOOLS,
    )
    assert payload["thinkingFlag"] is True
    assert payload["stream"] is False
    assert payload["tools"][0]["name"] == "bash"
    assert "input_schema" in payload["tools"][0]


def test_claude_tool_roundtrip_to_openai():
    system, msgs = claude_messages_with_tools(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "toolu_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command":"pwd"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "toolu_1", "content": "/tmp"},
        ]
    )
    assert msgs[0]["role"] == "assistant"
    assert msgs[0]["content"][0]["type"] == "tool_use"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"][0]["type"] == "tool_result"

    converted = openai_from_claude_content(
        {
            "id": "msg_1",
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_9",
                    "name": "bash",
                    "input": {"command": "ls"},
                }
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
        "claude-opus-4-8",
    )
    msg = converted["choices"][0]["message"]
    assert converted["choices"][0]["finish_reason"] == "tool_calls"
    assert msg["tool_calls"][0]["function"]["name"] == "bash"


def test_sse_emits_tool_calls():
    data = {
        "id": "chatcmpl-x",
        "model": "gemini-3.1-pro",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": '{"command":"ls"}',
                            },
                        }
                    ],
                },
            }
        ],
    }
    blob = "".join(_sse_from_completion(data))
    assert "tool_calls" in blob
    assert "bash" in blob
    assert '"finish_reason": "tool_calls"' in blob or "tool_calls" in blob


def test_openai_tools_to_claude_shape():
    out = openai_tools_to_claude(SAMPLE_TOOLS)
    assert out == [
        {
            "name": "bash",
            "description": "Run a shell command",
            "input_schema": SAMPLE_TOOLS[0]["function"]["parameters"],
        }
    ]
