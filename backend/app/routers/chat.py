"""OpenAI-compatible /v1/chat/completions — solo + zeuscode (legacy: zeus/fusion).

Cursor always sends stream=true; fusion streams thinking (no model names) live.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import upstream
from app.catalog import get_model
from app.config import get_settings
from app.cost import estimate_upstream_usd, estimate_user_rub
from app.db import SessionLocal, get_db
from app.deps import get_user_by_api_key
from app.model_policy import assert_model_allowed
from app.models import ApiKey, UsageLog, User
from app.openai_tools import (
    prepare_agent_messages,
    repair_completion_tool_calls,
    request_wants_tools,
)
from app.usage_analytics import (
    RequestTimer,
    extract_result_fields,
    log_product_event,
    prompt_preview_from_messages,
)

router = APIRouter(tags=["chat"])
settings = get_settings()


async def _log_chat(
    db: AsyncSession | None,
    *,
    event: str,
    user: User | None = None,
    api_key: ApiKey | None = None,
    user_id: int | None = None,
    api_key_id: int | None = None,
    key_prefix: str = "",
    model: str = "",
    stream: bool = False,
    session_id: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    data: dict[str, Any] | None = None,
    status_code: int = 0,
    latency_ms: int = 0,
    error: str = "",
    meta: dict[str, Any] | None = None,
) -> None:
    from app.usage_analytics import user_identity_meta

    fields = extract_result_fields(data)
    merged = user_identity_meta(user)
    if meta:
        merged.update(meta)
    await log_product_event(
        db,
        event=event,
        user_id=user.id if user is not None else user_id,
        api_key_id=api_key.id if api_key is not None else api_key_id,
        key_prefix=key_prefix or (getattr(api_key, "key_prefix", None) or ""),
        source="api",
        model=model,
        stream=stream,
        session_id=session_id or "",
        prompt_preview=prompt_preview_from_messages(messages),
        path=fields["path"],
        policy_path=fields["policy_path"],
        leader=fields["leader"],
        routed_by=fields["routed_by"],
        trace_id=fields["trace_id"],
        status_code=status_code,
        latency_ms=latency_ms,
        prompt_tokens=fields["prompt_tokens"],
        completion_tokens=fields["completion_tokens"],
        cost_rub=fields["cost_rub"],
        error=error,
        meta=merged,
    )


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: Any = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[Any] | None = None


class ChatCompletionIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = Field(default="zeuscode")
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    models: list[str] | None = None
    zeus: dict[str, Any] | None = None
    # OpenCode / Cline / Roo agent loop
    tools: list[Any] | None = None
    tool_choice: Any | None = None


def _automatic_tool_session_id(
    *,
    api_key_identity: str,
    messages: list[dict[str, Any]],
) -> str | None:
    """Stable privacy-safe task key for tool clients that omit a session id."""
    identity = str(api_key_identity or "").strip()
    if not identity:
        return None
    rows = list(messages or [])
    last_user_index = max(
        (
            index
            for index, message in enumerate(rows)
            if str(message.get("role") or "").strip().lower() == "user"
        ),
        default=-1,
    )
    has_current_tool_result = any(
        str(message.get("role") or "").strip().lower() in ("tool", "function")
        for message in rows[last_user_index + 1 :]
    )
    if has_current_tool_result:
        for message in rows:
            if str(message.get("role") or "").strip().lower() != "assistant":
                continue
            calls = message.get("tool_calls")
            if not isinstance(calls, list):
                continue
            for call in calls:
                call_id = str(call.get("id") or "").strip() if isinstance(call, dict) else ""
                if call_id:
                    return _tool_call_alias_session_id(identity, call_id)
    # Tool clients such as mini-swe append a synthetic user message after an
    # assistant accidentally returns prose. That message is a retry of the
    # existing tool turn, not a new task. Keep the original tool-call alias so
    # the retry restores its crew state and mandatory-tool contract.
    last_user_content = rows[last_user_index].get("content") if last_user_index >= 0 else ""
    last_user_text = (
        last_user_content
        if isinstance(last_user_content, str)
        else str(last_user_content or "")
    )
    normalized_retry = " ".join(last_user_text.lower().split())
    is_tool_protocol_retry = (
        "tool call error:" in normalized_retry
        and (
            "no tool calls found" in normalized_retry
            or "must include at least one tool call" in normalized_retry
        )
    )
    if is_tool_protocol_retry:
        for message in rows[:last_user_index]:
            if str(message.get("role") or "").strip().lower() != "assistant":
                continue
            calls = message.get("tool_calls")
            if not isinstance(calls, list):
                continue
            for call in calls:
                call_id = str(call.get("id") or "").strip() if isinstance(call, dict) else ""
                if call_id:
                    return _tool_call_alias_session_id(identity, call_id)
    first_task = ""
    task_rows = rows[last_user_index:] if last_user_index >= 0 else rows
    for message in task_rows:
        if str(message.get("role") or "").strip().lower() != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            text = "\n".join(
                str(part.get("text") or part.get("content") or "")
                if isinstance(part, dict)
                else str(part or "")
                for part in content
            ).strip()
        else:
            text = str(content or "").strip()
        if text:
            first_task = " ".join(text.split())
            break
    if not first_task:
        return None
    digest = hashlib.sha256(
        f"{identity}\0{first_task}".encode("utf-8", errors="ignore")
    ).hexdigest()
    return f"auto-tool-{digest[:48]}"


def _tool_call_alias_session_id(api_key_identity: str, tool_call_id: str) -> str:
    digest = hashlib.sha256(
        f"{str(api_key_identity).strip()}\0tool-call\0{str(tool_call_id).strip()}".encode(
            "utf-8", errors="ignore"
        )
    ).hexdigest()
    return f"auto-tool-call-{digest[:48]}"


def _namespace_session_id(api_key_identity: str, session_id: str) -> str:
    digest = hashlib.sha256(
        f"{str(api_key_identity).strip()}\0session\0{str(session_id).strip()}".encode(
            "utf-8", errors="ignore"
        )
    ).hexdigest()
    return f"key-session-{digest[:48]}"


def _namespace_project_scope(api_key_identity: str, project_id: str) -> str:
    """Scope persisted project memory to one API key.

    ``project_id`` is a free-form client string, so keying the store on it
    directly would let any caller read another tenant's file map by guessing
    the name.
    """
    digest = hashlib.sha256(
        f"{str(api_key_identity).strip()}\0project\0{str(project_id).strip()}".encode(
            "utf-8", errors="ignore"
        )
    ).hexdigest()
    return f"key-project-{digest[:48]}"


def _first_emitted_tool_call_id(data: dict[str, Any]) -> str:
    try:
        message = (data.get("choices") or [{}])[0].get("message") or {}
        calls = message.get("tool_calls") or []
        for call in calls:
            call_id = str(call.get("id") or "").strip() if isinstance(call, dict) else ""
            if call_id:
                return call_id
    except (AttributeError, IndexError, TypeError):
        pass
    return ""


async def _apply_sticky_hint(
    db: AsyncSession,
    zeus: dict[str, Any] | None,
    *,
    session_header: str | None,
    api_key_identity: str = "",
    messages: list[dict[str, Any]] | None = None,
    tools_enabled: bool = False,
) -> tuple[dict[str, Any], str | None]:
    """Load sticky Leader hint into zeus (never Path). Returns (zeus, session_id)."""
    from app.fusion import extract_session_id, get_sticky, sticky_leader_hint

    out = dict(zeus) if isinstance(zeus, dict) else {}
    # Crew counters/evidence are server-owned. Never trust a client replay of
    # crew_state, which could reset the session budget or forge a GREEN gate.
    out.pop("crew_state", None)
    out.pop("memory_scope", None)
    raw_project = str(out.get("project_id") or "").strip()
    if raw_project and str(api_key_identity or "").strip():
        out["memory_scope"] = _namespace_project_scope(api_key_identity, raw_project)
    sid = extract_session_id(header_value=session_header, zeus=out)
    if sid:
        sid = _namespace_session_id(api_key_identity, sid)
    elif tools_enabled:
        sid = _automatic_tool_session_id(
            api_key_identity=api_key_identity,
            messages=list(messages or []),
        )
    if sid:
        out["session_id"] = sid
    if not sid:
        return out, None
    try:
        state = await get_sticky(db, sid)
        leader = sticky_leader_hint(state)
        if leader and "sticky_leader" not in out:
            out["sticky_leader"] = leader
        # Clarifier multi-turn state lives in sticky phase_meta
        if state and isinstance(state.phase_meta, dict):
            clar = state.phase_meta.get("clarify")
            if isinstance(clar, dict) and "clarify_state" not in out:
                out["clarify_state"] = clar
            art = state.phase_meta.get("plan_artifact")
            if isinstance(art, dict) and art.get("content") and "plan_artifact" not in out:
                out["plan_artifact"] = art
            crew = state.phase_meta.get("crew")
            if isinstance(crew, dict):
                out["crew_state"] = crew
    except Exception:  # noqa: BLE001
        pass
    return out, sid


async def _observe_and_persist_sticky(
    db: AsyncSession,
    data: dict[str, Any],
    *,
    session_id: str | None,
) -> None:
    """Epic4 edge: metrics + sticky write after FusionResult is known."""
    from app.fusion import observe_request
    from app.fusion.session import atomic_merge_sticky
    from app.fusion.metrics import load_fusion_flags

    fr = data.get("_fusion_result")
    onestack = data.get("onestack") if isinstance(data.get("onestack"), dict) else {}
    path = getattr(fr, "path", None) or onestack.get("path") or ""
    phase = getattr(fr, "phase", None) or onestack.get("phase") or "unknown"
    routed_by = getattr(fr, "routed_by", None) or onestack.get("routed_by") or "unknown"
    escalate = getattr(fr, "escalate_from", None) or onestack.get("escalate_from")
    trace_id = getattr(fr, "trace_id", None) or onestack.get("trace_id")
    leader = getattr(fr, "leader", None) or onestack.get("leader")
    stack = onestack.get("stack") if isinstance(onestack.get("stack"), list) else None
    if not stack and isinstance(data.get("models"), list):
        stack = list(data["models"])
    try:
        observe_request(
            path=str(path),
            phase=str(phase),
            routed_by=str(routed_by),
            escalate_from=str(escalate) if escalate else None,
            trace_id=str(trace_id) if trace_id else None,
            leader=str(leader) if leader else None,
            model_ids=list(stack) if stack else None,
            baseline_id=load_fusion_flags().baseline_id,
        )
    except Exception:  # noqa: BLE001
        pass

    try:
        meta: dict[str, Any] = {"phase": phase, "routed_by": routed_by}
        incoming_crew = onestack.get("crew_state") or data.get("crew_state")
        # Preserve clarifier interview across turns (ask → confirm → plan → done)
        clar = onestack.get("clarify_state") or onestack.get("clarify")
        if isinstance(clar, dict):
            meta["clarify"] = clar
        elif isinstance(data.get("clarify_state"), dict):
            meta["clarify"] = data["clarify_state"]
        # omp-style plan artifact (sticky, not only chat text)
        art = onestack.get("plan_artifact") or data.get("plan_artifact")
        if (
            isinstance(art, dict)
            and art.get("content")
        ):
            meta["plan_artifact"] = {
                "version": max(1, min(10, int(art.get("version") or 1))),
                "kind": str(art.get("kind") or "crew_plan_digest")[:80],
                "content": str(art.get("content") or "")[:6000],
            }
        elif isinstance(clar, dict) and clar.get("dev_plan"):
            try:
                from app.fusion.plan_artifact import plan_artifact_from_clarify_state

                built = plan_artifact_from_clarify_state(clar)
                if built:
                    meta["plan_artifact"] = built
            except Exception:  # noqa: BLE001
                pass
        crew = incoming_crew
        if isinstance(crew, dict):
            meta["crew"] = crew
        budgets = (
            onestack.get("crew_budgets")
            if isinstance(onestack.get("crew_budgets"), dict)
            else {}
        )
        await atomic_merge_sticky(
            db,
            session_id,
            leader=str(leader) if leader else None,
            stack=list(stack) if stack else None,
            phase_meta=meta,
            spent_internal_branches=int(
                budgets.get("spent_internal_branches") or 0
            ),
        )
    except Exception:  # noqa: BLE001
        pass


def _sse_pack(
    *,
    cid: str,
    model: str,
    created: int,
    delta: dict[str, Any],
    finish: str | None = None,
) -> str:
    body = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"


def _sse_from_text(data: dict[str, Any], *, chunk_size: int = 48) -> list[str]:
    """Back-compat alias — prefer full completion (content + tool_calls)."""
    return _sse_from_completion(data, chunk_size=chunk_size)


def _sse_from_completion(data: dict[str, Any], *, chunk_size: int = 48) -> list[str]:
    """Fake-stream a buffered completion, including OpenAI tool_calls for OpenCode."""
    cid = data.get("id") or f"chatcmpl-{int(time.time())}"
    model = data.get("model") or "zeuscode"
    created = int(data.get("created") or time.time())
    choice = {}
    try:
        choice = (data.get("choices") or [{}])[0] or {}
    except (IndexError, TypeError):
        choice = {}
    msg = choice.get("message") or {}
    content = msg.get("content")
    if content is None:
        content = ""
    if not isinstance(content, str):
        content = str(content)
    tool_calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else None
    finish = "tool_calls" if tool_calls else (choice.get("finish_reason") or "stop")

    lines = [_sse_pack(cid=cid, model=model, created=created, delta={"role": "assistant"})]
    if content.strip():
        for i in range(0, len(content), chunk_size):
            lines.append(
                _sse_pack(
                    cid=cid,
                    model=model,
                    created=created,
                    delta={"content": content[i : i + chunk_size]},
                )
            )
    elif not tool_calls:
        content = "На связи. Напиши задачу."
        lines.append(
            _sse_pack(cid=cid, model=model, created=created, delta={"content": content})
        )
    if tool_calls:
        # Emit as one delta — OpenCode accumulates; avoids null-name chunk issues.
        lines.append(
            _sse_pack(
                cid=cid,
                model=model,
                created=created,
                delta={"tool_calls": tool_calls},
            )
        )
    lines.append(_sse_pack(cid=cid, model=model, created=created, delta={}, finish=finish))
    lines.append("data: [DONE]\n\n")
    return lines


async def _sse_stream(lines: list[str]) -> AsyncIterator[str]:
    for line in lines:
        yield line
        await asyncio.sleep(0)


def _fusion_result_from_data(data: dict[str, Any]) -> Any | None:
    """Prefer Execute→Bill FusionResult; never invent Path from token heuristics."""
    fr = data.get("_fusion_result")
    if fr is not None:
        return fr
    # JSON-shaped fallback (SSE / serialized)
    raw = data.get("fusion_result")
    if isinstance(raw, dict) and raw.get("path") and "branches" in raw:
        return raw
    onestack = data.get("onestack") or {}
    if isinstance(onestack, dict) and onestack.get("path") and onestack.get("branches"):
        return {
            "path": onestack.get("path"),
            "policy_path": onestack.get("policy_path"),
            "routed_by": onestack.get("routed_by"),
            "phase": onestack.get("phase"),
            "complexity": onestack.get("complexity"),
            "leader": onestack.get("leader"),
            "branches": onestack.get("branches"),
            "escalate_from": onestack.get("escalate_from"),
            "trace_id": onestack.get("trace_id"),
            "answer": onestack.get("answer_only") or "",
        }
    return None


def _branch_rows(fr: Any) -> list[dict[str, Any]]:
    branches = getattr(fr, "branches", None)
    if branches is None and isinstance(fr, dict):
        branches = fr.get("branches") or []
    rows: list[dict[str, Any]] = []
    for b in branches or []:
        if isinstance(b, dict):
            rows.append(b)
            continue
        prompt_tokens = int(getattr(b, "prompt_tokens", 0) or 0)
        cached_tokens = max(
            0, min(int(getattr(b, "cached_tokens", 0) or 0), prompt_tokens)
        )
        row = {
            "model": getattr(b, "model_id", None),
            "model_id": getattr(b, "model_id", None),
            "billable_state": getattr(b, "billable_state", "completed"),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": int(getattr(b, "completion_tokens", 0) or 0),
            "role": getattr(b, "role", "agent"),
        }
        if cached_tokens:
            row["cached_tokens"] = cached_tokens
            row["usage"] = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": int(getattr(b, "completion_tokens", 0) or 0),
                "cached_tokens": cached_tokens,
            }
        rows.append(row)
    return rows


def _cached_tokens(data: dict[str, Any]) -> int:
    """Cache hits for this response — per branch on the crew path, else usage."""
    fr = _fusion_result_from_data(data)
    if fr is not None:
        total = 0
        for b in _branch_rows(fr):
            if str(b.get("billable_state") or "completed") in (
                "cancelled_no_tokens",
                "disaster",
                "empty",
            ):
                continue
            usage = b.get("usage") if isinstance(b.get("usage"), dict) else {}
            try:
                total += int(usage.get("cached_tokens") or b.get("cached_tokens") or 0)
            except (TypeError, ValueError):
                continue
        if total:
            return total
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    try:
        return int(
            (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
            or usage.get("cached_tokens")
            or 0
        )
    except (TypeError, ValueError):
        return 0


def _is_fusion_completion(data: dict[str, Any]) -> bool:
    """Detect fusion payloads so Bill never takes the agents-only path (AD-14)."""
    if data.get("_fusion_result") is not None or data.get("fusion_result"):
        return True
    onestack = data.get("onestack") if isinstance(data.get("onestack"), dict) else {}
    if onestack.get("fusion_mode") is not None or onestack.get("stack_size") is not None:
        return True
    path = str(onestack.get("path") or "").upper()
    return path in ("FAST", "CASCADE", "RACE", "FULL")


def _is_disaster(data: dict[str, Any], fr: Any | None = None) -> bool:
    """TZ §5.2: disaster → no user charge."""
    if fr is None:
        fr = _fusion_result_from_data(data)
    if fr is not None:
        if bool(getattr(fr, "disaster", False)):
            return True
        if isinstance(fr, dict) and fr.get("disaster"):
            return True
        code = getattr(fr, "disaster_code", None) or (
            fr.get("disaster_code") if isinstance(fr, dict) else None
        )
        if code:
            return True
    onestack = data.get("onestack") if isinstance(data.get("onestack"), dict) else {}
    if onestack.get("disaster") or onestack.get("disaster_code"):
        return True
    err = data.get("error")
    if isinstance(err, dict) and err.get("type") == "fusion_disaster":
        return True
    return False


def _charge_amounts(data: dict[str, Any], bill_model: str) -> tuple[float, float, int, int]:
    """Bill from FusionResult branches when present (AD-8 / AD-14 / FR-19).

    ``cancelled_no_tokens`` → ₽0. Path is never inferred from token totals alone.
    Fusion completions never use the legacy ``onestack.agents``-only charge path.
    Disaster → ₽0 (TZ: за disaster деньги не списываются).
    """
    fr = _fusion_result_from_data(data)
    if _is_disaster(data, fr):
        return 0.0, 0.0, 0, 0
    if fr is not None:
        upstream_cost = 0.0
        charged = 0.0
        prompt = 0
        completion = 0
        for b in _branch_rows(fr):
            state = str(b.get("billable_state") or "completed")
            usage = b.get("usage") if isinstance(b.get("usage"), dict) else {}
            pt = int(b.get("prompt_tokens") or usage.get("prompt_tokens") or 0)
            ct = int(b.get("completion_tokens") or usage.get("completion_tokens") or 0)
            if state in ("cancelled_no_tokens", "disaster", "empty"):
                continue
            mid = b.get("model_id") or b.get("model") or bill_model
            prompt += pt
            completion += ct
            cached = int(
                usage.get("cached_tokens")
                or b.get("cached_tokens")
                or (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
                or 0
            )
            upstream_cost += estimate_upstream_usd(str(mid), pt, ct, cached_tokens=cached)
            charged += estimate_user_rub(str(mid), pt, ct, cached_tokens=cached)
        return upstream_cost, charged, prompt, completion

    usage = data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)

    # AD-14: fusion without FusionResult → disaster fallback on usage totals only.
    # Never charge via onestack.agents in parallel.
    if _is_fusion_completion(data):
        upstream_cost = estimate_upstream_usd(bill_model, prompt, completion)
        charged = estimate_user_rub(bill_model, prompt, completion)
        return upstream_cost, charged, prompt, completion

    onestack = data.get("onestack") or {}
    agents = onestack.get("agents") or []
    if agents:
        upstream_cost = 0.0
        charged = 0.0
        for a in agents:
            state = str(a.get("billable_state") or "")
            if state == "cancelled_no_tokens":
                continue
            mid = a.get("model") or bill_model
            pt = int(a.get("prompt_tokens") or 0)
            ct = int(a.get("completion_tokens") or 0)
            upstream_cost += estimate_upstream_usd(mid, pt, ct)
            charged += estimate_user_rub(mid, pt, ct)
        a_p = sum(
            int(a.get("prompt_tokens") or 0)
            for a in agents
            if str(a.get("billable_state") or "") != "cancelled_no_tokens"
        )
        a_c = sum(
            int(a.get("completion_tokens") or 0)
            for a in agents
            if str(a.get("billable_state") or "") != "cancelled_no_tokens"
        )
        if prompt + completion > a_p + a_c:
            upstream_cost += estimate_upstream_usd(
                bill_model, max(prompt - a_p, 0), max(completion - a_c, 0)
            )
            charged += estimate_user_rub(bill_model, max(prompt - a_p, 0), max(completion - a_c, 0))
    else:
        upstream_cost = estimate_upstream_usd(bill_model, prompt, completion)
        charged = estimate_user_rub(bill_model, prompt, completion)
    return upstream_cost, charged, prompt, completion


def _sync_onestack_from_fusion_result(data: dict[str, Any]) -> None:
    """Ensure Onestack Path fields come from FusionResult (never token heuristics)."""
    fr = _fusion_result_from_data(data)
    if fr is None:
        return
    onestack = data.get("onestack")
    if not isinstance(onestack, dict):
        onestack = {}
        data["onestack"] = onestack

    def _get(name: str) -> Any:
        if isinstance(fr, dict):
            return fr.get(name)
        return getattr(fr, name, None)

    for key in (
        "path",
        "policy_path",
        "escalate_from",
        "routed_by",
        "phase",
        "complexity",
        "leader",
        "trace_id",
    ):
        val = _get(key)
        if val is not None and key not in onestack:
            onestack[key] = val
        elif val is not None and key in ("path", "policy_path", "routed_by"):
            # Authoritative from FusionResult — do not keep invented Path
            onestack[key] = val
    branches = _branch_rows(fr)
    if branches:
        onestack["branches"] = branches


_EMPTY_FALLBACK = (
    "ZeusCode не получил ответ от модели (пустой upstream). "
    "Повтори запрос — при повторе система сменит маршрут."
)


def _ensure_non_empty_completion(data: dict[str, Any]) -> bool:
    """TZ: пустое наружу не уходит. Returns True if content was empty before fix."""
    try:
        choice = (data.get("choices") or [{}])[0] or {}
        msg = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        content = msg.get("content")
        tools = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else None
        text = content if isinstance(content, str) else ("" if content is None else str(content))
        if tools:
            choice["finish_reason"] = "tool_calls"
            return False
        if text.strip():
            return False
        # Structured disaster error already explains — still need non-empty body
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            fill = str(err.get("message"))
        else:
            fill = _EMPTY_FALLBACK
        if "choices" not in data or not data["choices"]:
            data["choices"] = [{"index": 0, "message": {"role": "assistant", "content": fill}, "finish_reason": "stop"}]
        else:
            data["choices"][0].setdefault("message", {"role": "assistant"})
            data["choices"][0]["message"]["content"] = fill
            data["choices"][0]["finish_reason"] = data["choices"][0].get("finish_reason") or "stop"
        data["_empty_guard"] = True
        return True
    except Exception:  # noqa: BLE001
        return False


async def _bill_and_enrich(
    *,
    db: AsyncSession,
    user: User,
    api_key: ApiKey,
    data: dict[str, Any],
    model: str,
    mode: str,
    bill_model: str,
) -> dict[str, Any]:
    _sync_onestack_from_fusion_result(data)
    was_empty = _ensure_non_empty_completion(data)
    disaster = _is_disaster(data)
    try:
        from app.fusion.metrics import note_response_emptiness, note_token_profile

        note_response_emptiness(empty=was_empty, disaster=disaster)
    except Exception:  # noqa: BLE001
        pass
    upstream_cost, charged, prompt, completion = _charge_amounts(data, bill_model)
    try:
        from app.fusion.metrics import note_token_profile

        note_token_profile(
            prompt_tokens=prompt,
            completion_tokens=completion,
            cached_tokens=_cached_tokens(data),
        )
    except Exception:  # noqa: BLE001
        pass

    if user.balance_usd < charged:
        raise HTTPException(402, f"Недостаточно средств (~{charged:.2f} ₽)")

    budget = float(api_key.budget_rub or 0)
    spent = float(api_key.spent_rub or 0)
    if budget > 0 and spent + charged > budget:
        left = max(0.0, budget - spent)
        raise HTTPException(
            402,
            f"Лимит ключа исчерпан (осталось ~{left:.2f} ₽ из {budget:.0f} ₽). "
            "Подними бюджет ключа в кабинете или создай новый.",
        )

    api_key.spent_rub = round(spent + charged, 8)
    user.balance_usd = round(float(user.balance_usd or 0) - charged, 8)
    db.add(
        UsageLog(
            user_id=user.id,
            api_key_id=api_key.id,
            model=data.get("model") or model,
            mode=mode,
            prompt_tokens=prompt,
            completion_tokens=completion,
            cost_upstream_usd=upstream_cost,
            cost_user_usd=charged,
            meta=str((data.get("onestack") or {})),
        )
    )
    await db.commit()

    from app.routers.billing import alert_payload, month_spent_rub

    month_spent = await month_spent_rub(db, user.id)
    alerts = alert_payload(user, month_spent)
    onestack = data.get("onestack") if isinstance(data.get("onestack"), dict) else {}
    data["onestack_billing"] = {
        "currency": "RUB",
        "charged_rub": round(charged, 4),
        "markup": settings.MARKUP,
        "balance_left_rub": round(float(user.balance_usd or 0), 4),
        "key_spent_rub": round(float(api_key.spent_rub or 0), 4),
        "key_budget_rub": round(budget, 2),
        "path": onestack.get("path"),
        "policy_path": onestack.get("policy_path"),
        "routed_by": onestack.get("routed_by"),
        "trace_id": onestack.get("trace_id"),
        "alerts": {
            "low_balance": alerts["low_balance_triggered"],
            "monthly_budget": alerts["monthly_budget_triggered"],
            "monthly_budget_warning": alerts["monthly_budget_warning"],
        },
    }
    return data


async def _fusion_live_sse(
    *,
    messages: list[dict[str, Any]],
    user_id: int,
    api_key_id: int,
    key_prefix: str = "",
    model: str,
    panel: list[str] | None,
    judge: str | None,
    zeus: dict[str, Any] | None,
    session_id: str | None = None,
) -> AsyncIterator[str]:
    """Live SSE for Cursor.

    Full mode: brief unique progress frame (no repeating heartbeats),
    then the final answer. Keepalives are SSE comments only.
    Disable with zeus.thinking=false.
    """
    from app.fusion import iter_fusion

    # Brief thinking ON by default for full stack; opt-out via zeus.thinking=false
    want_thinking = True
    if isinstance(zeus, dict) and "thinking" in zeus:
        want_thinking = bool(zeus.get("thinking"))

    zeus_live = dict(zeus) if isinstance(zeus, dict) else {}
    zeus_live["thinking"] = want_thinking
    if session_id:
        zeus_live.setdefault("session_id", session_id)

    cid = f"chatcmpl-fusion-{int(time.time())}"
    created = int(time.time())
    timer = RequestTimer()

    def pack(delta: dict[str, Any], finish: str | None = None) -> str:
        return _sse_pack(cid=cid, model="zeuscode", created=created, delta=delta, finish=finish)

    yield pack({"role": "assistant"})

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    data: dict[str, Any] | None = None
    err_payload: str | None = None
    err_status: int = 500
    got_answer = False
    # Story 3.4: client disconnect / abort → Soft-Stop unfinished branches
    cancel_event = asyncio.Event()

    async def producer() -> None:
        nonlocal data, err_payload, err_status
        try:
            async with SessionLocal() as db:
                user = await db.get(User, user_id)
                api_key = await db.get(ApiKey, api_key_id)
                if not user or not api_key:
                    raise HTTPException(401, "Auth lost")

                async for ev in iter_fusion(
                    messages=messages,
                    user=user,
                    models=panel,
                    judge=judge,
                    model_id=model,
                    zeus=zeus_live,
                    show_thinking=want_thinking,
                    cancel_event=cancel_event,
                ):
                    kind = ev.get("kind")
                    if kind in ("think", "answer"):
                        await queue.put(ev)
                    elif kind == "done":
                        data = ev["data"]

                if not data:
                    raise HTTPException(502, "ZeusCode: пустой результат")

                await _observe_and_persist_sticky(db, data, session_id=session_id)

                # Close user-visible stream before slow billing
                await queue.put({"kind": "_prebill"})
                bill_model = data.get("_bill_model") or settings.DEFAULT_MODEL
                await _bill_and_enrich(
                    db=db,
                    user=user,
                    api_key=api_key,
                    data=data,
                    model=model,
                    mode="fusion",
                    bill_model=bill_model,
                )
                await _log_chat(
                    db,
                    event="chat_done",
                    user=user,
                    api_key=api_key,
                    model=model,
                    stream=True,
                    session_id=session_id,
                    messages=messages,
                    data=data,
                    status_code=200,
                    latency_ms=timer.ms(),
                    meta={"mode": "fusion"},
                )
        except HTTPException as e:
            err_status = int(e.status_code or 500)
            err_payload = json.dumps(
                {"error": {"message": e.detail, "type": "zeus_error"}},
                ensure_ascii=False,
            )
            try:
                async with SessionLocal() as db:
                    await _log_chat(
                        db,
                        event="chat_error",
                        user_id=user_id,
                        api_key_id=api_key_id,
                        key_prefix=key_prefix,
                        model=model,
                        stream=True,
                        session_id=session_id,
                        messages=messages,
                        status_code=err_status,
                        latency_ms=timer.ms(),
                        error=str(e.detail)[:800],
                        meta={"mode": "fusion"},
                    )
            except Exception:  # noqa: BLE001
                pass
        except Exception as e:  # noqa: BLE001
            err_status = 500
            err_payload = json.dumps(
                {"error": {"message": str(e)[:400], "type": "zeus_error"}},
                ensure_ascii=False,
            )
            try:
                async with SessionLocal() as db:
                    await _log_chat(
                        db,
                        event="chat_error",
                        user_id=user_id,
                        api_key_id=api_key_id,
                        key_prefix=key_prefix,
                        model=model,
                        stream=True,
                        session_id=session_id,
                        messages=messages,
                        status_code=500,
                        latency_ms=timer.ms(),
                        error=str(e)[:800],
                        meta={"mode": "fusion"},
                    )
            except Exception:  # noqa: BLE001
                pass
        finally:
            await queue.put(None)

    task = asyncio.create_task(producer())
    try:
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=8.0)
            except asyncio.TimeoutError:
                if not got_answer:
                    yield ": keepalive\n\n"
                continue

            if ev is None:
                break

            kind = ev.get("kind")
            if kind == "_prebill":
                yield pack({}, finish="stop")
                yield "data: [DONE]\n\n"
                while True:
                    rest = await queue.get()
                    if rest is None:
                        break
                return

            text = ev.get("text") or ""
            if kind == "answer":
                got_answer = True
                if not text.strip():
                    text = "Привет! На связи. Напиши задачу — отвечу."
                # Auto free-host HTML sites/apps + Zeus badge
                try:
                    from app.publish import enrich_answer_with_publish

                    text = enrich_answer_with_publish(text)
                except Exception:
                    pass
            if kind == "think" and not want_thinking:
                continue
            if not text and kind != "think":
                continue
            # Emit think lines whole (pretty frame); answer in larger chunks
            if kind == "think":
                yield pack({"content": text})
                await asyncio.sleep(0)
                continue
            step = 64
            for i in range(0, len(text), step):
                chunk = text[i : i + step]
                if not chunk:
                    continue
                yield pack({"content": chunk})
                await asyncio.sleep(0)
    finally:
        cancel_event.set()
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    if err_payload:
        try:
            msg = json.loads(err_payload).get("error", {}).get("message") or err_payload
        except Exception:
            msg = err_payload
        visible = f"⚠️ Zeus: {str(msg)[:500]}"
        for i in range(0, len(visible), 48):
            yield pack({"content": visible[i : i + 48]})
        yield pack({}, finish="stop")
        yield "data: [DONE]\n\n"
        return

    yield pack({}, finish="stop")
    yield "data: [DONE]\n\n"


@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionIn,
    request: Request,
    auth: tuple[User, ApiKey] = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
    x_zeus_session_id: str | None = Header(default=None, alias="X-Zeus-Session-Id"),
    x_zeus_client: str | None = Header(default=None, alias="X-Zeus-Client"),
):
    user, api_key = auth
    timer = RequestTimer()
    messages = [m.model_dump(exclude_none=True) for m in body.messages]
    from app.client_hands import apply_client_hands_policy, detect_external_coding_client

    _client = detect_external_coding_client(
        user_agent=request.headers.get("user-agent"),
        client_header=x_zeus_client,
        messages=messages,
    )
    from app.claude_gateway import resolve_model_id

    model = resolve_model_id(body.model or settings.DEFAULT_MODEL)
    from app.fusion import is_fusion_model as _is_fusion_early

    if _client or _is_fusion_early(model):
        messages = apply_client_hands_policy(messages, client=_client or "zeuscode")

    wants_tools = request_wants_tools(body.tools)

    if user.balance_usd <= 0:
        await _log_chat(
            db,
            event="chat_error",
            user=user,
            api_key=api_key,
            model=model,
            stream=body.stream,
            messages=messages,
            status_code=402,
            latency_ms=timer.ms(),
            error="Insufficient balance",
        )
        raise HTTPException(402, "Insufficient balance")

    assert_model_allowed(user, model)

    import logging

    _log = logging.getLogger("zeus.chat")
    _ulog = prompt_preview_from_messages(messages, limit=80)
    _log.info(
        "chat user=%s key=%s model=%s stream=%s msg=%r",
        user.id,
        api_key.key_prefix,
        model,
        body.stream,
        _ulog,
    )
    await _log_chat(
        db,
        event="chat_start",
        user=user,
        api_key=api_key,
        model=model,
        stream=body.stream,
        messages=messages,
        status_code=0,
        latency_ms=0,
        meta={"msg_count": len(messages)},
    )

    from app.fusion import apply_user_fusion_pref, is_fusion_model, run_fusion

    # Live thinking SSE is text-only. With tools: buffer crew → fake-stream tool_calls.
    if is_fusion_model(model) and body.stream and not wants_tools:
        zeus = body.zeus if isinstance(body.zeus, dict) else {}
        panel = body.models or zeus.get("models")
        zeus, panel = apply_user_fusion_pref(user, zeus=zeus, models=list(panel) if panel else None)
        zeus.setdefault("user_id", user.id)
        from app.fusion.metrics import RateLimitExceeded, check_rate_limit

        try:
            check_rate_limit()
        except RateLimitExceeded as e:
            await _log_chat(
                db,
                event="chat_error",
                user=user,
                api_key=api_key,
                model=model,
                stream=True,
                messages=messages,
                status_code=429,
                latency_ms=timer.ms(),
                error=str(e)[:800],
            )
            raise HTTPException(429, str(e)) from e
        zeus, sid = await _apply_sticky_hint(
            db,
            zeus,
            session_header=x_zeus_session_id,
            api_key_identity=str(api_key.id),
            messages=messages,
            tools_enabled=False,
        )
        judge = zeus.get("judge") if isinstance(zeus, dict) else None
        return StreamingResponse(
            _fusion_live_sse(
                messages=messages,
                user_id=user.id,
                api_key_id=api_key.id,
                key_prefix=api_key.key_prefix or "",
                model=model,
                panel=list(panel) if panel else None,
                judge=str(judge) if judge else None,
                zeus=zeus if isinstance(zeus, dict) else None,
                session_id=sid,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    mode = "solo"
    bill_model = model
    sid: str | None = None
    try:
        studio_ids = {
            "ultra-mode",
            "ultra",
            "onestack-ultra",
            "studio-light",
            "studio-standard",
            "studio-ultra",
            "studio-premium",
        }
        if is_fusion_model(model):
            zeus = body.zeus or {}
            panel = body.models or (zeus.get("models") if isinstance(zeus, dict) else None)
            zeus, panel = apply_user_fusion_pref(
                user, zeus=zeus if isinstance(zeus, dict) else {}, models=list(panel) if panel else None
            )
            if isinstance(zeus, dict):
                zeus.setdefault("user_id", user.id)
            from app.fusion.metrics import RateLimitExceeded, check_rate_limit

            try:
                check_rate_limit()
            except RateLimitExceeded as e:
                raise HTTPException(429, str(e)) from e
            zeus, sid = await _apply_sticky_hint(
                db,
                zeus,
                session_header=x_zeus_session_id,
                api_key_identity=str(api_key.id),
                messages=messages,
                tools_enabled=wants_tools,
            )
            judge = zeus.get("judge") if isinstance(zeus, dict) else None
            data = await run_fusion(
                messages=messages,
                user=user,
                models=list(panel) if panel else None,
                judge=str(judge) if judge else None,
                model_id=model,
                zeus=zeus if isinstance(zeus, dict) else None,
                tools=body.tools if wants_tools else None,
                tool_choice=body.tool_choice if wants_tools else None,
            )
            await _observe_and_persist_sticky(db, data, session_id=sid)
            if wants_tools:
                emitted_call_id = _first_emitted_tool_call_id(data)
                if emitted_call_id:
                    alias_sid = _tool_call_alias_session_id(
                        str(api_key.id), emitted_call_id
                    )
                    if alias_sid != sid:
                        await _observe_and_persist_sticky(
                            db, data, session_id=alias_sid
                        )
            mode = "fusion"
            bill_model = data.get("_bill_model") or settings.DEFAULT_MODEL
        elif model in studio_ids:
            raise HTTPException(
                410,
                "Studio / ultra-mode сняты. Используй model=zeuscode (ZeusCode) "
                "или обычную модель из каталога.",
            )
        else:
            meta = get_model(model)
            if meta and not meta.get("ready"):
                raise HTTPException(
                    400,
                    f"Модель {model} в каталоге, но ещё не подключена. Выбери Gemini / Claude / zeuscode.",
                )
            from app.fusion import sanitize_messages

            if wants_tools:
                agent_msgs = prepare_agent_messages(messages)
            else:
                # Cursor Agent without native tools: flatten tool protocol (legacy).
                agent_msgs = sanitize_messages(messages)
            data = await upstream.chat_completions(
                model=model,
                messages=agent_msgs,
                stream=False,
                max_tokens=body.max_tokens,
                temperature=body.temperature,
                tools=body.tools if wants_tools else None,
                tool_choice=body.tool_choice if wants_tools else None,
            )
            mode = "solo"
            bill_model = model if get_model(model) else settings.DEFAULT_MODEL
    except HTTPException as e:
        await _log_chat(
            db,
            event="chat_error",
            user=user,
            api_key=api_key,
            model=model,
            stream=body.stream,
            session_id=sid,
            messages=messages,
            status_code=int(e.status_code or 500),
            latency_ms=timer.ms(),
            error=str(e.detail)[:800],
            meta={"mode": mode},
        )
        raise
    except upstream.UpstreamError as e:
        if e.status_code == 429 or "RATE LIMIT" in str(e).upper():
            _log.error("chat.upstream_rate_limit model=%s err=%s", model, e)
        else:
            _log.warning("chat.upstream_error model=%s status=%s err=%s", model, e.status_code, e)
        await _log_chat(
            db,
            event="chat_error",
            user=user,
            api_key=api_key,
            model=model,
            stream=body.stream,
            session_id=sid,
            messages=messages,
            status_code=int(e.status_code or 502),
            latency_ms=timer.ms(),
            error=str(e)[:800],
            meta={"mode": mode},
        )
        raise HTTPException(e.status_code, str(e)) from e
    except Exception as e:  # noqa: BLE001
        await _log_chat(
            db,
            event="chat_error",
            user=user,
            api_key=api_key,
            model=model,
            stream=body.stream,
            session_id=sid,
            messages=messages,
            status_code=500,
            latency_ms=timer.ms(),
            error=str(e)[:800],
            meta={"mode": mode},
        )
        raise

    if wants_tools and isinstance(data, dict):
        data = repair_completion_tool_calls(data, body.tools)

    data = await _bill_and_enrich(
        db=db,
        user=user,
        api_key=api_key,
        data=data,
        model=model,
        mode=mode,
        bill_model=bill_model,
    )
    await _log_chat(
        db,
        event="chat_done",
        user=user,
        api_key=api_key,
        model=model,
        stream=body.stream,
        session_id=sid,
        messages=messages,
        data=data,
        status_code=200,
        latency_ms=timer.ms(),
        meta={"mode": mode},
    )

    # Auto-publish HTML sites from non-stream / buffered answers
    try:
        from app.publish import enrich_answer_with_publish

        msg = ((data.get("choices") or [{}])[0].get("message") or {})
        content = msg.get("content")
        if isinstance(content, str) and content:
            new_c = enrich_answer_with_publish(content)
            if new_c != content:
                data["choices"][0]["message"]["content"] = new_c
                if isinstance(data.get("onestack"), dict):
                    data["onestack"]["answer_only"] = new_c
    except Exception:
        pass

    if body.stream:
        return StreamingResponse(
            _sse_stream(_sse_from_completion(data)),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    return data


class ResponsesCreateIn(BaseModel):
    """Minimal OpenAI Responses API body (Codex CLI / OmniRoute)."""

    model_config = ConfigDict(extra="allow")

    model: str = Field(default="gemini-3.1-pro")
    input: Any = None
    instructions: str | None = None
    stream: bool = False
    temperature: float | None = None
    max_output_tokens: int | None = None
    max_tokens: int | None = None
    tools: list[Any] | None = None
    tool_choice: Any | None = None


@router.post("/v1/responses")
async def create_response(
    body: ResponsesCreateIn,
    request: Request,
    auth: tuple[User, ApiKey] = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
    x_zeus_session_id: str | None = Header(default=None, alias="X-Zeus-Session-Id"),
    x_zeus_client: str | None = Header(default=None, alias="X-Zeus-Client"),
):
    """
    Codex CLI (wire_api=responses) + OmniRoute bridge.
    Internally runs Chat Completions, returns Responses-shaped JSON / SSE.
    """
    from app.responses_compat import (
        chat_completion_to_response,
        response_to_sse_events,
        responses_input_to_messages,
    )

    messages = responses_input_to_messages(body.input, instructions=body.instructions)
    chat_body = ChatCompletionIn(
        model=body.model or "gemini-3.1-pro",
        messages=[ChatMessage(**m) for m in messages],
        stream=False,  # always resolve fully, then optionally fake SSE
        temperature=body.temperature,
        max_tokens=body.max_output_tokens or body.max_tokens,
        tools=body.tools,
        tool_choice=body.tool_choice,
    )
    result = await chat_completions(
        chat_body,
        request,
        auth=auth,
        db=db,
        x_zeus_session_id=x_zeus_session_id,
        x_zeus_client=x_zeus_client,
    )
    if isinstance(result, StreamingResponse):
        # Fusion stream path shouldn't run with stream=False; safety net
        raise HTTPException(
            400,
            "Responses: выбери обычную модель (gemini-3.1-pro / claude-opus-4-8), "
            "не zeuscode со stream.",
        )
    if not isinstance(result, dict):
        raise HTTPException(502, "Responses bridge: unexpected chat result")
    resp = chat_completion_to_response(result, model=chat_body.model)
    if body.stream:
        return StreamingResponse(
            _sse_stream(response_to_sse_events(resp)),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    return resp


class AnthropicMessagesIn(BaseModel):
    """Anthropic Messages API body (Claude Code)."""

    model_config = ConfigDict(extra="allow")

    model: str = Field(default="claude-sonnet-4-6")
    messages: list[Any] = Field(default_factory=list)
    system: Any = None
    max_tokens: int = 4096
    stream: bool = False
    temperature: float | None = None
    tools: list[Any] | None = None
    tool_choice: Any | None = None


@router.post("/v1/messages")
async def anthropic_messages(
    body: AnthropicMessagesIn,
    request: Request,
    auth: tuple[User, ApiKey] = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
    x_zeus_session_id: str | None = Header(default=None, alias="X-Zeus-Session-Id"),
    x_zeus_client: str | None = Header(default=None, alias="X-Zeus-Client"),
):
    """
    Claude Code: ANTHROPIC_BASE_URL=https://zeuscode.ru (без /v1)
    → POST /v1/messages. Ключ: ANTHROPIC_AUTH_TOKEN (x-api-key) или Bearer.
    """
    from app.anthropic_compat import (
        anthropic_to_openai_messages,
        anthropic_to_sse_events,
        anthropic_tools_to_openai,
        chat_completion_to_anthropic,
    )

    from app.claude_gateway import resolve_model_id
    from app.openai_tools import repair_completion_tool_calls, request_wants_tools

    messages = anthropic_to_openai_messages(body.messages, system=body.system)
    tools_oai = anthropic_tools_to_openai(body.tools)
    wants_tools = request_wants_tools(tools_oai)
    chat_body = ChatCompletionIn(
        model=resolve_model_id(body.model or "zeuscode"),
        messages=[ChatMessage(**m) for m in messages],
        stream=False,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        tools=tools_oai if wants_tools else None,
        tool_choice=body.tool_choice if wants_tools else None,
    )
    result = await chat_completions(
        chat_body,
        request,
        auth=auth,
        db=db,
        x_zeus_session_id=x_zeus_session_id,
        x_zeus_client=x_zeus_client,
    )
    if isinstance(result, StreamingResponse):
        raise HTTPException(
            400,
            "Messages: выбери обычную модель (claude-sonnet-4-6 / claude-opus-4-8), "
            "не zeuscode со stream.",
        )
    if not isinstance(result, dict):
        raise HTTPException(502, "Anthropic bridge: unexpected chat result")
    if wants_tools:
        result = repair_completion_tool_calls(result, tools_oai)
    msg = chat_completion_to_anthropic(result, model=chat_body.model)
    if body.stream:
        return StreamingResponse(
            _sse_stream(anthropic_to_sse_events(msg)),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    return msg
