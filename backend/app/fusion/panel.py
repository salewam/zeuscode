"""Path executors: RACE / FULL, Brief, Soft-Stop, prompt adaptation (Epic 3)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .judge import JudgeAnalysis, rank_then_fuse_plan, run_structured_judge
from .types import BillableState, BranchUsage, ComplexityBand, FusionResult, PathName
from .verify import (
    AspectBundle,
    aspects_block_tau_exit,
    near_duplicate_among,
    run_aspect_verifiers_v1,
)

# Role presets (B10) — presence required even if some adapters ignore temp.
ROLE_TEMPERATURE: dict[str, float] = {"A": 0.2, "B": 0.55, "C": 0.85}
def _agent_max_tokens(*, path: str | None = None) -> int:
    """FULL/RACE keep high ceiling; CASCADE/FAST use tighter small cap."""
    try:
        from app.config import get_settings

        settings = get_settings()
        full = int(getattr(settings, "FUSION_AGENT_MAX_TOKENS", 65536) or 65536)
        small = int(getattr(settings, "FUSION_SMALL_MAX_TOKENS", 8192) or 8192)
    except Exception:  # noqa: BLE001
        full, small = 65536, 8192
    p = (path or "").strip().upper()
    if p in ("CASCADE", "FAST"):
        return max(1024, min(full, small))
    return max(1024, full)


# Kept for imports/tests; values resolved at call-time via _agent_max_tokens().
ROLE_MAX_TOKENS: dict[str, int] = {"A": 65536, "B": 65536, "C": 65536}

# Prompt adaptation v1 — system/hint layer only (FR-32). Separate from Soft-Stop.
_FAMILY_HINTS: dict[str, str] = {
    "claude": (
        "[Zeus adapt] Prefer precise structured answers and concrete code/diffs; "
        "avoid long preambles. Do not change the user's requirements."
    ),
    "gemini": (
        "[Zeus adapt] Lead with usable code or steps; keep rationale short. "
        "Do not add or remove user requirements."
    ),
    "deepseek": (
        "[Zeus adapt] Focus on correct, complete code and clear fixes. "
        "Do not invent extra product goals."
    ),
    "openai": (
        "[Zeus adapt] Deliver a complete actionable answer. "
        "Preserve the user's intent exactly."
    ),
    "gpt": (
        "[Zeus adapt] Deliver a complete actionable answer. "
        "Preserve the user's intent exactly."
    ),
    "grok": (
        "[Zeus adapt] Be direct and technical; ship a usable answer. "
        "Do not alter requirements."
    ),
}

_ERROR_RE = re.compile(
    r"(?i)(traceback|exception|error:|typeerror|referenceerror|syntaxerror|"
    r"failed|ошибка|исключение)"
)

UpstreamCall = Callable[..., Awaitable[dict[str, Any]]]
MiniVerifyFn = Callable[..., Awaitable[Any]]
CancelFlag = asyncio.Event | None


@dataclass
class LiveBranch:
    model_id: str
    role: str  # A|B|C|cheap|strong
    text: str = ""
    ok: bool = False
    billable_state: BillableState = "cancelled_no_tokens"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    error: str | None = None
    verifier_confidence: float = 0.0
    verifier_pass: bool = False
    verifier_degraded: bool = False
    is_leader: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecuteOutcome:
    path: PathName
    policy_path: PathName
    routed_by: str
    answer: str
    leader: str | None
    branches: list[BranchUsage]
    live: list[LiveBranch] = field(default_factory=list)
    escalate_from: PathName | str | None = None
    phase: str = "execute"
    complexity: ComplexityBand | str = "med"
    trace_id: str = ""
    early_exit: str | None = None
    disaster: bool = False
    disaster_code: str | None = None
    aspects: AspectBundle | None = None
    judge: JudgeAnalysis | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.trace_id:
            self.trace_id = uuid.uuid4().hex[:16]


class PanelDiversityError(ValueError):
    """Three models from the same family without ops exception."""


def model_family(model_id: str) -> str:
    mid = (model_id or "").strip().lower()
    if not mid:
        return "unknown"
    try:
        from app.catalog import get_model

        row = get_model(mid)
        if row and row.get("family"):
            fam = str(row["family"]).strip().lower()
            if fam and fam not in ("fusion", "ultra", "studio"):
                return fam
        if row and row.get("provider"):
            return str(row["provider"]).strip().lower()
    except Exception:  # noqa: BLE001
        pass
    if mid.startswith("claude") or "anthropic" in mid:
        return "claude"
    if mid.startswith("gemini") or mid.startswith("gemma"):
        return "gemini"
    if mid.startswith("deepseek"):
        return "deepseek"
    if mid.startswith("gpt") or mid.startswith("o1") or mid.startswith("o3"):
        return "openai"
    if mid.startswith("grok"):
        return "grok"
    head = mid.split("-", 1)[0]
    return head or "unknown"


def assert_panel_diversity(
    panel: list[str],
    *,
    ops_exception: bool = False,
) -> dict[str, str]:
    """Forbid 3× same model_family unless ops exception (FR-10)."""
    families = {m: model_family(m) for m in panel}
    if ops_exception or len(panel) < 3:
        return families
    vals = list(families.values())
    if len(vals) == 3 and len(set(vals)) == 1:
        raise PanelDiversityError(
            f"Panel diversity violated: all three models are family={vals[0]}"
        )
    return families


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


def extract_brief_parts(messages: list[dict[str, Any]], user_q: str) -> dict[str, str]:
    """Brief = last_assistant + errors + goal (AD-4 / FR-22)."""
    last_assistant = ""
    errors: list[str] = []
    for m in messages or []:
        role = (m.get("role") or "").strip().lower()
        text = _plain(m.get("content")).strip()
        if not text:
            continue
        if role == "assistant":
            last_assistant = text
        if _ERROR_RE.search(text):
            errors.append(text[:1200])
    goal = (user_q or "").strip()
    if len(goal) > 2800:
        goal = goal[:2400] + "\n…\n" + goal[-350:]
    err_blob = "\n---\n".join(errors[-3:]) if errors else ""
    return {
        "last_assistant": last_assistant[-2500:] if last_assistant else "",
        "errors": err_blob,
        "goal": goal,
    }


def build_satellite_brief(
    messages: list[dict[str, Any]],
    user_q: str,
    *,
    family: str | None = None,
) -> list[dict[str, Any]]:
    """Satellite messages: Brief only — never full Cursor dump."""
    parts = extract_brief_parts(messages, user_q)
    body = (
        "Ты satellite-ветка Zeus Fusion. Полный IDE-контекст только у Leader.\n"
        "Дай сильную альтернативу по Brief (подход / код / правка). Без мета-воды.\n\n"
        f"## Goal\n{parts['goal'] or '(empty)'}\n"
    )
    if parts["last_assistant"]:
        body += f"\n## Last assistant\n{parts['last_assistant']}\n"
    if parts["errors"]:
        body += f"\n## Errors\n{parts['errors']}\n"
    out: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": "Zeus Fusion satellite. Follow the Brief; do not invent extra goals.",
        },
        {"role": "user", "content": body},
    ]
    if family:
        out = adapt_prompt_for_family(out, family, role="satellite")
    return out


def adapt_prompt_for_family(
    messages: list[dict[str, Any]],
    family: str,
    *,
    role: str = "leader",
) -> list[dict[str, Any]]:
    """FR-32: rewrite limited to system/hint layer; user content untouched."""
    fam = (family or "").strip().lower()
    hint = _FAMILY_HINTS.get(fam)
    if not hint:
        # Unknown family — no-op (still a valid adaptation pass).
        return [dict(m) for m in messages]

    out: list[dict[str, Any]] = []
    system_touched = False
    role_tag = f"role={role}"
    for m in messages:
        item = dict(m)
        if (item.get("role") or "").strip().lower() == "system":
            base = _plain(item.get("content")).rstrip()
            # Idempotent: don't stack identical adapt hints.
            if "[Zeus adapt]" not in base:
                item["content"] = (base + "\n\n" + hint + f" ({role_tag})").strip()
            system_touched = True
        out.append(item)
    if not system_touched:
        out.insert(0, {"role": "system", "content": f"{hint} ({role_tag})"})
    return out


def billable_for_branch(
    *,
    ok: bool,
    prompt_tokens: int,
    completion_tokens: int,
    text: str,
    cancelled: bool,
    partial: bool = False,
) -> BillableState:
    tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)
    if cancelled:
        return "cancelled_with_usage" if tokens > 0 else "cancelled_no_tokens"
    if ok and (text or "").strip() and not partial:
        return "completed"
    if (text or "").strip() or tokens > 0:
        return "partial_stream"
    return "cancelled_no_tokens"


def soft_stop_pick_by_power(
    branches: list[LiveBranch],
    *,
    leader_id: str | None = None,
) -> LiveBranch | None:
    """AD-25 Soft-Stop: max power_score among post-merge candidates; tie → latest."""
    from app.fusion.model_power import power_score

    eligible = [
        b
        for b in branches
        if b.billable_state in ("completed", "partial_stream")
        and (b.text or "").strip()
    ]
    if not eligible:
        for b in branches:
            if leader_id and b.model_id == leader_id and (b.text or "").strip():
                return b
        return None
    best: LiveBranch | None = None
    best_score = -1
    for b in eligible:
        sc = power_score(b.model_id)
        if sc >= best_score:
            best_score = sc
            best = b
    return best


def soft_stop_pick(
    branches: list[LiveBranch],
    *,
    leader_id: str | None = None,
) -> LiveBranch | None:
    """FR-14 order: verifier confidence → first-complete → Leader-partial."""
    eligible = [
        b
        for b in branches
        if b.billable_state in ("completed", "partial_stream")
        and ((b.text or "").strip() or b.prompt_tokens or b.completion_tokens)
    ]
    if not eligible:
        # Leader-partial even if only cancelled_with_usage + text crumbs
        for b in branches:
            if leader_id and b.model_id == leader_id and (b.text or "").strip():
                return b
        return None

    completedish = [
        b for b in eligible if b.billable_state in ("completed", "partial_stream")
    ]
    if completedish:
        best = max(completedish, key=lambda b: float(b.verifier_confidence or 0.0))
        if any(b.verifier_confidence > 0 for b in completedish):
            return best
        # first-complete: lowest latency among completed
        done = [b for b in completedish if b.billable_state == "completed"]
        if done:
            return min(done, key=lambda b: (b.latency_s, 0 if b.is_leader else 1))
        return min(completedish, key=lambda b: (b.latency_s, 0 if b.is_leader else 1))

    if leader_id:
        for b in branches:
            if b.model_id == leader_id and (b.text or "").strip():
                return b
    return eligible[0]


def live_to_usage(b: LiveBranch, *, role: str | None = None) -> BranchUsage:
    return BranchUsage(
        model_id=b.model_id,
        billable_state=b.billable_state,
        prompt_tokens=int(b.prompt_tokens or 0),
        completion_tokens=int(b.completion_tokens or 0),
        role=role or ("agent" if b.role in {"A", "B", "C", "cheap", "strong"} else b.role),
        meta={
            "panel_role": b.role,
            "latency_s": b.latency_s,
            "ok": b.ok,
            "is_leader": b.is_leader,
            "verifier_confidence": b.verifier_confidence,
            "error": b.error,
            **(b.meta or {}),
        },
    )


def _complexity_at_least_med(complexity: str) -> bool:
    return str(complexity or "").lower() in {"med", "heavy"}


def race_both_fail_terminal(
    *,
    product_mode: str,
    complexity: str,
    branches: list[LiveBranch],
    leader_id: str | None,
    policy_path: PathName = "RACE",
) -> ExecuteOutcome:
    """FR-9 both-fail map."""
    mode = (product_mode or "power").lower()
    if mode in {"power", "custom"} and _complexity_at_least_med(complexity):
        return ExecuteOutcome(
            path="FULL",
            policy_path=policy_path,
            routed_by="race_escalate_full",
            escalate_from="RACE",
            answer="",
            leader=leader_id,
            branches=[live_to_usage(b) for b in branches],
            live=branches,
            complexity=complexity,  # type: ignore[arg-type]
            meta={"terminal": "race_escalate_full"},
        )

    pick = soft_stop_pick_by_power(branches, leader_id=leader_id)
    if pick is not None and (pick.text or "").strip():
        return ExecuteOutcome(
            path="RACE",
            policy_path=policy_path,
            routed_by="race_soft_stop",
            answer=pick.text.strip(),
            leader=leader_id,
            branches=[live_to_usage(b) for b in branches],
            live=branches,
            complexity=complexity,  # type: ignore[arg-type]
            early_exit="soft_stop",
            meta={"terminal": "race_soft_stop", "picked": pick.model_id},
        )

    return ExecuteOutcome(
        path="RACE",
        policy_path=policy_path,
        routed_by="race_disaster",
        answer="",
        leader=leader_id,
        branches=[live_to_usage(b) for b in branches],
        live=branches,
        complexity=complexity,  # type: ignore[arg-type]
        disaster=True,
        disaster_code="race_disaster",
        meta={"terminal": "race_disaster"},
    )


def _extract_tool_calls(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    try:
        msg = ((data or {}).get("choices") or [{}])[0].get("message") or {}
        tcs = msg.get("tool_calls")
        return list(tcs) if isinstance(tcs, list) else []
    except (IndexError, TypeError, AttributeError):
        return []


async def _default_upstream(
    model: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tools: list[Any] | None = None,
    tool_choice: Any | None = None,
    prompt_cache_key: str | None = None,
) -> dict[str, Any]:
    from app import upstream

    kw: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kw["tools"] = tools
        if tool_choice is not None:
            kw["tool_choice"] = tool_choice
    if prompt_cache_key:
        kw["prompt_cache_key"] = prompt_cache_key
    data = await upstream.chat_completions(**kw)
    text = upstream.extract_text(data)
    pt, ct = upstream.extract_usage(data)
    tool_calls = _extract_tool_calls(data)
    return {
        "ok": True,
        "text": text,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "cached_tokens": upstream.extract_cached_tokens(data),
        "raw": data,
        "tool_calls": tool_calls,
    }


def _stable_prefix_messages(
    messages: list[dict[str, Any]],
    *,
    plan: str,
    fresh_note: str,
) -> list[dict[str, Any]]:
    """Order the doer turn so the provider prompt cache can hit.

    A tool loop is append-only, so the transcript itself is already a stable
    prefix. Anything volatile placed above it re-prices every earlier token,
    so the rarely-changing plan sits just under the client system prompt and
    this turn's note goes last.
    """
    out = list(messages)
    plan = (plan or "").strip()
    if plan:
        lead = 0
        while lead < len(out) and str(out[lead].get("role") or "") == "system":
            lead += 1
        out.insert(
            lead,
            {
                "role": "system",
                "content": (
                    "ZeusCode Task Card (durable contract; use client tools for hands):\n"
                    f"{plan[:6000]}"
                ),
            },
        )
    note = (fresh_note or "").strip()
    if note:
        # A trailing system turn is legal after tool results and never merges
        # into a neighbour, so every earlier message stays byte-identical
        # between turns. Folding the note into the last user message instead
        # would rewrite that message and break the shared prefix.
        out.append(
            {
                "role": "system",
                "content": f"[ZeusCode crew · this turn]\n{note[:4000]}",
            }
        )
    return out


def _stable_prefix_bytes(messages: list[dict[str, Any]]) -> bytes:
    """Canonical bytes for the provider-reusable portion of a doer prompt."""
    anchor: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "").lower()
        content = str(message.get("content") or "")
        if role in ("tool", "function") or (
            role == "assistant" and bool(message.get("tool_calls"))
        ) or (
            role == "system" and content.startswith("[ZeusCode crew · this turn]")
        ):
            break
        anchor.append(message)
    return json.dumps(
        anchor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _compress_tool_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compress oversized tool bodies deterministically, preserving error tails."""
    from app.fusion.context_compress import compress_tool_log

    out: list[dict[str, Any]] = []
    for raw in messages:
        item = dict(raw)
        if str(item.get("role") or "").lower() in ("tool", "function"):
            content = item.get("content")
            if isinstance(content, str):
                item["content"] = compress_tool_log(
                    content, max_chars=6000, error_tail_chars=3200
                )
        out.append(item)
    return out


async def run_hands_doer(
    *,
    model_id: str,
    messages: list[dict[str, Any]],
    crew_answer: str,
    fresh_note: str = "",
    tools: list[Any],
    tool_choice: Any | None = None,
    require_tool_call: bool = False,
    cancel_event: CancelFlag = None,
    upstream_call: UpstreamCall | None = None,
) -> dict[str, Any]:
    """Final doer call with client tools after the crew produced a plan/answer.

    ``require_tool_call`` is for clients already inside a tool loop: prose is
    not a protocol-legal reply there, so one forced retry beats handing the
    agent a message it cannot parse.
    """
    from app.openai_tools import prepare_agent_messages

    if _cancelled(cancel_event) or not tools or not model_id:
        return {
            "text": "",
            "tool_calls": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cached_tokens": 0,
            "ok": False,
        }
    agent_msgs = _stable_prefix_messages(
        prepare_agent_messages(_compress_tool_messages(list(messages or []))),
        plan=crew_answer,
        fresh_note=fresh_note,
    )
    prefix_bytes = _stable_prefix_bytes(agent_msgs)
    prefix_sha256 = hashlib.sha256(prefix_bytes).hexdigest()
    call = upstream_call or _default_upstream

    async def _invoke(*, with_tools: bool, force: bool = False) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "temperature": 0.2,
            "max_tokens": _agent_max_tokens(),
            "prompt_cache_key": f"zeus-task-{prefix_sha256[:48]}",
        }
        if with_tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "required" if force else tool_choice
        try:
            timeout_s = max(
                5.0, min(120.0, float(os.environ.get("ZEUS_HANDS_DOER_TIMEOUT_S") or 45.0))
            )
        except (TypeError, ValueError):
            timeout_s = 45.0
        return await asyncio.wait_for(
            call(model_id, agent_msgs, **kwargs),
            timeout=timeout_s,
        )

    def _calls_of(payload: dict[str, Any] | None) -> list[Any]:
        found = list((payload or {}).get("tool_calls") or [])
        if found:
            return found
        raw = (payload or {}).get("raw") if isinstance(payload, dict) else None
        return _extract_tool_calls(raw)

    data = await _invoke(with_tools=True, force=require_tool_call)
    text = str((data or {}).get("text") or "")
    tcs = _calls_of(data)
    prompt_tokens = int((data or {}).get("prompt_tokens") or 0)
    completion_tokens = int((data or {}).get("completion_tokens") or 0)
    cached_tokens = int((data or {}).get("cached_tokens") or 0)
    forced = False

    if require_tool_call:
        forced = True
        if not tcs:
            # The first call already used tool_choice=required. Retrying would
            # hide an extra billable branch and can still return invalid prose.
            text = ""
    if _cancelled(cancel_event):
        text = ""
        tcs = []

    return {
        "text": text,
        "tool_calls": tcs,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
        "forced_tool_call": forced,
        "ok": bool(tcs) if require_tool_call else bool(text.strip() or tcs),
        "model_id": model_id,
        "cache_prefix_sha256": prefix_sha256,
        "cache_prefix_bytes": len(prefix_bytes),
    }


def _note_mini(good: bool, deg: bool) -> None:
    """NFR3: verifier always-OK streak (pass without degrade)."""
    try:
        from app.fusion.metrics import note_verifier_result

        note_verifier_result(always_ok=bool(good) and not deg)
    except Exception:  # noqa: BLE001
        pass


def pick_mini_model_from_panel(panel: list[str] | None) -> str | None:
    """Stack-scoped Mini model — never invent out-of-stack DeepSeek (AD-27)."""
    stack = [m for m in (panel or []) if (m or "").strip()]
    if not stack:
        return None
    for mid in stack:
        low = mid.lower()
        if "deepseek" in low or "haiku" in low or "flash" in low:
            return mid
    return stack[0]


async def _call_mini(
    answer: str,
    user_q: str,
    *,
    mini_verify_fn: MiniVerifyFn | None,
    model: str | None = None,
) -> tuple[bool, float, bool, str]:
    """Return (pass, confidence, degraded, reason)."""
    fn = mini_verify_fn
    if fn is None:
        try:
            from app.fusion import verify as verify_mod

            fn = getattr(verify_mod, "mini_verify", None) or getattr(
                verify_mod, "run_mini_verifier", None
            )
        except Exception:  # noqa: BLE001
            fn = None
    if fn is None:
        _note_mini(False, True)
        return False, 0.0, True, "mini_unavailable"
    try:
        if model:
            try:
                res = await fn(answer=answer, user_q=user_q, model=model)
            except TypeError:
                res = await fn(answer=answer, user_q=user_q)
        else:
            res = await fn(answer=answer, user_q=user_q)
    except TypeError:
        res = await fn(answer, user_q)
    except Exception as e:  # noqa: BLE001
        _note_mini(False, True)
        return False, 0.0, True, f"mini_degrade:{e}"[:200]

    if isinstance(res, dict):
        # Prefer threshold-gated `passed` when present (Epic 2 MiniVerifyResult shape).
        if "passed" in res:
            good = bool(res.get("passed"))
        else:
            good = bool(res.get("good_enough") or res.get("pass"))
        conf = float(res.get("confidence") or 0.0)
        deg = bool(res.get("degraded"))
        reason = str(res.get("reason") or "")
        _note_mini(good, deg)
        return good, conf, deg, reason
    if hasattr(res, "passed"):
        good = bool(getattr(res, "passed"))
    else:
        good = bool(getattr(res, "good_enough", False))
    conf = float(getattr(res, "confidence", 0.0) or 0.0)
    deg = bool(getattr(res, "degraded", False))
    reason = str(getattr(res, "reason", "") or "")
    _note_mini(good, deg)
    return good, conf, deg, reason


def _cancelled(flag: CancelFlag) -> bool:
    return bool(flag is not None and flag.is_set())


async def _run_one_model(
    *,
    model_id: str,
    messages: list[dict[str, Any]],
    role: str,
    is_leader: bool,
    upstream_call: UpstreamCall | None,
    temperature: float | None,
    max_tokens: int | None,
    cancel_event: CancelFlag,
) -> LiveBranch:
    if _cancelled(cancel_event):
        return LiveBranch(
            model_id=model_id,
            role=role,
            is_leader=is_leader,
            billable_state="cancelled_no_tokens",
            error="cancelled_before_start",
        )
    t0 = time.perf_counter()
    call = upstream_call or _default_upstream
    try:
        data = await call(
            model_id,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if _cancelled(cancel_event):
            text = str((data or {}).get("text") or "")
            pt = int((data or {}).get("prompt_tokens") or 0)
            ct = int((data or {}).get("completion_tokens") or 0)
            return LiveBranch(
                model_id=model_id,
                role=role,
                text=text,
                ok=False,
                is_leader=is_leader,
                prompt_tokens=pt,
                completion_tokens=ct,
                latency_s=round(time.perf_counter() - t0, 3),
                billable_state=billable_for_branch(
                    ok=False,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    text=text,
                    cancelled=True,
                    partial=True,
                ),
                error="cancelled_mid_flight",
            )
        ok = bool((data or {}).get("ok", True))
        text = str((data or {}).get("text") or "")
        pt = int((data or {}).get("prompt_tokens") or 0)
        ct = int((data or {}).get("completion_tokens") or 0)
        err = (data or {}).get("error")
        branch = LiveBranch(
            model_id=model_id,
            role=role,
            text=text,
            ok=ok and bool(text.strip()),
            is_leader=is_leader,
            prompt_tokens=pt,
            completion_tokens=ct,
            latency_s=round(time.perf_counter() - t0, 3),
            error=str(err)[:400] if err else None,
            billable_state=billable_for_branch(
                ok=ok and bool(text.strip()),
                prompt_tokens=pt,
                completion_tokens=ct,
                text=text,
                cancelled=False,
            ),
        )
        if not branch.ok:
            try:
                from app.fusion.metrics import note_dead_model

                note_dead_model(model_id)
            except Exception:  # noqa: BLE001
                pass
        return branch
    except asyncio.CancelledError:
        # Tokens may already be spent on the wire — prefer cancelled_with_usage when known.
        return LiveBranch(
            model_id=model_id,
            role=role,
            is_leader=is_leader,
            latency_s=round(time.perf_counter() - t0, 3),
            billable_state="cancelled_no_tokens",
            error="cancelled",
        )
    except Exception as e:  # noqa: BLE001
        err = str(e)[:400]
        return LiveBranch(
            model_id=model_id,
            role=role,
            is_leader=is_leader,
            latency_s=round(time.perf_counter() - t0, 3),
            billable_state="cancelled_no_tokens",
            error=err,
            ok=False,
        )


async def execute_fallback_single(
    *,
    curator: str,
    messages: list[dict[str, Any]],
    user_q: str = "",
    product_mode: str = "custom",
    complexity: str = "med",
    phase: str = "implement",
    upstream_call: UpstreamCall | None = None,
    cancel_event: CancelFlag = None,
    adapt_prompts: bool = True,
) -> ExecuteOutcome:
    """AD-23 / FR-18.8: curator full answer in **one** call.

    No Architect Brief, no mid-parallel doers, no models auto-added.
    Mini → Log → Escalate ≤2 → Soft-Stop run afterward (Trusted Verify Loop).
    """
    _ = (user_q, product_mode)  # reserved for telemetry / adapt
    cur = (curator or "").strip()
    cx = complexity if complexity in ("light", "med", "heavy") else "med"
    ph = phase if phase in (
        "chat", "ui", "docs", "test", "implement", "debug", "plan", "review"
    ) else "implement"
    if not cur:
        return ExecuteOutcome(
            path="CASCADE",
            policy_path="CASCADE",
            routed_by="fallback_single_disaster",
            answer="",
            leader=None,
            branches=[],
            disaster=True,
            disaster_code="fusion_disaster_no_curator",
            complexity=cx,
            phase=ph,
            meta={
                "pipeline": "fallback_single",
                "no_architect_brief": True,
                "mid_parallel": False,
            },
        )

    msgs = list(messages or [])
    if adapt_prompts:
        msgs = adapt_prompt_for_family(
            msgs, model_family(cur), role="leader"
        )
    # Explicit full-answer contract — never satellite Brief
    sys_hint = (
        "[Zeus fallback_single] You are the sole curator. Write the complete "
        "final answer for the user in one shot. Do not emit an Architect Brief, "
        "component plan, or wait for peer doers."
    )
    if msgs and msgs[0].get("role") == "system":
        msgs = [
            {
                "role": "system",
                "content": f"{msgs[0].get('content') or ''}\n\n{sys_hint}".strip(),
            },
            *msgs[1:],
        ]
    else:
        msgs = [{"role": "system", "content": sys_hint}, *msgs]

    branch = await _run_one_model(
        model_id=cur,
        messages=msgs,
        role="doer_logic",
        is_leader=True,
        upstream_call=upstream_call,
        temperature=0.2,
        max_tokens=_agent_max_tokens(path="CASCADE"),
        cancel_event=cancel_event,
    )
    branch.meta = {
        **(branch.meta or {}),
        "pipeline": "fallback_single",
        "no_architect_brief": True,
        "mid_parallel": False,
    }
    answer = (branch.text or "").strip()
    return ExecuteOutcome(
        path="CASCADE",
        policy_path="CASCADE",
        routed_by="fallback_single_curator",
        answer=answer,
        leader=cur,
        branches=[live_to_usage(branch, role="doer_logic")],
        live=[branch],
        complexity=cx,  # type: ignore[arg-type]
        phase=ph,
        # Leave Mini to Trusted Verify Loop (AD-23 order)
        early_exit=None,
        disaster=not bool(answer),
        disaster_code="fusion_disaster_curator_empty" if not answer else None,
        meta={
            "pipeline": "fallback_single",
            "no_architect_brief": True,
            "mid_parallel": False,
            "max_doer_llms": 1,
            "llm_calls": 1,
        },
    )


async def execute_cascade(
    *,
    panel: list[str],
    leader: str,
    messages: list[dict[str, Any]],
    user_q: str,
    product_mode: str = "power",
    complexity: str = "med",
    phase: str = "implement",
    kill_switch: bool = False,
    ready: list[str] | None = None,
    upstream_call: UpstreamCall | None = None,
    mini_verify_fn: MiniVerifyFn | None = None,
    mini_model: str | None = None,
    cancel_event: CancelFlag = None,
    adapt_prompts: bool = True,
) -> ExecuteOutcome:
    """CASCADE: execute-leader first + Mini-Verifier; FR-8 escalate; FR-15 failover.

    Panel is doer-first (role routing). On empty/500 → next in failover chain
    (Opus flakiness must not block cheaper doers that already sit first).
    """
    from app.fusion.policy import cascade_escalate_action, leader_failover_chain
    from app.fusion.verify import run_mini_verifier

    pm = product_mode if product_mode in ("simple", "power", "custom") else "power"
    cx = complexity if complexity in ("light", "med", "heavy") else "med"
    mini_model = (mini_model or "").strip() or pick_mini_model_from_panel(panel)
    ph = phase if phase in (
        "chat", "ui", "docs", "test", "implement", "debug", "plan", "review"
    ) else "implement"
    # Role-routing: leader = doer (panel[0]). Legacy strength-first used panel[-1].
    ready_list = list(ready or panel or [])
    start = (
        leader
        if leader and leader in ready_list
        else (panel[0] if panel else leader)
    )
    # Custom: preserve user panel order (FR-15). Power/simple: start → ascending power
    # (ops LEADER_FAILOVER is strong-first and would leave flash with no next).
    if pm == "custom":
        order = list(panel) if panel else list(ready_list)
        if start and start in order:
            chain = [start] + [m for m in order if m != start]
        else:
            chain = leader_failover_chain(
                product_mode=pm,  # type: ignore[arg-type]
                ready=ready_list,
                custom_order=order,
                start=start,
            )
    elif start and start in ready_list:
        try:
            from app.fusion.model_power import power_score as _ps

            rest = sorted(
                (m for m in ready_list if m != start),
                key=lambda m: (_ps(m), ready_list.index(m) if m in ready_list else 0),
            )
            chain = [start, *rest]
        except Exception:  # noqa: BLE001
            chain = leader_failover_chain(
                product_mode=pm,  # type: ignore[arg-type]
                ready=ready_list,
                custom_order=None,
                start=start,
            )
    else:
        chain = leader_failover_chain(
            product_mode=pm,  # type: ignore[arg-type]
            ready=ready_list,
            custom_order=None,
            start=start,
        )
    if not chain:
        return ExecuteOutcome(
            path="CASCADE",
            policy_path="CASCADE",
            routed_by="cascade_disaster",
            answer="",
            leader=leader,
            branches=[],
            disaster=True,
            disaster_code="fusion_disaster_empty_failover",
            complexity=cx,
            phase=ph,
        )
    # Light: never walk the full power stack — one doer (+ optional panel backup)
    if cx == "light":
        lead0 = chain[0]
        backup = next((m for m in chain[1:] if m in (panel or [])), None)
        chain = [lead0, backup] if backup and backup != lead0 else [lead0]

    live: list[LiveBranch] = []
    stronger_tried = False
    steps = 0
    current = chain[0]
    final_answer = ""
    final_leader = current
    routed_by = "policy_cascade_mini_pass"
    escalate_from: str | None = None

    def _next_in_chain(cur: str | None) -> str | None:
        if not cur or cur not in chain:
            return chain[0] if chain else None
        i = chain.index(cur)
        return chain[i + 1] if i + 1 < len(chain) else None

    while current and steps < 6:
        steps += 1
        if _cancelled(cancel_event):
            break
        msgs = messages
        if adapt_prompts:
            msgs = adapt_prompt_for_family(
                messages,
                model_family(current),
                role="leader" if current == leader else "satellite",
            )
        branch = await _run_one_model(
            model_id=current,
            messages=msgs,
            role="cheap" if not stronger_tried else "strong",
            is_leader=current == leader,
            upstream_call=upstream_call,
            temperature=0.2,
            max_tokens=_agent_max_tokens(path="CASCADE"),
            cancel_event=cancel_event,
        )
        live.append(branch)

        if not branch.ok or not (branch.text or "").strip():
            nxt = _next_in_chain(current)
            if not nxt:
                return ExecuteOutcome(
                    path="CASCADE",
                    policy_path="CASCADE",
                    routed_by="cascade_disaster",
                    answer="",
                    leader=final_leader,
                    branches=[
                        BranchUsage(
                            model_id=b.model_id,
                            billable_state=b.billable_state,
                            prompt_tokens=b.prompt_tokens,
                            completion_tokens=b.completion_tokens,
                            role="agent",
                        )
                        for b in live
                    ],
                    live=live,
                    disaster=True,
                    disaster_code="fusion_disaster_leader_failover_empty",
                    complexity=cx,
                    phase=ph,
                    escalate_from=escalate_from,
                )
            current = nxt
            stronger_tried = True
            continue

        mini_fn = mini_verify_fn or run_mini_verifier
        try:
            if mini_model:
                try:
                    mini_res = await mini_fn(
                        answer=branch.text, user_q=user_q, model=mini_model
                    )
                except TypeError:
                    mini_res = await mini_fn(answer=branch.text, user_q=user_q)
            else:
                mini_res = await mini_fn(answer=branch.text, user_q=user_q)
        except TypeError:
            mini_res = await mini_fn(branch.text, user_q)
        passed, conf, deg, reason = False, 0.0, True, "mini_unavailable"
        if hasattr(mini_res, "passed"):
            passed = bool(mini_res.passed)
            conf = float(getattr(mini_res, "confidence", 0.0) or 0.0)
            deg = bool(getattr(mini_res, "degraded", False))
            reason = str(getattr(mini_res, "reason", "") or "")
        elif isinstance(mini_res, dict):
            passed = bool(mini_res.get("passed") or mini_res.get("good_enough"))
            conf = float(mini_res.get("confidence") or 0.0)
            deg = bool(mini_res.get("degraded"))
            reason = str(mini_res.get("reason") or "")
        branch.verifier_pass = passed
        branch.verifier_confidence = conf
        branch.verifier_degraded = deg
        branch.meta["mini_reason"] = reason

        if passed:
            final_answer = branch.text
            final_leader = current
            routed_by = "policy_cascade_mini_pass"
            break

        esc = cascade_escalate_action(
            kill_switch=kill_switch,
            product_mode=pm,  # type: ignore[arg-type]
            complexity=cx,  # type: ignore[arg-type]
            phase=ph,  # type: ignore[arg-type]
            stronger_already_tried=stronger_tried,
        )
        escalate_from = "CASCADE"
        routed_by = esc.routed_by
        if esc.action == "keep":
            # Power fixed crew: accept current answer; Judge/soft-stop later.
            final_answer = branch.text
            final_leader = current
            break
        if esc.action == "full" and esc.allow_full:
            return ExecuteOutcome(
                path="FULL",
                policy_path="CASCADE",
                routed_by=esc.routed_by,
                answer=final_answer or branch.text,
                leader=final_leader,
                branches=[
                    BranchUsage(
                        model_id=b.model_id,
                        billable_state=b.billable_state,
                        prompt_tokens=b.prompt_tokens,
                        completion_tokens=b.completion_tokens,
                        role="agent",
                    )
                    for b in live
                ],
                live=live,
                escalate_from="CASCADE",
                complexity=cx,
                phase=ph,
                early_exit="cascade_escalate_full",
                meta={"hand_off_full": True},
            )

        nxt = _next_in_chain(current)
        if not nxt:
            final_answer = branch.text
            final_leader = current
            break
        current = nxt
        stronger_tried = True

    return ExecuteOutcome(
        path="CASCADE",
        policy_path="CASCADE",
        routed_by=routed_by,
        answer=(final_answer or "").strip(),
        leader=final_leader,
        branches=[
            BranchUsage(
                model_id=b.model_id,
                billable_state=b.billable_state,
                prompt_tokens=b.prompt_tokens,
                completion_tokens=b.completion_tokens,
                role="agent",
                meta=dict(b.meta),
            )
            for b in live
        ],
        live=live,
        escalate_from=escalate_from,
        complexity=cx,
        phase=ph,
        early_exit="mini_pass" if routed_by == "policy_cascade_mini_pass" else None,
    )


async def execute_race(
    *,
    cheap_model: str,
    strong_model: str,
    messages: list[dict[str, Any]],
    user_q: str = "",
    product_mode: str = "power",
    complexity: str = "med",
    policy_path: PathName = "RACE",
    mini_verify_fn: MiniVerifyFn | None = None,
    upstream_call: UpstreamCall | None = None,
    cancel_event: CancelFlag = None,
    soft_stop: bool = False,
    timeout_s: float | None = None,
    adapt_prompts: bool = True,
) -> ExecuteOutcome:
    """Speculative RACE: parallel cheap+strong; first годный wins (FR-9)."""
    q = user_q or ""
    try:
        from app.fusion.metrics import (
            race_concurrency_semaphore,
            runtime_budgets_from_settings,
        )

        _budgets = runtime_budgets_from_settings()
        if timeout_s is None:
            timeout_s = min(14.0, float(_budgets.global_timeout_s))
        else:
            timeout_s = min(float(timeout_s), float(_budgets.global_timeout_s))
        race_sem = race_concurrency_semaphore()
    except Exception:  # noqa: BLE001
        if timeout_s is None:
            timeout_s = 14.0
        race_sem = None
    pair = [
        ("cheap", cheap_model, False),
        ("strong", strong_model, True),
    ]

    async def _race_one(
        mid: str, role: str, is_leader: bool, msgs: list[dict[str, Any]]
    ) -> LiveBranch:
        async def _inner() -> LiveBranch:
            return await _run_one_model(
                model_id=mid,
                messages=msgs,
                role=role,
                is_leader=is_leader,
                upstream_call=upstream_call,
                temperature=0.3 if role == "cheap" else 0.4,
                max_tokens=_agent_max_tokens(),
                cancel_event=cancel_event,
            )

        if race_sem is None:
            return await _inner()
        async with race_sem:
            return await _inner()

    tasks: dict[asyncio.Task[LiveBranch], str] = {}
    for role, mid, is_leader in pair:
        msgs = [dict(m) for m in messages]
        if adapt_prompts:
            msgs = adapt_prompt_for_family(msgs, model_family(mid), role=role)
        tasks[
            asyncio.create_task(
                _race_one(mid, role, is_leader, msgs),
                name=f"race-{role}",
            )
        ] = role

    results: list[LiveBranch] = []
    winner: LiveBranch | None = None
    deadline = time.perf_counter() + timeout_s
    mini_degrade_global = False

    try:
        while tasks and winner is None:
            if _cancelled(cancel_event):
                break
            left = max(0.05, deadline - time.perf_counter())
            done, _ = await asyncio.wait(
                set(tasks.keys()), timeout=left, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                break
            for t in done:
                tasks.pop(t, None)
                try:
                    branch = t.result()
                except Exception as e:  # noqa: BLE001
                    branch = LiveBranch(
                        model_id="unknown",
                        role="strong",
                        error=str(e)[:400],
                        billable_state="cancelled_no_tokens",
                    )
                results.append(branch)
                if not branch.ok or not (branch.text or "").strip():
                    continue
                good, conf, deg, reason = await _call_mini(
                    branch.text,
                    q,
                    mini_verify_fn=mini_verify_fn,
                    model=pick_mini_model_from_panel([cheap_model, strong_model]),
                )
                branch.verifier_confidence = conf
                branch.verifier_pass = good
                branch.verifier_degraded = deg
                branch.meta["mini_reason"] = reason
                if deg:
                    mini_degrade_global = True
                # Годный = Mini pass OR (degrade → first-complete strong)
                if good or (deg and branch.role == "strong"):
                    winner = branch
                    break
                if deg and branch.role == "cheap" and not good:
                    # cheap under degrade does not auto-win; wait for strong
                    continue
    finally:
        for t in list(tasks):
            t.cancel()
        if tasks:
            finished = await asyncio.gather(*tasks.keys(), return_exceptions=True)
            for item in finished:
                if isinstance(item, LiveBranch):
                    # Loser cancelled mid-flight
                    if item.billable_state not in (
                        "completed",
                        "partial_stream",
                        "cancelled_with_usage",
                        "cancelled_no_tokens",
                    ):
                        item.billable_state = billable_for_branch(
                            ok=False,
                            prompt_tokens=item.prompt_tokens,
                            completion_tokens=item.completion_tokens,
                            text=item.text,
                            cancelled=True,
                        )
                    elif item.ok and winner is not None and item is not winner:
                        item.billable_state = billable_for_branch(
                            ok=False,
                            prompt_tokens=item.prompt_tokens,
                            completion_tokens=item.completion_tokens,
                            text=item.text,
                            cancelled=True,
                            partial=bool(item.text),
                        )
                        item.ok = False
                        item.error = item.error or "cancelled_loser"
                    results.append(item)

    # Mark non-winner completed branches as cancelled losers when we have a winner.
    if winner is not None:
        for b in results:
            if b.model_id == winner.model_id and b.role == winner.role:
                b.billable_state = "completed"
                b.ok = True
                continue
            if b.billable_state == "completed":
                b.billable_state = billable_for_branch(
                    ok=False,
                    prompt_tokens=b.prompt_tokens,
                    completion_tokens=b.completion_tokens,
                    text=b.text,
                    cancelled=True,
                    partial=bool(b.text),
                )
                b.ok = False
                b.error = b.error or "cancelled_loser"

        return ExecuteOutcome(
            path="RACE",
            policy_path=policy_path,
            routed_by="race_first_fit",
            answer=winner.text.strip(),
            leader=strong_model,
            branches=[live_to_usage(b) for b in results],
            live=results,
            complexity=complexity,  # type: ignore[arg-type]
            early_exit="race_winner",
            meta={
                "winner": winner.model_id,
                "mini_degrade": mini_degrade_global,
                "soft_stop": soft_stop,
            },
        )

    # Soft-Stop trigger with partials mid-flight (AD-25: power_score pick)
    if soft_stop or _cancelled(cancel_event):
        pick = soft_stop_pick_by_power(results, leader_id=strong_model)
        if pick is not None and (pick.text or "").strip():
            return ExecuteOutcome(
                path="RACE",
                policy_path=policy_path,
                routed_by="race_soft_stop",
                answer=pick.text.strip(),
                leader=strong_model,
                branches=[live_to_usage(b) for b in results],
                live=results,
                complexity=complexity,  # type: ignore[arg-type]
                early_exit="soft_stop",
                meta={"terminal": "soft_stop_cancel"},
            )

    return race_both_fail_terminal(
        product_mode=product_mode,
        complexity=complexity,
        branches=results,
        leader_id=strong_model,
        policy_path=policy_path,
    )


def _assign_roles(panel: list[str], leader: str) -> list[tuple[str, str, bool]]:
    """Return list of (role, model_id, is_leader)."""
    ordered = [leader] + [m for m in panel if m != leader]
    roles = ["A", "B", "C", "D", "E", "F", "G"]
    try:
        from app.fusion.roles import max_panel_size

        cap = max_panel_size()
    except Exception:  # noqa: BLE001
        cap = 5
    out: list[tuple[str, str, bool]] = []
    for i, mid in enumerate(ordered[:cap]):
        out.append((roles[i], mid, mid == leader))
    return out


async def execute_full(
    *,
    panel: list[str],
    leader: str,
    messages: list[dict[str, Any]],
    user_q: str,
    judge_model: str | None = None,
    policy_path: PathName = "FULL",
    ops_diversity_exception: bool = False,
    upstream_call: UpstreamCall | None = None,
    judge_call: Any | None = None,
    aspect_call: Any | None = None,
    cancel_event: CancelFlag = None,
    soft_stop: bool = False,
    adapt_prompts: bool = True,
    include_security_aspect: bool = False,
) -> ExecuteOutcome:
    """FULL Panel: Brief, diversity, Aspects→τ→rank-then-fuse Judge (FR-10/12/13/31)."""
    try:
        from app.fusion.roles import max_panel_size

        _cap = max_panel_size()
    except Exception:  # noqa: BLE001
        _cap = 5
    panel = list(panel)[:_cap]
    if leader not in panel and panel:
        leader = panel[0]
    families = assert_panel_diversity(panel, ops_exception=ops_diversity_exception)

    try:
        from app.fusion.metrics import panel_concurrency_semaphore

        panel_sem = panel_concurrency_semaphore()
    except Exception:  # noqa: BLE001
        panel_sem = None

    async def _full_one(
        mid: str,
        role: str,
        is_lead: bool,
        msgs: list[dict[str, Any]],
    ) -> LiveBranch:
        async def _inner() -> LiveBranch:
            return await _run_one_model(
                model_id=mid,
                messages=msgs,
                role=role,
                is_leader=is_lead,
                upstream_call=upstream_call,
                temperature=ROLE_TEMPERATURE.get(role),
                max_tokens=_agent_max_tokens(),
                cancel_event=cancel_event,
            )

        if panel_sem is None:
            return await _inner()
        async with panel_sem:
            return await _inner()

    role_rows = _assign_roles(panel, leader)
    tasks: list[asyncio.Task[LiveBranch]] = []
    for role, mid, is_lead in role_rows:
        if is_lead:
            msgs = [dict(m) for m in messages]
            if adapt_prompts:
                msgs = adapt_prompt_for_family(msgs, families.get(mid, model_family(mid)), role="leader")
        else:
            msgs = build_satellite_brief(
                messages,
                user_q,
                family=families.get(mid, model_family(mid)) if adapt_prompts else None,
            )
        tasks.append(
            asyncio.create_task(
                _full_one(mid, role, is_lead, msgs),
                name=f"full-{role}",
            )
        )

    live: list[LiveBranch] = []
    pending = set(tasks)
    while pending:
        if _cancelled(cancel_event) and live:
            # Cancel unfinished
            for t in list(pending):
                t.cancel()
            break
        done, pending = await asyncio.wait(
            pending, return_when=asyncio.FIRST_COMPLETED
        )
        for t in done:
            try:
                live.append(t.result())
            except Exception as e:  # noqa: BLE001
                live.append(
                    LiveBranch(
                        model_id="unknown",
                        role="A",
                        error=str(e)[:400],
                        billable_state="cancelled_no_tokens",
                    )
                )

    # Collect cancelled leftovers
    for t in pending:
        t.cancel()
    if pending:
        extras = await asyncio.gather(*pending, return_exceptions=True)
        for item in extras:
            if isinstance(item, LiveBranch):
                if item.billable_state == "completed" and _cancelled(cancel_event):
                    item.billable_state = billable_for_branch(
                        ok=False,
                        prompt_tokens=item.prompt_tokens,
                        completion_tokens=item.completion_tokens,
                        text=item.text,
                        cancelled=True,
                        partial=True,
                    )
                live.append(item)

    # Soft-Stop / cancel mid-flight: only when cancel signaled (FR-14).
    # ``soft_stop`` alone must not skip Aspects/Judge after a full successful panel.
    if _cancelled(cancel_event) or soft_stop:
        for b in live:
            if b.billable_state == "completed" and not b.ok:
                b.billable_state = billable_for_branch(
                    ok=False,
                    prompt_tokens=b.prompt_tokens,
                    completion_tokens=b.completion_tokens,
                    text=b.text,
                    cancelled=True,
                    partial=bool(b.text),
                )
        unfinished = _cancelled(cancel_event) or any(
            b.billable_state
            in {"cancelled_no_tokens", "cancelled_with_usage", "partial_stream"}
            for b in live
        )
        if unfinished:
            pick = soft_stop_pick_by_power(live, leader_id=leader)
            if pick is not None and (pick.text or "").strip():
                return ExecuteOutcome(
                    path="FULL",
                    policy_path=policy_path,
                    routed_by="full_soft_stop",
                    answer=pick.text.strip(),
                    leader=leader,
                    branches=[live_to_usage(b) for b in live],
                    live=live,
                    early_exit="soft_stop",
                    meta={"families": families, "soft_stop": True},
                )

    ok_live = [b for b in live if b.ok and (b.text or "").strip()]
    if not ok_live:
        pick = soft_stop_pick_by_power(live, leader_id=leader)
        if pick is not None and (pick.text or "").strip():
            return ExecuteOutcome(
                path="FULL",
                policy_path=policy_path,
                routed_by="full_soft_stop",
                answer=pick.text.strip(),
                leader=leader,
                branches=[live_to_usage(b) for b in live],
                live=live,
                early_exit="soft_stop",
                meta={"families": families},
            )
        return ExecuteOutcome(
            path="FULL",
            policy_path=policy_path,
            routed_by="full_disaster",
            answer="",
            leader=leader,
            branches=[live_to_usage(b) for b in live],
            live=live,
            disaster=True,
            disaster_code="full_disaster",
            meta={"families": families},
        )

    # 1 success ⇒ that branch is final (no Judge) — FR-10/13
    if len(ok_live) == 1:
        only = ok_live[0]
        return ExecuteOutcome(
            path="FULL",
            policy_path=policy_path,
            routed_by="full_single_success",
            answer=only.text.strip(),
            leader=leader,
            branches=[live_to_usage(b) for b in live],
            live=live,
            early_exit="single_success",
            meta={"families": families},
        )

    # Aspects BEFORE near-duplicate τ (AD-5 / FR-31). Prefer Leader text.
    aspect_src = next((b for b in ok_live if b.is_leader), ok_live[0])
    aspects = await run_aspect_verifiers_v1(
        answer=aspect_src.text,
        user_q=user_q,
        call_fn=aspect_call,
        include_security=include_security_aspect,
    )
    aspect_branches = [
        BranchUsage(
            model_id=f"aspect:{v.aspect}",
            billable_state="completed" if not v.degraded else "partial_stream",
            prompt_tokens=v.prompt_tokens,
            completion_tokens=v.completion_tokens,
            role="verifier",
            meta={
                "passed": v.passed,
                "must": v.must,
                "confidence": v.confidence,
                "reason": v.reason,
                "degraded": v.degraded,
            },
        )
        for v in aspects.verdicts
    ]

    texts = [b.text for b in ok_live]
    is_dup, dup_score = near_duplicate_among(texts)
    if is_dup and not aspects_block_tau_exit(aspects):
        # Early-exit without full Judge — AD-25 power_score pick (tie→latest)
        pick = soft_stop_pick_by_power(ok_live, leader_id=leader) or ok_live[0]
        usages = [live_to_usage(b) for b in live] + aspect_branches
        return ExecuteOutcome(
            path="FULL",
            policy_path=policy_path,
            routed_by="full_near_duplicate",
            answer=pick.text.strip(),
            leader=leader,
            branches=usages,
            live=live,
            aspects=aspects,
            early_exit="near_duplicate",
            meta={
                "families": families,
                "near_duplicate_score": dup_score,
                "aspects_must_fail": aspects.must_fail,
            },
        )

    # Rank-then-fuse top-K → Structured Judge
    ranked, top_k = rank_then_fuse_plan(
        [
            {
                "model_id": b.model_id,
                "text": b.text,
                "ok": b.ok,
                "is_leader": b.is_leader,
                "latency_s": b.latency_s,
                "verifier_confidence": b.verifier_confidence,
            }
            for b in ok_live
        ]
    )

    async def _judge_call(model: str, msgs: list[dict[str, Any]]) -> Any:
        if judge_call is not None:
            return await judge_call(model, msgs)
        data = await (upstream_call or _default_upstream)(model, msgs)
        return data.get("text"), data.get("prompt_tokens", 0), data.get("completion_tokens", 0)

    analysis = await run_structured_judge(
        top_k=top_k,
        user_q=user_q,
        judge_model=judge_model,
        call_fn=_judge_call if judge_model else None,
    )

    usages = [live_to_usage(b) for b in live] + aspect_branches
    if analysis.used_judge and judge_model:
        usages.append(
            BranchUsage(
                model_id=judge_model,
                billable_state="completed",
                prompt_tokens=analysis.prompt_tokens,
                completion_tokens=analysis.completion_tokens,
                role="judge",
                meta={
                    "anti_bias_fail": analysis.anti_bias_fail,
                    "top_k": [r.model_id for r in top_k],
                },
            )
        )

    return ExecuteOutcome(
        path="FULL",
        policy_path=policy_path,
        routed_by="full_judge" if analysis.used_judge else "full_local_fuse",
        answer=(analysis.final_answer or "").strip(),
        leader=leader,
        branches=usages,
        live=live,
        aspects=aspects,
        judge=analysis,
        meta={
            "families": families,
            "ranked": [(r.model_id, r.score) for r in ranked],
            "top_k": [r.model_id for r in top_k],
            "near_duplicate_score": dup_score,
            "aspects_must_fail": aspects.must_fail,
            "anti_bias_fail": analysis.anti_bias_fail,
            "judge_analysis": {
                "consensus": analysis.consensus,
                "contradictions": analysis.contradictions,
                "unique": analysis.unique,
                "blind_spots": analysis.blind_spots,
            },
        },
    )


def outcome_to_completion(
    outcome: ExecuteOutcome,
    *,
    panel: list[str],
    product_mode: str = "power",
    task_kind: str = "general",
    role_routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Brownfield-shaped completion dict for iter_fusion done event."""
    total_pt = sum(b.prompt_tokens for b in outcome.branches)
    total_ct = sum(b.completion_tokens for b in outcome.branches)
    answer = outcome.answer or ""
    rr = role_routing if isinstance(role_routing, dict) else {}

    def _rr_role(raw: str, model_id: str) -> str:
        r = (raw or "agent").strip().lower()
        if r in ("verifier", "mini", "mini_verifier"):
            return "mini_verifier"
        if r in ("log_analyst", "classifier", "judge", "architect", "test_author"):
            return r
        # Map brownfield panel/agent → doer_* from Role Routing table when present
        mbr = rr.get("models_by_role") if isinstance(rr.get("models_by_role"), dict) else {}
        for role_name, mid in mbr.items():
            if mid == model_id and str(role_name).startswith("doer"):
                return str(role_name)
        doer = None
        roles_list = rr.get("roles") if isinstance(rr.get("roles"), list) else []
        for role_name in roles_list:
            if str(role_name).startswith("doer"):
                doer = str(role_name)
                break
        if r in ("agent", "panel", "doer", "") and doer:
            return doer
        return r if r else "agent"

    branch_dicts = [
        {
            "model_id": b.model_id,
            "billable_state": b.billable_state,
            "prompt_tokens": b.prompt_tokens,
            "completion_tokens": b.completion_tokens,
            "role": _rr_role(b.role, b.model_id),
            "meta": b.meta,
        }
        for b in outcome.branches
    ]
    # Keep BranchUsage.role aligned for FusionResult
    for b, row in zip(outcome.branches, branch_dicts):
        b.role = str(row["role"])
    anti_bias = bool((outcome.meta or {}).get("anti_bias_fail"))
    if outcome.judge is not None:
        anti_bias = anti_bias or bool(getattr(outcome.judge, "anti_bias_fail", False))
    # AD-32: leader = who executed; curator = Soft-Stop/Judge (may differ on small)
    exec_lead = (
        rr.get("execute_leader")
        or outcome.leader
        or rr.get("curator_model")
    )
    curator = rr.get("curator_model") or exec_lead
    onestack = {
        "mode": f"fusion-{str(outcome.path).lower()}",
        "fusion_mode": "full" if outcome.path in {"FULL", "RACE"} else "fast",
        "stack_size": "full" if outcome.path in {"FULL", "RACE"} else "fast",
        "product_mode": product_mode,
        "path": outcome.path,
        "policy_path": outcome.policy_path,
        "escalate_from": outcome.escalate_from,
        "routed_by": outcome.routed_by,
        "phase": outcome.phase,
        "complexity": outcome.complexity,
        "task_kind": rr.get("task_kind") or task_kind,
        "leader": exec_lead,
        "panel": panel,
        "trace_id": outcome.trace_id,
        "early_exit": outcome.early_exit,
        "disaster": outcome.disaster,
        "anti_bias_fail": anti_bias,
        "release_blocked": anti_bias,  # FR-13 / Story 3.3 — fails PR/release gate
        "branches": branch_dicts,
        "answer_only": answer,
        "thinking_visible": True,
        "epic3": outcome.meta,
        "ui_crew": (
            {
                "author": (outcome.meta or {}).get("author"),
                "critics": (outcome.meta or {}).get("critics"),
                "power_scores": (outcome.meta or {}).get("power_scores"),
                "web": (outcome.meta or {}).get("web"),
                "critique_merged": (outcome.meta or {}).get("critique_merged"),
            }
            if (outcome.meta or {}).get("crew") == "ui_author_critics"
            else None
        ),
        "pipeline": rr.get("pipeline") or "small",
        "size": rr.get("size") or "small",
        "second_signal": bool(rr.get("second_signal")),
        "curator_model": curator,
        "role_table": rr.get("role_table") or "v1",
        "roles": list(rr.get("roles") or []),
        "models_by_role": dict(rr.get("models_by_role") or {}),
        "gate": rr.get("gate"),
        "gate_reasons": list(rr.get("gate_reasons") or []),
        "escalate_count": int(rr.get("escalate_count") or 0),
        "soft_stop": bool(
            rr.get("soft_stop") or (outcome.early_exit == "soft_stop")
        ),
        "log_report": rr.get("log_report", "N/A"),
        "soft_stop_model": rr.get("soft_stop_model"),
        "turn_kind": rr.get("turn_kind") or "bootstrap",
        "crew_size": int(rr.get("crew_size") or 2),
        "crew_tier": rr.get("crew_tier") or "compact",
        "active_roles": list(rr.get("active_roles") or []),
        "crew_reason": rr.get("crew_reason") or "",
        "crew_budgets": dict(rr.get("crew_budgets") or {}),
        "crew_state": dict(rr.get("crew_state") or {}),
    }
    fr = FusionResult(
        path=outcome.path,
        policy_path=outcome.policy_path,
        routed_by=outcome.routed_by,
        phase=outcome.phase,
        complexity=outcome.complexity,
        leader=exec_lead,
        branches=list(outcome.branches),
        answer=answer,
        trace_id=outcome.trace_id,
        escalate_from=outcome.escalate_from,
        onestack=onestack,
        pipeline=onestack["pipeline"],
        curator_model=curator,
        role_table=onestack["role_table"],
        roles=list(onestack["roles"]),
        models_by_role=dict(onestack["models_by_role"]),
        task_kind=onestack["task_kind"],
        size=onestack["size"],
        gate=onestack.get("gate"),
        gate_reasons=list(onestack.get("gate_reasons") or []),
        escalate_count=int(onestack.get("escalate_count") or 0),
        soft_stop=bool(onestack.get("soft_stop")),
    )
    tool_calls = list((outcome.meta or {}).get("tool_calls") or [])
    message: dict[str, Any] = {
        "role": "assistant",
        "content": answer if answer else (None if tool_calls else ""),
    }
    if tool_calls:
        message["tool_calls"] = tool_calls
    finish_reason = "tool_calls" if tool_calls else "stop"
    data = {
        "id": f"chatcmpl-fusion-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "zeuscode",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": total_pt,
            "completion_tokens": total_ct,
            "total_tokens": total_pt + total_ct,
        },
        "onestack": onestack,
        "_bill_model": outcome.leader or (panel[0] if panel else "deepseek-chat"),
        "_fusion_outcome": outcome,
        "_fusion_result": fr,
        "fusion_result": {
            "path": fr.path,
            "policy_path": fr.policy_path,
            "routed_by": fr.routed_by,
            "phase": fr.phase,
            "complexity": fr.complexity,
            "leader": fr.leader,
            "branches": branch_dicts,
            "answer": fr.answer,
            "trace_id": fr.trace_id,
            "escalate_from": fr.escalate_from,
        },
    }
    fr.completion = {k: v for k, v in data.items() if k != "_fusion_result"}
    return data


def clamp_f13_never_race_on_heavy(
    path: PathName | str,
    *,
    complexity: str | None = None,
    phase: str | None = None,
) -> PathName:
    """F13 / FR-9: never serve RACE on heavy (or plan/review heavy rows) — clamp to FULL."""
    p = str(path or "").strip().upper()
    cx = str(complexity or "").strip().lower()
    ph = str(phase or "").strip().lower()
    if p == "RACE" and (cx == "heavy" or ph in ("plan", "review")):
        return "FULL"
    if p in {"FAST", "CASCADE", "RACE", "FULL"}:
        return p  # type: ignore[return-value]
    return "FULL"


def resolve_path_override(
    zeus: dict[str, Any] | None,
    *,
    policy_module: Any | None = None,
    complexity: str | None = None,
    phase: str | None = None,
) -> PathName | None:
    """Accept Path override args; call policy if present (Agent B). F13 clamp applied."""
    if isinstance(zeus, dict):
        raw = str(zeus.get("path") or zeus.get("Path") or "").strip().upper()
        if raw in {"FAST", "CASCADE", "RACE", "FULL"}:
            cx = complexity or str(zeus.get("complexity") or zeus.get("complexity_band") or "")
            ph = phase or str(zeus.get("phase") or zeus.get("classify_phase") or "")
            return clamp_f13_never_race_on_heavy(raw, complexity=cx, phase=ph)
    mod = policy_module
    if mod is None:
        try:
            from app.fusion import policy as mod  # type: ignore
        except Exception:  # noqa: BLE001
            mod = None
    if mod is None:
        return None
    for name in ("resolve_path", "select_path", "choose_path"):
        fn = getattr(mod, name, None)
        if fn is None:
            continue
        try:
            val = fn(zeus=zeus) if callable(fn) else None
        except TypeError:
            try:
                val = fn()
            except Exception:  # noqa: BLE001
                continue
        except Exception:  # noqa: BLE001
            continue
        if isinstance(val, str) and val.upper() in {"FAST", "CASCADE", "RACE", "FULL"}:
            return clamp_f13_never_race_on_heavy(
                val.upper(), complexity=complexity, phase=phase
            )
        if isinstance(val, dict):
            p = str(val.get("path") or "").upper()
            if p in {"FAST", "CASCADE", "RACE", "FULL"}:
                return clamp_f13_never_race_on_heavy(
                    p, complexity=complexity, phase=phase
                )
    return None
