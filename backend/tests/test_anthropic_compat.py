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
