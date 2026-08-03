from app.anthropic_compat import (
    anthropic_to_openai_messages,
    anthropic_to_sse_events,
    chat_completion_to_anthropic,
)


def test_system_and_user():
    msgs = anthropic_to_openai_messages(
        [{"role": "user", "content": "hi"}],
        system="be brief",
    )
    assert msgs[0] == {"role": "system", "content": "be brief"}
    assert msgs[1] == {"role": "user", "content": "hi"}


def test_content_blocks():
    msgs = anthropic_to_openai_messages(
        [
            {
                "role": "user",
                "content": [{"type": "text", "text": "ping"}],
            }
        ]
    )
    assert msgs[0]["content"] == "ping"


def test_chat_to_anthropic_sse():
    chat = {
        "id": "chatcmpl-1",
        "model": "claude-sonnet-4-6",
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    msg = chat_completion_to_anthropic(chat, model="claude-sonnet-4-6")
    assert msg["type"] == "message"
    assert msg["content"][0]["text"] == "ok"
    events = anthropic_to_sse_events(msg)
    assert any("message_start" in e for e in events)
    assert any("message_stop" in e for e in events)


def test_anthropic_tools_and_tool_use_roundtrip():
    from app.anthropic_compat import anthropic_tools_to_openai

    oai = anthropic_tools_to_openai(
        [
            {
                "name": "Write",
                "description": "Write file",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ]
    )
    assert oai[0]["function"]["name"] == "Write"

    msgs = anthropic_to_openai_messages(
        [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Write",
                        "input": {"path": "notes/x.txt"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "content": "ok",
                    }
                ],
            },
        ]
    )
    assert msgs[0]["tool_calls"][0]["function"]["name"] == "Write"
    assert msgs[1]["role"] == "tool"

    anth = chat_completion_to_anthropic(
        {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "toolu_9",
                                "type": "function",
                                "function": {
                                    "name": "Write",
                                    "arguments": '{"path":"a.txt"}',
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
        model="gemini-3.1-pro",
    )
    assert anth["stop_reason"] == "tool_use"
    assert anth["content"][0]["type"] == "tool_use"

    events = anthropic_to_sse_events(anth)
    joined = "\n".join(events)
    assert "input_json_delta" in joined
    assert "tool_use" in joined
    assert '"stop_reason": "tool_use"' in joined or '"stop_reason":"tool_use"' in joined.replace(" ", "")
