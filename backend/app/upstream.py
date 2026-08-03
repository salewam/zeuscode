"""Upstream LLM adapters — A6 only for chat (+ optional direct DeepSeek helper).

Kie.ai paths are removed. Every user-facing chat call goes through
``chat_completions`` → ``chat_a6`` (OpenAI-compatible flat /v1).
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
    """Legacy parts[] wrapper. Must keep tool_calls / tool_call_id (agent memory)."""
    # Prefer the shared OpenAI tool-safe normalizer, then wrap text as parts[].
    return normalize_openai_compat_messages(messages, as_parts=True)


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
    # Legacy Kie path helper — must never hit api.kie.ai again.
    if "kie.ai" in (url or "").lower():
        raise UpstreamError("Kie.ai upstream removed — use A6", 500)
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
        # Always tool-safe — same protocol for every model/path.
        "messages": normalize_openai_compat_messages(messages, as_parts=True),
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
        "messages": normalize_openai_compat_messages(messages, as_parts=True),
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
    raise UpstreamError("Kie.ai Gemini path removed — use chat_completions (A6)", 500)


async def chat_openai_path(
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    *,
    tools: list[Any] | None = None,
    tool_choice: Any | None = None,
) -> dict[str, Any]:
    raise UpstreamError("Kie.ai OpenAI-chat path removed — use chat_completions (A6)", 500)


async def chat_responses(
    model: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[Any] | None = None,
) -> dict[str, Any]:
    raise UpstreamError("Kie.ai Responses path removed — use chat_completions (A6)", 500)


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
    raise UpstreamError("Kie.ai Claude path removed — use chat_completions (A6)", 500)


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
    # Same tool-safe messages for all models (never strip tool rounds).
    msgs = normalize_openai_compat_messages(messages, as_parts=False)
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


# Transient A6 / CDN failures — retry before failing the ZeusCode turn.
_A6_RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524})
# Client / catalog mistakes — do not poison supplier health for 2h.
_A6_PERMANENT_STATUSES = frozenset({400, 401, 403, 404, 422})


def _a6_retry_delay(attempt: int, status_code: int) -> float:
    """attempt is 1-based; exponential backoff, longer on 429."""
    delay = min(12.0, 1.25 * (2 ** (attempt - 1)))
    if status_code == 429:
        delay = max(delay, 4.0)
    return delay


async def _a6_keys_for_request(cfg, *, model: str) -> list[tuple[str, str]]:
    """Cheap primary first for this model; skip while that model cools on 70%."""
    from app import a6_health

    out: list[tuple[str, str]] = []
    primary = (cfg.A6_API_KEY or "").strip()
    fb = (getattr(cfg, "A6_API_KEY_FALLBACK", None) or "").strip()

    try_primary = bool(primary)
    if primary and fb and fb != primary:
        try_primary = a6_health.should_try_primary(model)

    if try_primary and primary:
        out.append(("primary", primary))
    if fb and fb != primary:
        out.append(("fallback", fb))
    if not out and primary:
        out.append(("primary", primary))
    return out


def _a6_response_usable(data: dict[str, Any], *, wants_tools: bool) -> bool:
    """True if A6 returned something a client can use (text and/or tool_calls)."""
    ch = (data.get("choices") or [{}])[0]
    msg = ch.get("message") if isinstance(ch, dict) else {}
    if not isinstance(msg, dict):
        return False
    if wants_tools and msg.get("tool_calls"):
        return True
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return True
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and str(part.get("text") or "").strip():
                return True
            if isinstance(part, str) and part.strip():
                return True
    return False


def _a6_error_retry_status(status_code: int, data: Any) -> int:
    status_for_retry = status_code if status_code >= 400 else 502
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        code = str(data["error"].get("code") or data["error"].get("type") or "")
        if "timeout" in code or "unavailable" in code or "rate" in code:
            status_for_retry = (
                524 if "timeout" in code else (429 if "rate" in code else 503)
            )
    return status_for_retry


def _a6_fail_kind(status_code: int | None, exc: BaseException | None) -> str:
    """Classify walk failure: transient → mark supplier dead; permanent → skip."""
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return "transient"
    if status_code is not None and status_code in _A6_PERMANENT_STATUSES:
        return "permanent"
    if status_code is not None and status_code in _A6_RETRY_STATUSES:
        return "transient"
    msg = str(exc or "").lower()
    if "empty upstream" in msg or "unexpected a6" in msg:
        return "transient"
    if "unknown model" in msg or "invalid_request" in msg:
        return "permanent"
    # Default: treat as flaky supplier so the walk can skip it next time.
    return "transient"


async def chat_a6(
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    *,
    temperature: float | None = None,
    tools: list[Any] | None = None,
    tool_choice: Any | None = None,
    reasoning_effort: str | None = None,
    prompt_cache_key: str | None = None,
) -> dict[str, Any]:
    """Flat OpenAI chat on A6 for **every** catalog model (default path).

    Per model:
      • 30% key → walk up to N *live* pricing suppliers (skip dead ~2h);
        each *transient* fail marks that supplier dead for the primary lane
        (400/unknown-model etc. are permanent and do not poison health).
      • If the walk dies → 70% key for ``A6_PRIMARY_COOLDOWN_S`` (15m).
      • 70% key → same live-supplier walk on the fallback lane.
      • After cooldown → 30% again with *new* suppliers (dead still skipped).
      • Success on 30% → clear cooldown + sticky preferred supplier.
    """
    from app import a6_health
    from app.a6_route import resolve_a6_model

    cfg = get_settings()
    base = (cfg.A6_BASE_URL or "https://a6api.com/v1").strip().rstrip("/")
    a6_model = resolve_a6_model(model)
    if not a6_model:
        raise UpstreamError(f"No A6 mapping for model {model}", 400)

    keys = await _a6_keys_for_request(cfg, model=a6_model)
    if not keys:
        raise UpstreamError("A6_API_KEY not configured", 500)

    clean_tools = normalize_openai_tools(tools)
    wants = request_wants_tools(clean_tools)
    plain = normalize_openai_compat_messages(messages, as_parts=False)
    base_payload: dict[str, Any] = {
        "model": a6_model,
        "messages": plain,
        "stream": False,
    }
    if max_tokens:
        base_payload["max_tokens"] = int(max_tokens)
    if temperature is not None:
        base_payload["temperature"] = float(temperature)
    if reasoning_effort:
        base_payload["reasoning_effort"] = str(reasoning_effort)
    if prompt_cache_key:
        # OpenAI-compatible providers combine this stable conversation key
        # with the prefix hash to keep related turns on the same cache shard.
        base_payload["prompt_cache_key"] = str(prompt_cache_key)[:128]
    if wants:
        base_payload["tools"] = clean_tools
        if tool_choice is not None:
            base_payload["tool_choice"] = normalize_tool_choice(tool_choice, clean_tools)

    url = f"{base}/chat/completions"
    cooldown = float(getattr(cfg, "A6_PRIMARY_COOLDOWN_S", 900) or 900)
    dead_ttl = float(getattr(cfg, "A6_DEAD_SUPPLIER_TTL_S", 7200) or 7200)
    top_n = max(1, int(getattr(cfg, "A6_TOP_SUPPLIERS", 3) or 3))
    fb_n = max(1, int(getattr(cfg, "A6_FALLBACK_TOP_SUPPLIERS", top_n) or top_n))
    group_attempts = max(1, int(getattr(cfg, "A6_GROUP_ATTEMPTS", 3) or 3))
    last_exc: BaseException | None = None

    priced = await a6_health.get_enable_groups(pricing_base=base, model=a6_model)

    async def _post_once(
        *,
        key: str,
        key_label: str,
        group: str | None,
        payload: dict[str, Any],
        attempts: int,
    ) -> tuple[dict[str, Any] | None, str]:
        """Returns (data, fail_kind). fail_kind is '' on success."""
        nonlocal last_exc
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        g_label = group or "auto"
        last_status: int | None = None
        for attempt in range(1, attempts + 1):
            body = dict(payload)
            if group:
                body["group"] = group
            log.info(
                "A6_CHAT model=%s upstream=%s key=%s group=%s attempt=%s/%s",
                model,
                a6_model,
                key_label,
                g_label,
                attempt,
                attempts,
            )
            try:
                async with httpx.AsyncClient(timeout=240.0) as client:
                    r = await client.post(url, json=body, headers=headers)
                last_status = int(r.status_code)
                try:
                    data = r.json()
                except Exception as e:
                    last_exc = e
                    if r.status_code in _A6_RETRY_STATUSES and attempt < attempts:
                        await asyncio.sleep(
                            _a6_retry_delay(attempt, r.status_code or 502)
                        )
                        continue
                    return None, _a6_fail_kind(last_status, last_exc)
                if r.status_code >= 400 or (
                    isinstance(data, dict) and data.get("error")
                ):
                    status_for_retry = _a6_error_retry_status(r.status_code, data)
                    last_status = status_for_retry
                    err_msg = ""
                    if isinstance(data, dict) and isinstance(data.get("error"), dict):
                        err_msg = str(
                            data["error"].get("message")
                            or data["error"].get("code")
                            or ""
                        )
                    last_exc = UpstreamError(
                        f"A6 HTTP {status_for_retry}"
                        + (f": {err_msg}" if err_msg else ""),
                        status_for_retry,
                    )
                    if status_for_retry in _A6_RETRY_STATUSES and attempt < attempts:
                        await asyncio.sleep(_a6_retry_delay(attempt, status_for_retry))
                        continue
                    return None, _a6_fail_kind(status_for_retry, last_exc)
                if not isinstance(data, dict) or "choices" not in data:
                    last_exc = UpstreamError("Unexpected A6 response", 502)
                    last_status = 502
                    return None, "transient"
                if not _a6_response_usable(data, wants_tools=wants):
                    last_exc = UpstreamError("A6 empty upstream response", 502)
                    last_status = 502
                    if attempt < attempts:
                        await asyncio.sleep(_a6_retry_delay(attempt, 503))
                        continue
                    return None, "transient"
                data.setdefault("model", model)
                data["_zeus_upstream"] = {
                    "provider": "a6",
                    "upstream_model": a6_model,
                    "a6_key": key_label,
                    "a6_group": g_label,
                }
                return data, ""
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_exc = e
                last_status = 524
                if attempt < attempts:
                    await asyncio.sleep(_a6_retry_delay(attempt, 524))
                    continue
                return None, "transient"
        return None, _a6_fail_kind(last_status, last_exc)

    async def _walk_lane(
        *,
        key: str,
        key_label: str,
        limit: int,
    ) -> tuple[dict[str, Any] | None, list[str | None]]:
        """Try live suppliers for one key lane; mark *transient* failures dead."""
        lane = "primary" if key_label == "primary" else "fallback"
        walk = a6_health.live_supplier_groups(
            priced,
            model=a6_model,
            key_lane=lane,  # type: ignore[arg-type]
            limit=limit,
        )
        walk_opt: list[str | None] = list(walk) if walk else [None]
        log.info(
            "A6_SUPPLIER_WALK model=%s key=%s n=%s groups=%s",
            a6_model,
            key_label,
            len(walk_opt),
            walk_opt,
        )
        for group in walk_opt:
            data, fail_kind = await _post_once(
                key=key,
                key_label=key_label,
                group=group,
                payload=base_payload,
                attempts=group_attempts if group else max(group_attempts, 3),
            )
            if data is not None:
                if group:
                    a6_health.mark_supplier_live(
                        a6_model, group, key_lane=lane  # type: ignore[arg-type]
                    )
                if key_label == "primary":
                    a6_health.mark_model_up(a6_model, reason="live_ok")
                return data, walk_opt
            if group and fail_kind == "transient":
                a6_health.mark_supplier_dead(
                    a6_model,
                    group,
                    key_lane=lane,  # type: ignore[arg-type]
                    ttl_s=dead_ttl,
                    reason=fail_kind,
                )
            elif group and fail_kind == "permanent":
                log.warning(
                    "A6_SUPPLIER_SKIP_PERMANENT model=%s key=%s group=%s",
                    a6_model,
                    key_label,
                    group,
                )
        return None, walk_opt

    for key_i, (key_label, key) in enumerate(keys):
        if key_label == "primary":
            data, tried = await _walk_lane(key=key, key_label="primary", limit=top_n)
            if data is not None:
                return data
            if key_i + 1 < len(keys):
                log.warning(
                    "A6_KEY_FAILOVER model=%s from=primary tried_live=%s",
                    a6_model,
                    tried,
                )
                a6_health.mark_model_down(
                    a6_model, cooldown, reason="top_suppliers_failed"
                )
            continue

        # 70% fallback — same dead-supplier memory on the fallback lane.
        data, _tried_fb = await _walk_lane(key=key, key_label="fallback", limit=fb_n)
        if data is not None:
            return data

    raise UpstreamError(
        f"A6 failed after keys={len(keys)} attempts: {last_exc}",
        502,
    ) from last_exc


async def chat_completions(
    *,
    model: str,
    messages: list[dict[str, Any]],
    stream: bool = False,
    max_tokens: int | None = None,
    temperature: float | None = None,
    tools: list[Any] | None = None,
    tool_choice: Any | None = None,
    reasoning_effort: str | None = None,
    prompt_cache_key: str | None = None,
) -> dict[str, Any]:
    if stream:
        raise UpstreamError("Streaming not implemented in MVP gateway yet", 400)

    from app.a6_route import a6_should_route, resolve_a6_model
    from app.catalog import canonical_model_id

    model = canonical_model_id(model) or (model or "").strip()
    meta = get_model(model)
    if not meta:
        raise UpstreamError(
            f"Unknown model: {model}. Use GET /v1/models for the catalog.",
            400,
        )

    adapter = meta.get("adapter")
    if adapter == "pending" or not meta.get("ready"):
        raise UpstreamError(
            f"Модель {model} есть в каталоге, но ещё не подключена. "
            "Сейчас работают чат-модели: Gemini, Claude, GPT, Grok, DeepSeek + ultra-mode.",
            400,
        )

    if adapter == "ultra":
        raise UpstreamError("Use ultra.run_ultra for ultra-mode", 400)

    # Kie.ai removed — all chat LLMs go through A6 (OpenAI-compatible).
    cfg = get_settings()
    if not (cfg.A6_ENABLED and (cfg.A6_API_KEY or "").strip()):
        raise UpstreamError(
            "A6_API_KEY required (Kie.ai upstream removed). Set A6_API_KEY in .env.",
            500,
        )
    if not a6_should_route(meta) or not resolve_a6_model(model):
        raise UpstreamError(
            f"Model {model} is not routable via A6. Use GET /v1/models.",
            400,
        )
    return await chat_a6(
        model,
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        tools=tools,
        tool_choice=tool_choice,
        reasoning_effort=reasoning_effort,
        prompt_cache_key=prompt_cache_key,
    )


def extract_usage(data: dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    return prompt, completion


def extract_cached_tokens(data: dict[str, Any]) -> int:
    """Prompt tokens served from the provider cache (billed at the cached rate)."""
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return 0
    candidates: list[Any] = []
    for key in ("prompt_tokens_details", "input_tokens_details"):
        details = usage.get(key)
        if isinstance(details, dict):
            candidates.append(details.get("cached_tokens"))
    # OpenAI-compat flattens it; Anthropic-compat names it cache_read_input_tokens.
    candidates.extend(
        (usage.get("cached_tokens"), usage.get("cache_read_input_tokens"))
    )
    for raw in candidates:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0


def extract_text(data: dict[str, Any]) -> str:
    try:
        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        if isinstance(content, list):
            return "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
        return str(content)
    except (KeyError, IndexError, TypeError):
        return ""
