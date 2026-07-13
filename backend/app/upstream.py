"""Upstream LLM adapters — Gemini, Claude, GPT (chat/responses), Grok."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.catalog import BY_ID, get_model
from app.config import get_settings

settings = get_settings()


class UpstreamError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


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
    system = None
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        text = _plain_text(m.get("content"))
        if role == "system":
            system = (system + "\n" + text) if system else text
            continue
        if role not in ("user", "assistant"):
            role = "user"
        out.append({"role": role, "content": text})
    if not out:
        out = [{"role": "user", "content": ""}]
    return system, out


def _openai_from_claude(data: dict[str, Any], model: str) -> dict[str, Any]:
    content = data.get("content")
    text = _plain_text(content)
    usage = data.get("usage") or {}
    return {
        "id": data.get("id") or f"claude-{model}",
        "object": "chat.completion",
        "model": data.get("model") or model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": data.get("stop_reason") or "stop",
            }
        ],
        "usage": {
            "prompt_tokens": int(usage.get("input_tokens") or 0),
            "completion_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("input_tokens") or 0)
            + int(usage.get("output_tokens") or 0),
        },
    }


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
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        try:
            data = r.json()
        except Exception as e:
            raise UpstreamError(f"Upstream non-JSON {r.status_code}: {r.text[:400]}", 502) from e
        if (
            isinstance(data, dict)
            and data.get("code") not in (None, 200)
            and "choices" not in data
            and "content" not in data
            and "output" not in data
        ):
            raise UpstreamError(
                f"Upstream error: {json.dumps(data, ensure_ascii=False)[:800]}",
                502,
            )
        if r.status_code >= 400:
            raise UpstreamError(
                f"Upstream error {r.status_code}: {json.dumps(data, ensure_ascii=False)[:800]}",
                502,
            )
        return data


async def chat_gemini(model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    meta = get_model(model) or {}
    path = meta.get("path") or GEMINI_PATHS.get(model) or model
    base = settings.upstream_base_url
    if not base:
        raise UpstreamError("UPSTREAM_BASE_URL не задан", 500)
    url = f"{base}/{path}/v1/chat/completions"
    payload = {
        "messages": _normalize_gemini_messages(messages),
        "stream": False,
        "include_thoughts": False,
        "reasoning_effort": "low",
    }
    data = await _post_json(url, payload)
    if "choices" not in data:
        raise UpstreamError(f"Unexpected Gemini response: {json.dumps(data, ensure_ascii=False)[:800]}", 502)
    data.setdefault("model", model)
    return data


async def chat_openai_path(model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    """GPT-5.2-style: POST /{path}/v1/chat/completions."""
    meta = get_model(model) or {}
    path = meta.get("path") or model
    base = settings.upstream_base_url
    if not base:
        raise UpstreamError("UPSTREAM_BASE_URL не задан", 500)
    url = f"{base}/{path}/v1/chat/completions"
    payload = {
        "messages": _normalize_gemini_messages(messages),
        "stream": False,
        "reasoning_effort": "low",
    }
    data = await _post_json(url, payload)
    if "choices" not in data:
        raise UpstreamError(
            f"Unexpected OpenAI-chat response: {json.dumps(data, ensure_ascii=False)[:800]}",
            502,
        )
    data.setdefault("model", model)
    return data


async def chat_responses(model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    """GPT-5.4+/Codex/Grok via Kie Responses API."""
    meta = get_model(model) or {}
    path = meta.get("path") or "codex/v1/responses"
    upstream_model = meta.get("upstream_model") or model
    base = settings.upstream_base_url
    if not base:
        raise UpstreamError("UPSTREAM_BASE_URL не задан", 500)
    url = f"{base}/{path.lstrip('/')}"
    payload: dict[str, Any] = {
        "model": upstream_model,
        "input": _messages_to_responses_input(messages),
        "reasoning": {"effort": "low"},
        "stream": False,
    }
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


async def chat_claude(model: str, messages: list[dict[str, Any]], max_tokens: int = 4096) -> dict[str, Any]:
    system, msgs = _claude_messages(messages)
    base = settings.upstream_base_url
    if not base:
        raise UpstreamError("UPSTREAM_BASE_URL не задан", 500)
    url = f"{base}/claude/v1/messages"
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": msgs,
    }
    if system:
        payload["system"] = system
    data = await _post_json(url, payload)
    if "content" not in data and "choices" not in data:
        raise UpstreamError(f"Unexpected Claude response: {json.dumps(data, ensure_ascii=False)[:800]}", 502)
    if "choices" in data:
        data.setdefault("model", model)
        return data
    return _openai_from_claude(data, model)


async def chat_completions(
    *,
    model: str,
    messages: list[dict[str, Any]],
    stream: bool = False,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    if stream:
        raise UpstreamError("Streaming not implemented in MVP gateway yet", 400)

    meta = get_model(model)
    if not meta:
        model = "gemini-2.5-flash"
        meta = get_model(model)

    adapter = meta.get("adapter")
    if adapter == "pending" or not meta.get("ready"):
        raise UpstreamError(
            f"Модель {model} есть в каталоге, но ещё не подключена. "
            "Сейчас работают чат-модели: Gemini, Claude, GPT, Grok + ultra-mode.",
            400,
        )
    if adapter == "gemini":
        return await chat_gemini(model, messages)
    if adapter == "claude":
        return await chat_claude(model, messages, max_tokens=max_tokens or 4096)
    if adapter == "openai_chat":
        return await chat_openai_path(model, messages)
    if adapter == "responses":
        return await chat_responses(model, messages)
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
