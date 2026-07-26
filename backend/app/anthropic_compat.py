"""Anthropic Messages API ↔ Chat Completions bridge for Claude Code."""

from __future__ import annotations

import json
import uuid
from typing import Any


def anthropic_to_openai_messages(
    messages: list[Any] | None,
    *,
    system: Any = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    sys_text = _flatten_content(system)
    if sys_text.strip():
        out.append({"role": "system", "content": sys_text.strip()})
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "user")
        if role not in ("user", "assistant", "system"):
            role = "user"
        text = _flatten_content(m.get("content"))
        out.append({"role": role, "content": text})
    if not out:
        out = [{"role": "user", "content": ""}]
    return out


def _flatten_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                if p.get("type") in ("text", "input_text", "output_text"):
                    parts.append(str(p.get("text") or ""))
                elif "text" in p:
                    parts.append(str(p.get("text") or ""))
        return "".join(parts)
    return str(content)


def chat_completion_to_anthropic(data: dict[str, Any], *, model: str) -> dict[str, Any]:
    choice = ((data.get("choices") or [{}])[0]) or {}
    msg = choice.get("message") or {}
    text = msg.get("content")
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    usage = data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    mid = str(data.get("id") or f"msg_{uuid.uuid4().hex[:24]}")
    if not mid.startswith("msg_"):
        mid = f"msg_{mid}"
    return {
        "id": mid,
        "type": "message",
        "role": "assistant",
        "model": data.get("model") or model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": prompt,
            "output_tokens": completion,
        },
    }


def anthropic_to_sse_events(msg: dict[str, Any]) -> list[str]:
    """Synthetic Anthropic SSE from a completed message (Claude Code stream)."""
    text = ""
    for part in msg.get("content") or []:
        if isinstance(part, dict) and part.get("type") == "text":
            text += str(part.get("text") or "")

    def pack(event: str, payload: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    events = [
        pack(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": msg.get("id"),
                    "type": "message",
                    "role": "assistant",
                    "model": msg.get("model"),
                    "content": [],
                    "stop_reason": None,
                    "usage": {"input_tokens": (msg.get("usage") or {}).get("input_tokens") or 0, "output_tokens": 0},
                },
            },
        ),
        pack(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
    ]
    step = 48
    for i in range(0, max(len(text), 1), step):
        chunk = text[i : i + step] if text else ""
        if not chunk and i > 0:
            break
        events.append(
            pack(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": chunk},
                },
            )
        )
        if not text:
            break
    events.append(
        pack(
            "content_block_stop",
            {"type": "content_block_stop", "index": 0},
        )
    )
    events.append(
        pack(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {
                    "output_tokens": (msg.get("usage") or {}).get("output_tokens") or 0
                },
            },
        )
    )
    events.append(pack("message_stop", {"type": "message_stop"}))
    return events
