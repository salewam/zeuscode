"""OpenAI Responses API ↔ Chat Completions bridge for Codex CLI / OmniRoute.

Codex (wire_api=responses) requires the full SSE lifecycle — not just text deltas.
Missing output_item.added / content_part.added → "OutputTextDelta without active item".
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any


def responses_input_to_messages(
    inp: Any,
    *,
    instructions: str | None = None,
) -> list[dict[str, Any]]:
    """Convert Responses `input` (+ optional instructions) to chat messages."""
    messages: list[dict[str, Any]] = []
    if instructions and str(instructions).strip():
        messages.append({"role": "system", "content": str(instructions).strip()})

    if inp is None:
        messages.append({"role": "user", "content": ""})
        return messages

    if isinstance(inp, str):
        messages.append({"role": "user", "content": inp})
        return messages

    if not isinstance(inp, list):
        messages.append({"role": "user", "content": str(inp)})
        return messages

    for item in inp:
        if isinstance(item, str):
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            continue
        # EasyInputMessage / message items
        itype = item.get("type")
        role = str(item.get("role") or "user")
        if role == "developer":
            role = "system"
        # Skip non-message tool results for now (flatten text only)
        if itype in ("function_call", "function_call_output", "reasoning"):
            continue
        content = item.get("content")
        text = _flatten_content(content)
        if text or role in ("user", "assistant", "system"):
            messages.append({"role": role, "content": text})
    if not messages or all(not (m.get("content") or "").strip() for m in messages):
        messages = [{"role": "user", "content": ""}]
    return messages


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
                t = p.get("type")
                if t in ("input_text", "output_text", "text"):
                    parts.append(str(p.get("text") or ""))
                elif "text" in p:
                    parts.append(str(p.get("text") or ""))
        return "".join(parts)
    return str(content)


def chat_completion_to_response(data: dict[str, Any], *, model: str) -> dict[str, Any]:
    """Wrap a chat.completion JSON as a Responses API object."""
    choice = ((data.get("choices") or [{}])[0]) or {}
    msg = choice.get("message") or {}
    text = msg.get("content")
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    usage = data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    rid = str(data.get("id") or f"resp_{uuid.uuid4().hex[:24]}")
    if not rid.startswith("resp_"):
        rid = f"resp_{rid}"
    item_id = f"msg_{uuid.uuid4().hex[:16]}"
    return {
        "id": rid,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": data.get("model") or model,
        "output": [
            {
                "type": "message",
                "id": item_id,
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                        "annotations": [],
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": prompt,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": completion,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": prompt + completion,
        },
    }


def response_to_sse_events(resp: dict[str, Any]) -> list[str]:
    """
    Synthetic Responses SSE for Codex.

    Required order (Codex drops deltas otherwise):
      created → output_item.added → content_part.added →
      output_text.delta* → output_text.done → content_part.done →
      output_item.done → completed
    """
    text = ""
    item_id = f"msg_{uuid.uuid4().hex[:16]}"
    for item in resp.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        item_id = str(item.get("id") or item_id)
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text":
                text += str(part.get("text") or "")

    # Keep completed payload in sync with streamed item id
    if isinstance(resp.get("output"), list) and resp["output"]:
        first = resp["output"][0]
        if isinstance(first, dict):
            first["id"] = item_id

    rid = resp.get("id") or f"resp_{uuid.uuid4().hex[:16]}"
    model = resp.get("model")
    output_index = 0
    content_index = 0

    def pack(event: str, payload: dict[str, Any]) -> str:
        # Codex accepts either `event:` line or type inside data; send both.
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    events: list[str] = []

    stub = {
        "id": rid,
        "object": "response",
        "created_at": resp.get("created_at") or int(time.time()),
        "status": "in_progress",
        "model": model,
        "output": [],
    }
    events.append(
        pack("response.created", {"type": "response.created", "response": stub})
    )
    events.append(
        pack(
            "response.in_progress",
            {"type": "response.in_progress", "response": stub},
        )
    )

    message_item = {
        "type": "message",
        "id": item_id,
        "status": "in_progress",
        "role": "assistant",
        "content": [],
    }
    events.append(
        pack(
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "output_index": output_index,
                "item": message_item,
            },
        )
    )

    part = {"type": "output_text", "text": "", "annotations": []}
    events.append(
        pack(
            "response.content_part.added",
            {
                "type": "response.content_part.added",
                "item_id": item_id,
                "output_index": output_index,
                "content_index": content_index,
                "part": part,
            },
        )
    )

    step = 48
    if not text:
        # Still emit one empty-safe path: done events with empty text
        pass
    else:
        for i in range(0, len(text), step):
            chunk = text[i : i + step]
            events.append(
                pack(
                    "response.output_text.delta",
                    {
                        "type": "response.output_text.delta",
                        "item_id": item_id,
                        "output_index": output_index,
                        "content_index": content_index,
                        "delta": chunk,
                    },
                )
            )

    events.append(
        pack(
            "response.output_text.done",
            {
                "type": "response.output_text.done",
                "item_id": item_id,
                "output_index": output_index,
                "content_index": content_index,
                "text": text,
            },
        )
    )
    events.append(
        pack(
            "response.content_part.done",
            {
                "type": "response.content_part.done",
                "item_id": item_id,
                "output_index": output_index,
                "content_index": content_index,
                "part": {"type": "output_text", "text": text, "annotations": []},
            },
        )
    )

    done_item = {
        "type": "message",
        "id": item_id,
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }
    events.append(
        pack(
            "response.output_item.done",
            {
                "type": "response.output_item.done",
                "output_index": output_index,
                "item": done_item,
            },
        )
    )

    # Final completed must carry full output (Codex may rebuild from this)
    completed = dict(resp)
    completed["id"] = rid
    completed["status"] = "completed"
    completed["output"] = [done_item]
    events.append(
        pack(
            "response.completed",
            {"type": "response.completed", "response": completed},
        )
    )
    return events
