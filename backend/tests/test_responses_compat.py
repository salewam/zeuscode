"""Responses API bridge for Codex / OmniRoute."""

from app.responses_compat import (
    chat_completion_to_response,
    response_to_sse_events,
    responses_input_to_messages,
)


def test_input_string():
    msgs = responses_input_to_messages("ping", instructions="be brief")
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "ping"}


def test_input_roles_and_parts():
    msgs = responses_input_to_messages(
        [
            {"role": "developer", "content": "sys"},
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "hi"}],
            },
        ]
    )
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "sys"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "hi"


def test_input_function_call_roundtrip():
    msgs = responses_input_to_messages(
        [
            {"role": "user", "content": "write"},
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "write_file",
                "arguments": '{"path":"a.txt","content":"hi"}',
            },
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": "ok",
            },
        ]
    )
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "write_file"
    assert msgs[1]["tool_calls"][0]["id"] == "call_1"
    assert msgs[2] == {"role": "tool", "tool_call_id": "call_1", "content": "ok"}


def test_chat_to_response_and_sse():
    chat = {
        "id": "chatcmpl-1",
        "model": "gemini-3.1-pro",
        "choices": [{"message": {"role": "assistant", "content": "hello world"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }
    resp = chat_completion_to_response(chat, model="gemini-3.1-pro")
    assert resp["object"] == "response"
    assert resp["status"] == "completed"
    assert resp["output"][0]["content"][0]["text"] == "hello world"
    events = response_to_sse_events(resp)
    joined = "\n".join(events)
    # Codex-required lifecycle (order matters)
    for needle in (
        "response.created",
        "response.output_item.added",
        "response.content_part.added",
        "response.output_text.delta",
        "response.output_text.done",
        "response.content_part.done",
        "response.output_item.done",
        "response.completed",
    ):
        assert needle in joined, needle
    assert "item_id" in joined
    assert "output_index" in joined
    assert "hello" in joined
    # deltas must come AFTER content_part.added
    assert joined.index("response.content_part.added") < joined.index(
        "response.output_text.delta"
    )


def test_chat_tool_calls_become_function_call_output():
    chat = {
        "id": "chatcmpl-tools",
        "model": "gemini-3.1-pro",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_abc",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": '{"path":"notes/x.txt","content":"hi"}',
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    resp = chat_completion_to_response(chat, model="gemini-3.1-pro")
    assert resp["output"][0]["type"] == "function_call"
    assert resp["output"][0]["name"] == "write_file"
    assert resp["output"][0]["call_id"] == "call_abc"
    assert "notes/x.txt" in resp["output"][0]["arguments"]
    # no empty text message when tools-only
    assert all(i.get("type") != "message" for i in resp["output"])

    joined = "\n".join(response_to_sse_events(resp))
    for needle in (
        "response.created",
        "response.output_item.added",
        "response.function_call_arguments.delta",
        "response.function_call_arguments.done",
        "response.output_item.done",
        "response.completed",
        "write_file",
        "call_abc",
    ):
        assert needle in joined, needle
    # completed must keep function_call (not overwrite with empty message)
    assert '"type": "function_call"' in joined or '"type":"function_call"' in joined
