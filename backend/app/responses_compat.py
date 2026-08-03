"""OpenAI Responses API ↔ Chat Completions bridge for Codex CLI / OmniRoute.

Codex (wire_api=responses) requires the full SSE lifecycle — not just text deltas.
Missing output_item.added / content_part.added → "OutputTextDelta without active item".

Tool loop (required for Codex agent write/shell):
  chat.completion tool_calls → Responses output type=function_call
  Responses function_call / function_call_output → chat messages
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

    pending_calls: list[dict[str, Any]] = []

    def flush_calls() -> None:
        nonlocal pending_calls
        if not pending_calls:
            return
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": pending_calls,
            }
        )
        pending_calls = []

    for item in inp:
        if isinstance(item, str):
            flush_calls()
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            continue

        itype = item.get("type")
        if itype == "reasoning":
            continue

        if itype == "function_call":
            call_id = str(item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:16]}")
            name = str(item.get("name") or "").strip()
            args = item.get("arguments")
            if not isinstance(args, str):
                args = json.dumps(args or {}, ensure_ascii=False)
            if name:
                pending_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": args},
                    }
                )
            continue

        if itype == "function_call_output":
            flush_calls()
            call_id = str(item.get("call_id") or item.get("id") or "")
            out = item.get("output")
            if isinstance(out, (dict, list)):
                content = json.dumps(out, ensure_ascii=False)
            else:
                content = "" if out is None else str(out)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id or f"call_{uuid.uuid4().hex[:12]}",
                    "content": content,
                }
            )
            continue

        # EasyInputMessage / message items
        flush_calls()
        role = str(item.get("role") or "user")
        if role == "developer":
            role = "system"
        content = item.get("content")
        text = _flatten_content(content)
        if text or role in ("user", "assistant", "system"):
            messages.append({"role": role, "content": text})

    flush_calls()

    if not messages or all(
        not str(m.get("content") or "").strip()
        and not m.get("tool_calls")
        and m.get("role") != "tool"
        for m in messages
    ):
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


def _cached_prompt_tokens(usage: dict[str, Any]) -> int:
    """Cached prompt tokens as reported upstream (A6 sends prompt_tokens_details)."""
    for key in ("prompt_tokens_details", "input_tokens_details"):
        details = usage.get(key)
        if isinstance(details, dict):
            raw = details.get("cached_tokens")
            if raw is not None:
                try:
                    return max(0, int(raw))
                except (TypeError, ValueError):
                    return 0
    return 0


def chat_completion_to_response(data: dict[str, Any], *, model: str) -> dict[str, Any]:
    """Wrap a chat.completion JSON as a Responses API object (incl. tool_calls)."""
    choice = ((data.get("choices") or [{}])[0]) or {}
    msg = choice.get("message") or {}
    text = msg.get("content")
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    tool_calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else []

    usage = data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    cached = _cached_prompt_tokens(usage)
    rid = str(data.get("id") or f"resp_{uuid.uuid4().hex[:24]}")
    if not rid.startswith("resp_"):
        rid = f"resp_{rid}"

    output: list[dict[str, Any]] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = str((fn or {}).get("name") or "").strip()
        if not name:
            continue
        args = (fn or {}).get("arguments")
        if not isinstance(args, str):
            args = json.dumps(args or {}, ensure_ascii=False)
        call_id = str(tc.get("id") or f"call_{uuid.uuid4().hex[:16]}")
        output.append(
            {
                "type": "function_call",
                "id": f"fc_{uuid.uuid4().hex[:16]}",
                "call_id": call_id,
                "name": name,
                "arguments": args,
                "status": "completed",
            }
        )

    # Plain text reply (or empty message when no tools — keep prior Codex text path)
    if text.strip() or not output:
        output.append(
            {
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex[:16]}",
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
        )

    return {
        "id": rid,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": data.get("model") or model,
        "output": output,
        "usage": {
            "input_tokens": prompt,
            "input_tokens_details": {"cached_tokens": cached},
            "output_tokens": completion,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": prompt + completion,
        },
    }


def response_to_sse_events(resp: dict[str, Any]) -> list[str]:
    """
    Synthetic Responses SSE for Codex.

    Text path (required order):
      created → output_item.added → content_part.added →
      output_text.delta* → output_text.done → content_part.done →
      output_item.done → completed

    Tool path:
      created → for each function_call:
        output_item.added → function_call_arguments.delta* →
        function_call_arguments.done → output_item.done
      → completed (full output)
    """

    def pack(event: str, payload: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    rid = resp.get("id") or f"resp_{uuid.uuid4().hex[:16]}"
    model = resp.get("model")
    raw_output = [i for i in (resp.get("output") or []) if isinstance(i, dict)]

    events: list[str] = []
    stub = {
        "id": rid,
        "object": "response",
        "created_at": resp.get("created_at") or int(time.time()),
        "status": "in_progress",
        "model": model,
        "output": [],
    }
    events.append(pack("response.created", {"type": "response.created", "response": stub}))
    events.append(
        pack("response.in_progress", {"type": "response.in_progress", "response": stub})
    )

    final_output: list[dict[str, Any]] = []
    output_index = 0
    step = 48

    for item in raw_output:
        itype = item.get("type")
        if itype == "function_call":
            call_id = str(item.get("call_id") or f"call_{uuid.uuid4().hex[:16]}")
            item_id = str(item.get("id") or f"fc_{uuid.uuid4().hex[:16]}")
            name = str(item.get("name") or "")
            args = item.get("arguments")
            if not isinstance(args, str):
                args = json.dumps(args or {}, ensure_ascii=False)
            fc_item = {
                "type": "function_call",
                "id": item_id,
                "call_id": call_id,
                "name": name,
                "arguments": "",
                "status": "in_progress",
            }
            events.append(
                pack(
                    "response.output_item.added",
                    {
                        "type": "response.output_item.added",
                        "output_index": output_index,
                        "item": fc_item,
                    },
                )
            )
            if args:
                for i in range(0, len(args), step):
                    events.append(
                        pack(
                            "response.function_call_arguments.delta",
                            {
                                "type": "response.function_call_arguments.delta",
                                "item_id": item_id,
                                "output_index": output_index,
                                "delta": args[i : i + step],
                            },
                        )
                    )
            events.append(
                pack(
                    "response.function_call_arguments.done",
                    {
                        "type": "response.function_call_arguments.done",
                        "item_id": item_id,
                        "output_index": output_index,
                        "arguments": args,
                    },
                )
            )
            done_fc = {
                "type": "function_call",
                "id": item_id,
                "call_id": call_id,
                "name": name,
                "arguments": args,
                "status": "completed",
            }
            events.append(
                pack(
                    "response.output_item.done",
                    {
                        "type": "response.output_item.done",
                        "output_index": output_index,
                        "item": done_fc,
                    },
                )
            )
            final_output.append(done_fc)
            output_index += 1
            continue

        if itype != "message":
            continue

        item_id = str(item.get("id") or f"msg_{uuid.uuid4().hex[:16]}")
        text = ""
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text":
                text += str(part.get("text") or "")

        content_index = 0
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
        events.append(
            pack(
                "response.content_part.added",
                {
                    "type": "response.content_part.added",
                    "item_id": item_id,
                    "output_index": output_index,
                    "content_index": content_index,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                },
            )
        )
        if text:
            for i in range(0, len(text), step):
                events.append(
                    pack(
                        "response.output_text.delta",
                        {
                            "type": "response.output_text.delta",
                            "item_id": item_id,
                            "output_index": output_index,
                            "content_index": content_index,
                            "delta": text[i : i + step],
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
        final_output.append(done_item)
        output_index += 1

    # Fallback: empty message if nothing in output (should be rare)
    if not final_output:
        item_id = f"msg_{uuid.uuid4().hex[:16]}"
        done_item = {
            "type": "message",
            "id": item_id,
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "", "annotations": []}],
        }
        events.append(
            pack(
                "response.output_item.added",
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {**done_item, "status": "in_progress", "content": []},
                },
            )
        )
        events.append(
            pack(
                "response.content_part.added",
                {
                    "type": "response.content_part.added",
                    "item_id": item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                },
            )
        )
        events.append(
            pack(
                "response.output_text.done",
                {
                    "type": "response.output_text.done",
                    "item_id": item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "text": "",
                },
            )
        )
        events.append(
            pack(
                "response.content_part.done",
                {
                    "type": "response.content_part.done",
                    "item_id": item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                },
            )
        )
        events.append(
            pack(
                "response.output_item.done",
                {
                    "type": "response.output_item.done",
                    "output_index": 0,
                    "item": done_item,
                },
            )
        )
        final_output = [done_item]

    completed = dict(resp)
    completed["id"] = rid
    completed["status"] = "completed"
    completed["output"] = final_output
    events.append(
        pack("response.completed", {"type": "response.completed", "response": completed})
    )
    return events
