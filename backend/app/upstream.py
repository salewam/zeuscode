"""Upstream LLM adapters — Kie family contracts + DeepSeek.

Zeus never sends raw Anthropic/OpenAI SDK shapes to Kie. Every user-facing
chat call goes through ``chat_completions`` → a family builder that matches
docs.kie.ai OpenAPI for that adapter:

- claude      → POST /claude/v1/messages
                (thinkingFlag, stream:false, max_tokens clamped)
- gemini      → POST /{path}/v1/chat/completions
                (messages as parts[], stream:false, include_thoughts)
- openai_chat → POST /{path}/v1/chat/completions
- responses   → POST /{codex|grok|api}/v1/responses
                (input[], reasoning.effort, stream:false)
- deepseek    → direct DeepSeek OpenAI-compatible API (not Kie)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from app.catalog import BY_ID, get_model
from app.config import get_settings
from app.openai_tools import (
    claude_messages_with_tools,
    normalize_openai_compat_messages,
    normalize_openai_tools,
    normalize_tool_choice,
    openai_from_claude_content,
    openai_tools_to_claude,
    request_wants_tools,
)

settings = get_settings()
log = logging.getLogger("zeus.upstream")


class UpstreamError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _is_rate_limit(status_code: int, body: Any) -> bool:
    if status_code == 429:
        return True
    text = ""
    if isinstance(body, dict):
        text = json.dumps(body, ensure_ascii=False).lower()
    else:
        text = str(body or "").lower()
    needles = (
        "rate limit",
        "rate_limit",
        "too many requests",
        "quota exceeded",
        "tpm",
        "rpm",
    )
    return any(n in text for n in needles)


def _raise_upstream_http_error(url: str, status_code: int, data: Any) -> None:
    """Log loudly (esp. 429) then raise — evidence for upstream limit tickets."""
    body = (
        json.dumps(data, ensure_ascii=False)[:800]
        if not isinstance(data, str)
        else data[:800]
    )
    rate = _is_rate_limit(status_code, data)
    out_status = 429 if rate else (status_code if status_code >= 400 else 502)
    if rate:
        log.error(
            "UPSTREAM_RATE_LIMIT status=%s url=%s ts=%s body=%s",
            status_code,
            url,
            int(time.time()),
            body,
        )
        try:
            from app.fusion.metrics import note_dead_model

            note_dead_model(f"rate_limit:{status_code}")
        except Exception:  # noqa: BLE001
            pass
        raise UpstreamError(
            f"Upstream RATE LIMIT {status_code}: {body}",
            429,
        )
    log.warning(
        "UPSTREAM_HTTP_ERROR status=%s url=%s body=%s",
        status_code,
        url,
        body,
    )
    raise UpstreamError(f"Upstream error {status_code}: {body}", out_status)


# Back-compat alias
GEMINI_PATHS = {
    mid: (meta.get("path") or mid)
    for mid, meta in BY_ID.items()
    if meta.get("adapter") == "gemini"
}


def _normalize_gemini_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        elif isinstance(content, list):
            fixed = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    fixed.append(part)
                elif isinstance(part, dict) and "text" in part:
                    fixed.append({"type": "text", "text": part["text"]})
                elif isinstance(part, str):
                    fixed.append({"type": "text", "text": part})
            content = fixed or [{"type": "text", "text": ""}]
        out.append({"role": role, "content": content})
    return out


def _plain_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                parts.append(str(p.get("text") or p.get("content") or ""))
        return "\n".join(x for x in parts if x)
    return str(content or "")


def _claude_messages(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    """Kie Claude Messages: plain string content, user/assistant only, alternating roles."""
    system = None
    out: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "user").strip().lower()
        text = _plain_text(m.get("content"))
        if role in ("system", "developer"):
            if text.strip():
                system = f"{system}\n{text}".strip() if system else text
            continue
        if role not in ("user", "assistant"):
            role = "user"
        # Empty assistant turns break Kie; skip. Empty user → keep as "" only if alone later.
        if role == "assistant" and not text.strip():
            continue
        if out and out[-1]["role"] == role:
            prev = out[-1]["content"]
            out[-1]["content"] = f"{prev}\n{text}".strip() if prev else text
            continue
        out.append({"role": role, "content": text})
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": "Продолжи."})
    if not out:
        out = [{"role": "user", "content": ""}]
    return system, out


def _openai_from_claude(data: dict[str, Any], model: str) -> dict[str, Any]:
    return openai_from_claude_content(data, model)


def _messages_to_responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        text = _plain_text(m.get("content"))
        if role == "system":
            items.append(
                {"role": "system", "content": [{"type": "input_text", "text": text}]}
            )
        elif role == "assistant":
            items.append(
                {"role": "assistant", "content": [{"type": "output_text", "text": text}]}
            )
        else:
            items.append(
                {"role": "user", "content": [{"type": "input_text", "text": text}]}
            )
    return items or [{"role": "user", "content": [{"type": "input_text", "text": ""}]}]


def _openai_from_responses(data: dict[str, Any], model: str) -> dict[str, Any]:
    chunks: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("type") in ("output_text", "text"):
                    chunks.append(str(part.get("text") or ""))
        elif item.get("type") == "output_text":
            chunks.append(str(item.get("text") or ""))
    text = "".join(chunks).strip()
    usage = data.get("usage") or {}
    prompt = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    completion = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    # Some Kie responses under-count input_tokens; keep non-negative ints
    return {
        "id": data.get("id") or f"resp-{model}",
        "object": "chat.completion",
        "model": data.get("model") or model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
    }


async def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    key = settings.upstream_api_key
    if not key:
        raise UpstreamError("UPSTREAM_API_KEY not configured", 500)
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    # 120s: fail stuck calls earlier without cutting normal studio quality budgets
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        try:
            data = r.json()
        except Exception as e:
            log.warning(
                "UPSTREAM_NON_JSON status=%s url=%s body=%s",
                r.status_code,
                url,
                (r.text or "")[:400],
            )
            if _is_rate_limit(r.status_code, r.text):
                _raise_upstream_http_error(url, r.status_code, r.text)
            raise UpstreamError(
                f"Upstream non-JSON {r.status_code}: {r.text[:400]}", 502
            ) from e
        if (
            isinstance(data, dict)
            and data.get("code") not in (None, 200)
            and "choices" not in data
            and "content" not in data
            and "output" not in data
        ):
            # Some gateways return HTTP 200 + business code for rate limit
            biz = data.get("code")
            try:
                biz_i = int(biz) if biz is not None else 0
            except (TypeError, ValueError):
                biz_i = 0
            if biz_i == 429 or _is_rate_limit(r.status_code, data):
                _raise_upstream_http_error(url, 429 if biz_i == 429 else r.status_code, data)
            _raise_upstream_http_error(url, r.status_code if r.status_code >= 400 else 502, data)
        if r.status_code >= 400:
            _raise_upstream_http_error(url, r.status_code, data)
        return data


def build_gemini_payload(
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    *,
    tools: list[Any] | None = None,
    tool_choice: Any | None = None,
) -> dict[str, Any]:
    """Kie Gemini OpenAI-compat: parts[] content, stream off, thoughts off by default."""
    clean_tools = normalize_openai_tools(tools)
    wants = request_wants_tools(clean_tools)
    if tools and not wants:
        log.warning("gemini tools dropped after normalize (was %s entries)", len(tools or []))
    payload: dict[str, Any] = {
        "messages": (
            normalize_openai_compat_messages(messages, as_parts=True)
            if wants
            else _normalize_gemini_messages(messages)
        ),
        "stream": False,
        "include_thoughts": False,
        "reasoning_effort": "low",
    }
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)
    if wants:
        payload["tools"] = clean_tools
        if tool_choice is not None:
            payload["tool_choice"] = normalize_tool_choice(tool_choice, clean_tools)
    return payload


def build_openai_chat_payload(
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    *,
    tools: list[Any] | None = None,
    tool_choice: Any | None = None,
) -> dict[str, Any]:
    """Kie GPT chat-completions path (e.g. gpt-5-2)."""
    clean_tools = normalize_openai_tools(tools)
    wants = request_wants_tools(clean_tools)
    if tools and not wants:
        log.warning("openai_chat tools dropped after normalize (was %s entries)", len(tools or []))
    payload: dict[str, Any] = {
        "messages": (
            normalize_openai_compat_messages(messages, as_parts=True)
            if wants
            else _normalize_gemini_messages(messages)
        ),
        "stream": False,
        "reasoning_effort": "low",
    }
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)
    if wants:
        payload["tools"] = clean_tools
        if tool_choice is not None:
            payload["tool_choice"] = normalize_tool_choice(tool_choice, clean_tools)
    return payload


def build_responses_payload(
    model: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[Any] | None = None,
) -> dict[str, Any]:
    """Kie Codex/Grok Responses API: input[] + reasoning.effort + stream:false."""
    meta = get_model(model) or {}
    upstream_model = meta.get("upstream_model") or model
    payload: dict[str, Any] = {
        "model": upstream_model,
        "input": _messages_to_responses_input(messages),
        "reasoning": {"effort": "low"},
        "stream": False,
    }
    # Responses tools: sanitize first, then flatten to Responses function defs.
    clean = normalize_openai_tools(tools)
    if clean:
        payload["tools"] = [
            {
                "type": "function",
                "name": t["function"]["name"],
                "description": t["function"].get("description") or "",
                "parameters": t["function"].get("parameters")
                or {"type": "object", "properties": {}},
            }
            for t in clean
        ]
        payload["tool_choice"] = "auto"
    return payload


async def chat_gemini(
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    *,
    tools: list[Any] | None = None,
    tool_choice: Any | None = None,
) -> dict[str, Any]:
    meta = get_model(model) or {}
    path = meta.get("path") or GEMINI_PATHS.get(model) or model
    base = settings.upstream_base_url
    if not base:
        raise UpstreamError("UPSTREAM_BASE_URL не задан", 500)
    url = f"{base}/{path}/v1/chat/completions"
    payload = build_gemini_payload(
        messages, max_tokens=max_tokens, tools=tools, tool_choice=tool_choice
    )
    data = await _post_json(url, payload)
    if "choices" not in data:
        raise UpstreamError(f"Unexpected Gemini response: {json.dumps(data, ensure_ascii=False)[:800]}", 502)
    data.setdefault("model", model)
    return data


async def chat_openai_path(
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    *,
    tools: list[Any] | None = None,
    tool_choice: Any | None = None,
) -> dict[str, Any]:
    """GPT-5.2-style: POST /{path}/v1/chat/completions."""
    meta = get_model(model) or {}
    path = meta.get("path") or model
    base = settings.upstream_base_url
    if not base:
        raise UpstreamError("UPSTREAM_BASE_URL не задан", 500)
    url = f"{base}/{path}/v1/chat/completions"
    payload = build_openai_chat_payload(
        messages, max_tokens=max_tokens, tools=tools, tool_choice=tool_choice
    )
    data = await _post_json(url, payload)
    if "choices" not in data:
        raise UpstreamError(
            f"Unexpected OpenAI-chat response: {json.dumps(data, ensure_ascii=False)[:800]}",
            502,
        )
    data.setdefault("model", model)
    return data


async def chat_responses(
    model: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[Any] | None = None,
) -> dict[str, Any]:
    """GPT-5.4+/Codex/Grok via Kie Responses API."""
    meta = get_model(model) or {}
    path = meta.get("path") or "codex/v1/responses"
    base = settings.upstream_base_url
    if not base:
        raise UpstreamError("UPSTREAM_BASE_URL не задан", 500)
    url = f"{base}/{path.lstrip('/')}"
    payload = build_responses_payload(model, messages, tools=tools)
    data = await _post_json(url, payload)
    if "output" not in data and "choices" not in data:
        raise UpstreamError(
            f"Unexpected Responses API reply: {json.dumps(data, ensure_ascii=False)[:800]}",
            502,
        )
    if "choices" in data:
        data.setdefault("model", model)
        return data
    return _openai_from_responses(data, model)


def _output_token_ceiling(explicit: int | None = None) -> int:
    """Claude requires max_tokens; use a high ceiling so answers are not cut mid-task."""
    if explicit is not None and int(explicit) > 0:
        return int(explicit)
    try:
        n = int(getattr(settings, "UPSTREAM_MAX_OUTPUT_TOKENS", 65536) or 65536)
    except Exception:  # noqa: BLE001
        n = 65536
    return max(1024, n)


def _claude_token_ceiling(explicit: int | None = None) -> int:
    """Kie Claude: clamp max_tokens — >=8192 on long HTML returns Internal error 500."""
    try:
        hard = int(getattr(settings, "UPSTREAM_CLAUDE_MAX_TOKENS", 7680) or 7680)
    except Exception:  # noqa: BLE001
        hard = 7680
    hard = max(1024, hard)
    wanted = _output_token_ceiling(explicit)
    return min(wanted, hard)


def build_claude_payload(
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    *,
    tools: list[Any] | None = None,
) -> dict[str, Any]:
    """Kie Claude Messages (docs + support 2026-07).

    Canonical working shape:
      model, messages[{role, content:str}], thinkingFlag, stream:false, max_tokens≤clamp
    With agent tools: Anthropic tools[] + tool_use/tool_result blocks.
    """
    meta = get_model(model) or {}
    # Always catalog spelling (Claude-fable-5 → claude-fable-5), never client casing.
    upstream_model = meta.get("upstream_model") or meta.get("id") or model
    wants = request_wants_tools(tools)
    if wants:
        system, msgs = claude_messages_with_tools(messages)
    else:
        system, msgs = _claude_messages(messages)
    try:
        thinking = bool(getattr(settings, "UPSTREAM_CLAUDE_THINKING_FLAG", True))
    except Exception:  # noqa: BLE001
        thinking = True
    payload: dict[str, Any] = {
        "model": str(upstream_model),
        "messages": msgs,
        "max_tokens": _claude_token_ceiling(max_tokens),
        "stream": False,
        # Always send the flag explicitly — omitting it is a known Kie 500 trigger.
        "thinkingFlag": thinking,
    }
    if system:
        # Anthropic-compatible optional system; not in Motohaus support sample but
        # used by Fusion prompts. Keep as top-level, never as a messages role.
        payload["system"] = system
    if wants:
        claude_tools = openai_tools_to_claude(tools)
        if claude_tools:
            payload["tools"] = claude_tools
    return payload


async def chat_claude(
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    *,
    tools: list[Any] | None = None,
) -> dict[str, Any]:
    base = settings.upstream_base_url
    if not base:
        raise UpstreamError("UPSTREAM_BASE_URL не задан", 500)
    url = f"{base}/claude/v1/messages"
    payload = build_claude_payload(model, messages, max_tokens=max_tokens, tools=tools)
    log.debug(
        "KIE_CLAUDE_PAYLOAD model=%s max_tokens=%s thinkingFlag=%s stream=%s tools=%s",
        payload.get("model"),
        payload.get("max_tokens"),
        payload.get("thinkingFlag"),
        payload.get("stream"),
        bool(payload.get("tools")),
    )
    data = await _post_json(url, payload)
    if "content" not in data and "choices" not in data:
        raise UpstreamError(f"Unexpected Claude response: {json.dumps(data, ensure_ascii=False)[:800]}", 502)
    if "choices" in data:
        data.setdefault("model", model)
        return data
    return _openai_from_claude(data, model)


async def chat_deepseek(
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    temperature: float | None = None,
    *,
    tools: list[Any] | None = None,
    tool_choice: Any | None = None,
) -> dict[str, Any]:
    """Direct DeepSeek OpenAI-compatible chat (separate API key)."""
    key = settings.DEEPSEEK_API_KEY.strip()
    if not key:
        raise UpstreamError("DEEPSEEK_API_KEY not configured", 500)
    meta = get_model(model) or {}
    upstream_model = meta.get("upstream_model") or model
    base = (settings.DEEPSEEK_BASE_URL or "https://api.deepseek.com").rstrip("/")
    url = f"{base}/v1/chat/completions"
    clean_tools = normalize_openai_tools(tools)
    wants = request_wants_tools(clean_tools)
    if wants:
        msgs = normalize_openai_compat_messages(messages, as_parts=False)
    else:
        msgs = [
            {"role": m.get("role", "user"), "content": _plain_text(m.get("content"))}
            for m in messages
        ]
    payload: dict[str, Any] = {
        "model": upstream_model,
        "messages": msgs,
        "stream": False,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if temperature is not None:
        payload["temperature"] = temperature
    if wants:
        payload["tools"] = clean_tools
        if tool_choice is not None:
            payload["tool_choice"] = normalize_tool_choice(tool_choice, clean_tools)
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        try:
            data = r.json()
        except Exception as e:
            log.warning(
                "DEEPSEEK_NON_JSON status=%s url=%s body=%s",
                r.status_code,
                url,
                (r.text or "")[:400],
            )
            raise UpstreamError(f"DeepSeek non-JSON {r.status_code}: {r.text[:400]}", 502) from e
        if r.status_code >= 400:
            _raise_upstream_http_error(url, r.status_code, data)
        if "choices" not in data:
            raise UpstreamError(
                f"Unexpected DeepSeek response: {json.dumps(data, ensure_ascii=False)[:800]}",
                502,
            )
        data.setdefault("model", model)
        return data


async def chat_completions(
    *,
    model: str,
    messages: list[dict[str, Any]],
    stream: bool = False,
    max_tokens: int | None = None,
    temperature: float | None = None,
    tools: list[Any] | None = None,
    tool_choice: Any | None = None,
) -> dict[str, Any]:
    if stream:
        raise UpstreamError("Streaming not implemented in MVP gateway yet", 400)

    from app.catalog import canonical_model_id

    model = canonical_model_id(model) or (model or "").strip()
    meta = get_model(model)
    if not meta:
        model = "gemini-2.5-flash"
        meta = get_model(model)

    adapter = meta.get("adapter")
    if adapter == "pending" or not meta.get("ready"):
        raise UpstreamError(
            f"Модель {model} есть в каталоге, но ещё не подключена. "
            "Сейчас работают чат-модели: Gemini, Claude, GPT, Grok, DeepSeek + ultra-mode.",
            400,
        )
    if adapter == "gemini":
        return await chat_gemini(
            model, messages, max_tokens=max_tokens, tools=tools, tool_choice=tool_choice
        )
    if adapter == "claude":
        return await chat_claude(model, messages, max_tokens=max_tokens, tools=tools)
    if adapter == "openai_chat":
        return await chat_openai_path(
            model, messages, max_tokens=max_tokens, tools=tools, tool_choice=tool_choice
        )
    if adapter == "responses":
        return await chat_responses(model, messages, tools=tools)
    if adapter == "deepseek":
        return await chat_deepseek(
            model,
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
        )
    if adapter == "ultra":
        raise UpstreamError("Use ultra.run_ultra for ultra-mode", 400)
    raise UpstreamError(f"Unknown adapter for {model}", 400)


def extract_usage(data: dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    return prompt, completion


def extract_text(data: dict[str, Any]) -> str:
    try:
        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        if isinstance(content, list):
            return "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
        return str(content)
    except (KeyError, IndexError, TypeError):
        return ""
