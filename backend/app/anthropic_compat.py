"""Anthropic Messages API ↔ Chat Completions bridge for Claude Code."""

from __future__ import annotations

import json
import uuid
from typing import Any


def anthropic_tools_to_openai(tools: list[Any] | None) -> list[dict[str, Any]]:
    """Anthropic tools[] → OpenAI chat tools (via shared normalizer)."""
    from app.openai_tools import normalize_openai_tools

    raw: list[dict[str, Any]] = []
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "").strip()
        if not name:
            continue
        raw.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(t.get("description") or name),
                    "parameters": t.get("input_schema")
                    if isinstance(t.get("input_schema"), dict)
                    else {"type": "object", "properties": {}},
                },
            }
        )
    return normalize_openai_tools(raw)


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
        content = m.get("content")
        if role == "assistant":
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype in ("text", "output_text"):
                        text_parts.append(str(block.get("text") or ""))
                    elif btype == "tool_use":
                        tool_calls.append(
                            {
                                "id": str(block.get("id") or f"toolu_{uuid.uuid4().hex[:12]}"),
                                "type": "function",
                                "function": {
                                    "name": str(block.get("name") or "tool"),
                                    "arguments": json.dumps(
                                        block.get("input")
                                        if isinstance(block.get("input"), dict)
                                        else {},
                                        ensure_ascii=False,
                                    ),
                                },
                            }
                        )
            else:
                text_parts.append(_flatten_content(content))
            item: dict[str, Any] = {"role": "assistant"}
            text = "".join(text_parts).strip()
            if tool_calls:
                item["tool_calls"] = tool_calls
                item["content"] = text or None
            else:
                item["content"] = text
            out.append(item)
            continue
        if role == "user":
            text_parts: list[str] = []
            tool_results: list[dict[str, Any]] = []
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype in ("text", "input_text"):
                        text_parts.append(str(block.get("text") or ""))
                    elif btype == "tool_result":
                        tool_results.append(block)
            else:
                text_parts.append(_flatten_content(content))
            if tool_results:
                if text_parts:
                    out.append({"role": "user", "content": "".join(text_parts).strip()})
                for tr in tool_results:
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": str(tr.get("tool_use_id") or tr.get("id") or ""),
                            "content": _flatten_tool_result(tr.get("content")),
                        }
                    )
            else:
                out.append({"role": "user", "content": "".join(text_parts).strip()})
            continue
        if role == "system":
            out.append({"role": "system", "content": _flatten_content(content)})
            continue
        out.append({"role": "user", "content": _flatten_content(content)})
    if not out:
        out = [{"role": "user", "content": ""}]
    return out


def _flatten_tool_result(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return _flatten_content(content)
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    return "" if content is None else str(content)


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
    tool_calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else []

    content: list[dict[str, Any]] = []
    if text.strip():
        content.append({"type": "text", "text": text})
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = str((fn or {}).get("name") or "").strip()
        if not name:
            continue
        raw_args = (fn or {}).get("arguments")
        if isinstance(raw_args, dict):
            inp = raw_args
        elif isinstance(raw_args, str):
            try:
                inp = json.loads(raw_args)
                if not isinstance(inp, dict):
                    inp = {"value": inp}
            except Exception:  # noqa: BLE001
                inp = {"raw": raw_args}
        else:
            inp = {}
        content.append(
            {
                "type": "tool_use",
                "id": str(tc.get("id") or f"toolu_{uuid.uuid4().hex[:12]}"),
                "name": name,
                "input": inp,
            }
        )
    if not content:
        content = [{"type": "text", "text": ""}]

    finish = choice.get("finish_reason") or "stop"
    stop_reason = "tool_use" if tool_calls else ("end_turn" if finish in ("stop", None, "") else str(finish))

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
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": prompt,
            "output_tokens": completion,
        },
    }


def anthropic_to_sse_events(msg: dict[str, Any]) -> list[str]:
    """Synthetic Anthropic SSE from a completed message (Claude Code stream)."""

    def pack(event: str, payload: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    content_blocks = [b for b in (msg.get("content") or []) if isinstance(b, dict)]
    if not content_blocks:
        content_blocks = [{"type": "text", "text": ""}]

    stop_reason = str(msg.get("stop_reason") or "end_turn")
    usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else {}

    events: list[str] = [
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
                    "usage": {
                        "input_tokens": int(usage.get("input_tokens") or 0),
                        "output_tokens": 0,
                    },
                },
            },
        ),
    ]

    text_step = 48
    json_step = 64

    for index, block in enumerate(content_blocks):
        btype = block.get("type")
        if btype == "tool_use":
            tool_id = str(block.get("id") or f"toolu_{uuid.uuid4().hex[:12]}")
            name = str(block.get("name") or "tool")
            inp = block.get("input") if isinstance(block.get("input"), dict) else {}
            events.append(
                pack(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": name,
                            "input": {},
                        },
                    },
                )
            )
            partial = json.dumps(inp, ensure_ascii=False)
            if partial:
                for i in range(0, len(partial), json_step):
                    chunk = partial[i : i + json_step]
                    events.append(
                        pack(
                            "content_block_delta",
                            {
                                "type": "content_block_delta",
                                "index": index,
                                "delta": {"type": "input_json_delta", "partial_json": chunk},
                            },
                        )
                    )
            events.append(
                pack(
                    "content_block_stop",
                    {"type": "content_block_stop", "index": index},
                )
            )
            continue

        text = str(block.get("text") or "") if btype == "text" else ""
        events.append(
            pack(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {"type": "text", "text": ""},
                },
            )
        )
        if text:
            for i in range(0, len(text), text_step):
                chunk = text[i : i + text_step]
                events.append(
                    pack(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {"type": "text_delta", "text": chunk},
                        },
                    )
                )
        else:
            events.append(
                pack(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "text_delta", "text": ""},
                    },
                )
            )
        events.append(
            pack(
                "content_block_stop",
                {"type": "content_block_stop", "index": index},
            )
        )

    events.append(
        pack(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": int(usage.get("output_tokens") or 0)},
            },
        )
    )
    events.append(pack("message_stop", {"type": "message_stop"}))
    return events
