"""OpenAI tools protocol for agent clients (OpenCode / Cline / Roo).

OpenCode runs bash/read/edit locally. Zeus must:
1) accept `tools` + `tool_choice`
2) preserve `assistant.tool_calls` and `role=tool` turns
3) return OpenAI-shaped `tool_calls` (not strip them to plain text)

Fusion/Cursor chat without tools keeps using sanitize_messages (strip path).
"""

from __future__ import annotations

import json
from typing import Any


def _plain(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                parts.append(str(p.get("text") or p.get("content") or ""))
        return "\n".join(x for x in parts if x)
    if content is None:
        return ""
    return str(content)


def request_wants_tools(tools: Any | None) -> bool:
    return isinstance(tools, list) and len(tools) > 0


def normalize_openai_tools(tools: Any | None) -> list[dict[str, Any]]:
    """Force OpenAI chat tools shape that Kie accepts.

    Drops / repairs entries that trigger:
      {"code": 400, "msg": "Tool type or function is null"}
    Accepts flat Responses-style {name, parameters} and Anthropic-ish {name, input_schema}.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        name = ""
        description = ""
        params: Any = None

        fn = t.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            name = str(fn.get("name") or "").strip()
            description = str(fn.get("description") or name)
            params = fn.get("parameters") if fn.get("parameters") is not None else fn.get("input_schema")
        elif t.get("name"):
            # Flat chat / Responses / Anthropic-ish
            name = str(t.get("name") or "").strip()
            description = str(t.get("description") or name)
            params = t.get("parameters") if t.get("parameters") is not None else t.get("input_schema")
        else:
            continue

        if not name or name in seen:
            continue
        if not isinstance(params, dict):
            params = {"type": "object", "properties": {}}
        # Kie rejects null type/function — always emit full shape
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description or name,
                    "parameters": params,
                },
            }
        )
        seen.add(name)
    return out


def normalize_tool_choice(tool_choice: Any, tools: list[dict[str, Any]] | None = None) -> Any:
    """Keep tool_choice safe after tools sanitization."""
    if tool_choice is None:
        return None
    if isinstance(tool_choice, str):
        return tool_choice if tool_choice in ("auto", "none", "required") else "auto"
    if isinstance(tool_choice, dict):
        # {"type":"function","function":{"name":"..."}}
        fn = tool_choice.get("function") if isinstance(tool_choice.get("function"), dict) else {}
        name = (fn or {}).get("name") or tool_choice.get("name")
        allowed = {
            str((t.get("function") or {}).get("name") or "")
            for t in (tools or [])
            if isinstance(t, dict)
        }
        if name and (not allowed or str(name) in allowed):
            return {
                "type": "function",
                "function": {"name": str(name)},
            }
        return "auto"
    return "auto"


def normalize_tool_calls(tool_calls: Any) -> list[dict[str, Any]]:
    """Repair assistant.tool_calls so type/function are never null."""
    out: list[dict[str, Any]] = []
    for i, tc in enumerate(tool_calls or []):
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else None
        if fn and fn.get("name"):
            name = str(fn.get("name") or "").strip()
            args = fn.get("arguments")
        else:
            name = str(tc.get("name") or "").strip()
            args = tc.get("arguments")
        if not name:
            continue
        if isinstance(args, dict):
            args_s = json.dumps(args, ensure_ascii=False)
        elif args is None:
            args_s = "{}"
        else:
            args_s = str(args)
        out.append(
            {
                "id": str(tc.get("id") or f"call_{i}_{name}"),
                "type": "function",
                "function": {"name": name, "arguments": args_s},
            }
        )
    return out


def prepare_agent_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep OpenAI tool protocol intact for upstream agent loops."""
    out: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "user").strip().lower()
        if role == "tool":
            item: dict[str, Any] = {
                "role": "tool",
                "content": _plain(m.get("content")),
            }
            if m.get("tool_call_id"):
                item["tool_call_id"] = str(m["tool_call_id"])
            if m.get("name"):
                item["name"] = str(m["name"])
            out.append(item)
            continue
        if role not in ("system", "user", "assistant", "developer"):
            continue
        if role == "developer":
            role = "system"
        item = {"role": role}
        content = m.get("content")
        tool_calls = m.get("tool_calls")
        if role == "assistant" and tool_calls:
            cleaned = normalize_tool_calls(tool_calls)
            if cleaned:
                item["tool_calls"] = cleaned
            # OpenAI allows null content when only tool_calls are present
            if content is None or content == "":
                item["content"] = None
            else:
                item["content"] = _plain(content)
        else:
            item["content"] = _plain(content)
        if item.get("content") or item.get("tool_calls") or role == "user":
            out.append(item)
    return out or [{"role": "user", "content": "Привет"}]


def normalize_openai_compat_messages(
    messages: list[dict[str, Any]], *, as_parts: bool = True
) -> list[dict[str, Any]]:
    """Gemini/DeepSeek/OpenAI-chat: tool roles + optional parts[] for text."""
    out: list[dict[str, Any]] = []
    for m in prepare_agent_messages(messages):
        role = m["role"]
        if role == "tool":
            out.append(m)
            continue
        content = m.get("content")
        item: dict[str, Any] = {"role": role}
        if m.get("tool_calls"):
            item["tool_calls"] = m["tool_calls"]
        if content is None:
            item["content"] = None
        elif as_parts and role in ("user", "system", "assistant") and not m.get("tool_calls"):
            text = _plain(content)
            item["content"] = [{"type": "text", "text": text}]
        else:
            item["content"] = content if isinstance(content, str) or content is None else _plain(content)
        out.append(item)
    return out


def openai_tools_to_claude(tools: list[Any] | None) -> list[dict[str, Any]]:
    """OpenAI tools[] → Anthropic/Kie Claude tools[]."""
    out: list[dict[str, Any]] = []
    for t in normalize_openai_tools(tools):
        fn = t["function"]
        out.append(
            {
                "name": str(fn["name"]),
                "description": str(fn.get("description") or fn["name"]),
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return out


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            val = json.loads(raw)
            return val if isinstance(val, dict) else {"value": val}
        except Exception:  # noqa: BLE001
            return {"raw": raw}
    return {}


def claude_messages_with_tools(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Convert OpenAI tool turns → Claude Messages tool_use / tool_result blocks."""
    system: str | None = None
    out: list[dict[str, Any]] = []
    for m in prepare_agent_messages(messages):
        role = m["role"]
        if role == "system":
            text = _plain(m.get("content"))
            system = f"{system}\n{text}".strip() if system else text
            continue
        if role == "assistant":
            blocks: list[dict[str, Any]] = []
            text = _plain(m.get("content"))
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in m.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                name = (fn or {}).get("name") or tc.get("name")
                if not name:
                    continue
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": str(tc.get("id") or f"tool_{name}"),
                        "name": str(name),
                        "input": _parse_args((fn or {}).get("arguments")),
                    }
                )
            if blocks:
                out.append({"role": "assistant", "content": blocks})
            continue
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": str(m.get("tool_call_id") or ""),
                "content": _plain(m.get("content")),
            }
            # Merge consecutive tool_results into one user message (Anthropic style)
            if out and out[-1].get("role") == "user" and isinstance(out[-1].get("content"), list):
                prev = out[-1]["content"]
                if prev and all(isinstance(x, dict) and x.get("type") == "tool_result" for x in prev):
                    prev.append(block)
                    continue
            out.append({"role": "user", "content": [block]})
            continue
        # user
        out.append({"role": "user", "content": _plain(m.get("content"))})
    if not out:
        out = [{"role": "user", "content": ""}]
    return system, out


def openai_from_claude_content(data: dict[str, Any], model: str) -> dict[str, Any]:
    """Claude Messages response → OpenAI chat.completion (incl. tool_calls)."""
    content = data.get("content")
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype in ("text", "output_text") and block.get("text"):
                text_parts.append(str(block["text"]))
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "id": str(block.get("id") or f"tool_{block.get('name')}"),
                        "type": "function",
                        "function": {
                            "name": str(block.get("name") or "tool"),
                            "arguments": json.dumps(
                                block.get("input") if isinstance(block.get("input"), dict) else {},
                                ensure_ascii=False,
                            ),
                        },
                    }
                )
    else:
        text_parts.append(_plain(content))

    text = "\n".join(text_parts).strip()
    stop = data.get("stop_reason") or "stop"
    if tool_calls and stop in ("tool_use", "stop", None, ""):
        finish = "tool_calls"
    else:
        finish = "tool_calls" if tool_calls else str(stop)

    message: dict[str, Any] = {"role": "assistant", "content": text or (None if tool_calls else "")}
    if tool_calls:
        message["tool_calls"] = tool_calls

    usage = data.get("usage") or {}
    return {
        "id": data.get("id") or f"claude-{model}",
        "object": "chat.completion",
        "model": data.get("model") or model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish,
            }
        ],
        "usage": {
            "prompt_tokens": int(usage.get("input_tokens") or 0),
            "completion_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("input_tokens") or 0)
            + int(usage.get("output_tokens") or 0),
        },
    }


# Models that work well as OpenCode agent brains when user picked zeus/fusion
AGENT_SOLO_FALLBACKS = (
    "gemini-3.1-pro",
    "deepseek-v4-pro",
    "claude-opus-4-8",
    "gemini-3-pro",
    "deepseek-v4-flash",
    "claude-sonnet-4-6",
)


def pick_agent_solo_model(preferred: list[str] | None = None) -> str:
    from app.catalog import get_model

    for mid in list(preferred or []) + list(AGENT_SOLO_FALLBACKS):
        meta = get_model(mid)
        if meta and meta.get("ready") and meta.get("adapter") not in (None, "pending", "ultra"):
            # Fable has no function calling per Kie docs
            if mid == "claude-fable-5":
                continue
            return mid
    return "gemini-3.1-pro"
