"""Mini-Verifier (Epic 2) and Aspect-Verifier stubs (Epic 3).

Mini owns CASCADE early-exit: JSON ``{good_enough, confidence, reason}``.
Leader self-score never gates stop (FR-12).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

# Default Mini-Verifier pass threshold (FR-8 assumption).
DEFAULT_MINI_THRESHOLD = 0.8

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass
class MiniVerifyResult:
    good_enough: bool
    confidence: float
    reason: str
    passed: bool
    degraded: bool = False
    raw: dict[str, Any] = field(default_factory=dict)
    threshold: float = DEFAULT_MINI_THRESHOLD


def mini_threshold() -> float:
    raw = (os.environ.get("ZEUS_FUSION_MINI_THRESHOLD") or "").strip()
    if not raw:
        return DEFAULT_MINI_THRESHOLD
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return DEFAULT_MINI_THRESHOLD


def parse_mini_verifier_json(raw: str | dict[str, Any] | None) -> dict[str, Any] | None:
    """Parse Mini-Verifier payload; None on degrade/parse fail."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw).strip()
        if not text:
            return None
        if text.startswith("```"):
            text = _JSON_FENCE_RE.sub("", text).strip()
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                return None
            data = json.loads(text[start : end + 1])
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    if not isinstance(data, dict):
        return None
    if "good_enough" not in data or "confidence" not in data:
        return None
    try:
        conf = float(data.get("confidence"))
    except (TypeError, ValueError):
        return None
    good = data.get("good_enough")
    if not isinstance(good, bool):
        # allow 0/1
        if good in (0, 1, "0", "1", "true", "false", "True", "False"):
            good = str(good).lower() in ("1", "true")
        else:
            return None
    reason = str(data.get("reason") or "")
    return {
        "good_enough": bool(good),
        "confidence": max(0.0, min(1.0, conf)),
        "reason": reason,
    }


_MINI_SYSTEM = (
    "Ты Mini-Verifier Zeus Fusion. Ответ — ТОЛЬКО JSON объект "
    '{"good_enough": bool, "confidence": 0..1, "reason": "..."}. '
    "good_enough=true только если ответ решает user goal без критичных дыр."
)


async def run_mini_verifier(
    *,
    answer: str,
    user_q: str,
    model: str | None = None,
    threshold: float | None = None,
    upstream_call: Any | None = None,
) -> MiniVerifyResult:
    """Call cheap Mini-Verifier model; parse JSON; gate by threshold (FR-8/12).

    Leader self-score is never used. Degrade/parse fail → passed=False (escalate).
    Heuristic fallback when ``ZEUS_FUSION_MINI_HEURISTIC=1`` (tests/offline).
    """
    thr = mini_threshold() if threshold is None else float(threshold)
    if (os.environ.get("ZEUS_FUSION_MINI_HEURISTIC") or "").strip().lower() in (
        "1",
        "true",
        "on",
        "yes",
    ):
        text = (answer or "").strip()
        # Cheap offline oracle: non-empty + not obvious error dump
        ok = bool(text) and len(text) >= 8 and "traceback" not in text.lower()
        return MiniVerifyResult(
            good_enough=ok,
            confidence=0.9 if ok else 0.2,
            reason="heuristic_mini",
            passed=ok,
            degraded=False,
            threshold=thr,
        )

    mid = (model or os.environ.get("ZEUS_FUSION_MINI_MODEL") or "deepseek-v4-flash").strip()
    messages = [
        {"role": "system", "content": _MINI_SYSTEM},
        {
            "role": "user",
            "content": (
                f"User goal:\n{(user_q or '')[:2000]}\n\n"
                f"Candidate answer:\n{(answer or '')[:6000]}"
            ),
        },
    ]
    try:
        if upstream_call is not None:
            data = await upstream_call(model=mid, messages=messages, stream=False, max_tokens=120)
        else:
            from app import upstream

            data = await upstream.chat_completions(
                model=mid, messages=messages, stream=False, max_tokens=120, temperature=0.0
            )
        raw = ""
        if isinstance(data, dict):
            from app import upstream as _up

            raw = _up.extract_text(data)
        else:
            raw = str(data or "")
        return mini_verifier_passed(raw, threshold=thr)
    except Exception as e:  # noqa: BLE001
        return MiniVerifyResult(
            good_enough=False,
            confidence=0.0,
            reason=f"mini_call_failed:{e}"[:200],
            passed=False,
            degraded=True,
            threshold=thr,
        )


# Alias for panel._call_mini discovery
mini_verify = run_mini_verifier


def mini_verifier_passed(
    payload: str | dict[str, Any] | None,
    *,
    threshold: float | None = None,
) -> MiniVerifyResult:
    """Evaluate Mini-Verifier JSON against threshold (≥0.8 default).

    Pass iff ``good_enough`` and ``confidence >= threshold``.
    Parse/schema fail → degraded, not passed (escalate-safe, FR-17).
    """
    thr = mini_threshold() if threshold is None else float(threshold)
    parsed = parse_mini_verifier_json(payload)
    if parsed is None:
        return MiniVerifyResult(
            good_enough=False,
            confidence=0.0,
            reason="mini_verifier_degraded",
            passed=False,
            degraded=True,
            threshold=thr,
        )
    good = bool(parsed["good_enough"])
    conf = float(parsed["confidence"])
    ok = good and conf >= thr
    return MiniVerifyResult(
        good_enough=good,
        confidence=conf,
        reason=str(parsed.get("reason") or ""),
        passed=ok,
        degraded=False,
        raw=parsed,
        threshold=thr,
    )


# ---------------------------------------------------------------------------
# EPIC3-ASPECT
# ---------------------------------------------------------------------------

NEAR_DUPLICATE_TAU = 0.92

AspectName = Literal["correctness", "completeness", "security"]

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9_/#.+-]+", re.UNICODE)


@dataclass
class AspectVerdict:
    aspect: AspectName
    passed: bool
    must: bool = True
    confidence: float = 0.0
    reason: str = ""
    degraded: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class AspectBundle:
    verdicts: list[AspectVerdict] = field(default_factory=list)

    @property
    def must_fail(self) -> bool:
        for v in self.verdicts:
            if v.must and not v.degraded and not v.passed:
                return True
        return False

    @property
    def all_passed(self) -> bool:
        return all(v.passed or v.degraded for v in self.verdicts)


# Back-compat alias for earlier stub name
@dataclass
class AspectVerifyResult:
    aspect: str
    passed: bool
    must_fail: bool = False
    reason: str = ""
    degraded: bool = False
    confidence: float = 0.0


def tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}


def token_jaccard(a: str, b: str) -> float:
    ta, tb = tokenize(a), tokenize(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def near_duplicate_pair(
    a: str, b: str, *, tau: float = NEAR_DUPLICATE_TAU
) -> bool:
    return token_jaccard(a, b) >= tau


def near_duplicate_among(
    texts: list[str], *, tau: float = NEAR_DUPLICATE_TAU
) -> tuple[bool, float]:
    best = 0.0
    clean = [(t or "").strip() for t in texts if (t or "").strip()]
    for i in range(len(clean)):
        for j in range(i + 1, len(clean)):
            s = token_jaccard(clean[i], clean[j])
            if s > best:
                best = s
    return best >= tau, best


def _heuristic_correctness(answer: str, user_q: str) -> AspectVerdict:
    text = (answer or "").strip()
    if not text:
        return AspectVerdict(
            aspect="correctness", passed=False, confidence=0.95, reason="empty_answer"
        )
    low = text.lower()
    if any(
        m in low
        for m in ("i cannot help", "не могу помочь", "as an ai", "ошибка upstream")
    ):
        return AspectVerdict(
            aspect="correctness",
            passed=False,
            confidence=0.8,
            reason="refusal_or_error_marker",
        )
    if len(text) < 24:
        return AspectVerdict(
            aspect="correctness", passed=False, confidence=0.7, reason="too_short"
        )
    overlap = token_jaccard(text, user_q or "")
    conf = 0.55 + min(0.4, overlap)
    return AspectVerdict(
        aspect="correctness",
        passed=True,
        confidence=round(conf, 3),
        reason="heuristic_ok",
    )


def _heuristic_completeness(answer: str, user_q: str) -> AspectVerdict:
    text = (answer or "").strip()
    q = (user_q or "").strip()
    if not text:
        return AspectVerdict(
            aspect="completeness", passed=False, confidence=0.95, reason="empty_answer"
        )
    content = {t for t in tokenize(q) if len(t) >= 5}
    if content:
        covered = len(content & tokenize(text)) / len(content)
        if covered < 0.15 and len(text) < max(80, len(q) // 2):
            return AspectVerdict(
                aspect="completeness",
                passed=False,
                confidence=0.75,
                reason="low_requirement_coverage",
                meta={"coverage": round(covered, 3)},
            )
    if len(text) < 40:
        return AspectVerdict(
            aspect="completeness",
            passed=False,
            confidence=0.7,
            reason="too_short_for_completeness",
        )
    return AspectVerdict(
        aspect="completeness", passed=True, confidence=0.7, reason="heuristic_ok"
    )


def _parse_aspect_json(raw: str, aspect: AspectName) -> AspectVerdict | None:
    text = (raw or "").strip()
    if not text:
        return None
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    passed = bool(data.get("pass") if "pass" in data else data.get("passed"))
    conf = float(data.get("confidence") or 0.0)
    reason = str(data.get("reason") or "")[:400]
    return AspectVerdict(
        aspect=aspect,
        passed=passed,
        must=True,
        confidence=max(0.0, min(1.0, conf)),
        reason=reason or "llm",
    )


def _verdict_to_stub(v: AspectVerdict) -> AspectVerifyResult:
    return AspectVerifyResult(
        aspect=v.aspect,
        passed=v.passed,
        must_fail=bool(v.must and not v.degraded and not v.passed),
        reason=v.reason,
        degraded=v.degraded,
        confidence=v.confidence,
    )


async def verify_aspect(
    aspect: AspectName,
    *,
    answer: str,
    user_q: str,
    call_fn: Any | None = None,
    must: bool = True,
) -> AspectVerdict:
    if call_fn is None:
        if aspect == "correctness":
            v = _heuristic_correctness(answer, user_q)
        elif aspect == "completeness":
            v = _heuristic_completeness(answer, user_q)
        else:
            v = AspectVerdict(
                aspect=aspect,
                passed=True,
                must=False,
                confidence=0.5,
                reason="optional_security_skipped",
                degraded=True,
            )
        v.must = must
        return v

    prompt = (
        f"Aspect={aspect}. Answer pass/fail as JSON "
        '{"pass":bool,"confidence":0-1,"reason":"..."}.\n'
        f"User ask:\n{(user_q or '')[:2000]}\n\n"
        f"Candidate answer:\n{(answer or '')[:6000]}"
    )
    try:
        raw = await call_fn(
            [
                {
                    "role": "system",
                    "content": "You are an Aspect-Verifier. Output JSON only.",
                },
                {"role": "user", "content": prompt},
            ]
        )
        parsed = _parse_aspect_json(str(raw or ""), aspect)
        if parsed is None:
            if aspect == "correctness":
                fb = _heuristic_correctness(answer, user_q)
            else:
                fb = _heuristic_completeness(answer, user_q)
            fb.degraded = True
            fb.reason = f"aspect_degrade:{fb.reason}"
            fb.must = must
            return fb
        parsed.must = must
        return parsed
    except Exception as e:  # noqa: BLE001
        if aspect == "correctness":
            fb = _heuristic_correctness(answer, user_q)
        else:
            fb = _heuristic_completeness(answer, user_q)
        fb.degraded = True
        fb.reason = f"aspect_degrade:{e}"[:400]
        fb.must = must
        return fb


async def run_aspect_verifiers_v1(
    *,
    answer: str,
    user_q: str,
    call_fn: Any | None = None,
    include_security: bool = False,
) -> AspectBundle:
    """MVP Aspects: correctness + completeness (required on FULL)."""
    verdicts = [
        await verify_aspect(
            "correctness", answer=answer, user_q=user_q, call_fn=call_fn, must=True
        ),
        await verify_aspect(
            "completeness", answer=answer, user_q=user_q, call_fn=call_fn, must=True
        ),
    ]
    if include_security:
        verdicts.append(
            await verify_aspect(
                "security",
                answer=answer,
                user_q=user_q,
                call_fn=call_fn,
                must=False,
            )
        )
    return AspectBundle(verdicts=verdicts)


def aspects_block_tau_exit(bundle: AspectBundle | None) -> bool:
    """AD-5 / FR-31: Aspect must-fail blocks near-duplicate early-exit."""
    if bundle is None:
        return False
    return bundle.must_fail


def aspect_verify_correctness(  # EPIC3-ASPECT
    answer: str = "",
    user_q: str = "",
    **_kwargs: Any,
) -> AspectVerifyResult:
    return _verdict_to_stub(_heuristic_correctness(answer, user_q))


def aspect_verify_completeness(  # EPIC3-ASPECT
    answer: str = "",
    user_q: str = "",
    **_kwargs: Any,
) -> AspectVerifyResult:
    return _verdict_to_stub(_heuristic_completeness(answer, user_q))


def run_aspect_verifiers(  # EPIC3-ASPECT
    answer: str = "",
    user_q: str = "",
    **_kwargs: Any,
) -> list[AspectVerifyResult]:
    """Sync helper (heuristics). Prefer ``run_aspect_verifiers_v1`` async in panel."""
    return [
        aspect_verify_correctness(answer, user_q),
        aspect_verify_completeness(answer, user_q),
    ]


# ---------------------------------------------------------------------------
# /EPIC3-ASPECT
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Epic 2 — Unified Gate + Soft-Stop helpers (AD-5 / AD-25)
# ---------------------------------------------------------------------------

SOFT_STOP_RED_LINE = (
    "⚠️ Проверка не пройдена. Ниже — лучший доступный ответ; исправьте и повторите."
)

MAX_ESCALATE_GLOBAL = 2


@dataclass
class GateSignals:
    """Inputs for Unified Gate. ``None`` on tests/build = N/A (not critical)."""

    mini_passed: bool | None = None
    mini_degraded: bool = False
    log_report: Any = "N/A"  # dict | "N/A" | None (called but unparsed)
    parse_degraded: bool = False
    tests_failed: bool | None = None
    build_failed: bool | None = None
    lint_failed: bool = False
    doer_self_score: float | None = None  # never forces GREEN (AD-5)
    allow_green_without_mini: bool = False


@dataclass
class TrustedVerifyResult:
    answer: str
    gate: str  # GREEN | RED
    gate_reasons: list[str]
    escalate_count: int = 0
    soft_stop: bool = False
    log_report: Any = "N/A"
    soft_stop_model: str | None = None
    fix_hint: str = ""
    branches: list[Any] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def append_soft_stop_red_line(answer: str, *, line: str = SOFT_STOP_RED_LINE) -> str:
    body = (answer or "").strip()
    if not body:
        body = "Ответ недоступен после проверки."
    if line in body:
        return body
    return f"{line}\n\n{body}"


def compute_unified_gate(signals: GateSignals) -> tuple[str, list[str]]:
    """Aggregate criticals → RED|GREEN. Lint alone is never critical (FR-6)."""
    reasons: list[str] = []

    # Doer self-score is explicitly ignored for GREEN forcing
    _ = signals.doer_self_score

    if signals.mini_degraded or signals.parse_degraded:
        reasons.append("parse_degrade")
    if signals.mini_passed is False:
        reasons.append("mini_fail")

    lr = signals.log_report
    if lr == "N/A":
        pass  # skip = N/A, not RED (AD-27)
    elif isinstance(lr, dict):
        if "critical" not in lr:
            reasons.append("log_missing_critical")
        elif lr.get("critical") is True:
            reasons.append("log_critical")
        elif not isinstance(lr.get("critical"), bool):
            reasons.append("log_bad_critical")
    elif lr is None:
        # Called but no parseable report → RED (AD-27)
        reasons.append("log_parse_degraded")

    if signals.tests_failed is True:
        reasons.append("tests_failed")
    if signals.build_failed is True:
        reasons.append("build_failed")
    # lint_failed intentionally ignored as sole critical

    if reasons:
        return "RED", reasons

    if signals.mini_passed is True:
        return "GREEN", ["mini_pass"]
    if signals.mini_passed is None and signals.allow_green_without_mini:
        return "GREEN", ["mini_skipped"]
    if signals.mini_passed is None:
        return "RED", ["mini_not_run"]
    return "RED", ["mini_fail"]


def extract_mini_signals_from_outcome(
    *,
    early_exit: str | None,
    routed_by: str | None,
    branches: list[Any] | None,
    disaster: bool = False,
) -> tuple[bool | None, bool]:
    """Return (mini_passed, mini_degraded) from executor outcome."""
    ee = str(early_exit or "").lower()
    rb = str(routed_by or "").lower()
    if "mini_pass" in ee or rb.endswith("mini_pass") or "cascade_mini_pass" in rb:
        return True, False
    if "soft_stop" in ee or "soft_stop" in rb or disaster:
        # soft-stop path: mini did not pass
        deg = False
        for b in branches or []:
            meta = getattr(b, "meta", None) or (b.get("meta") if isinstance(b, dict) else {}) or {}
            if meta.get("mini_reason") == "mini_verifier_degraded" or getattr(
                b, "verifier_degraded", False
            ):
                deg = True
        return False, deg
    # Inspect branch meta from CASCADE
    saw_mini = False
    any_pass = False
    any_deg = False
    for b in branches or []:
        meta = getattr(b, "meta", None) or (b.get("meta") if isinstance(b, dict) else {}) or {}
        if "mini_reason" in meta or getattr(b, "verifier_pass", None) is not None:
            saw_mini = True
        if getattr(b, "verifier_pass", None) is True or meta.get("verifier_pass") is True:
            any_pass = True
        if getattr(b, "verifier_degraded", False) or meta.get("mini_reason") == "mini_verifier_degraded":
            any_deg = True
    if saw_mini:
        # Prefer pass without sticky degrade when any branch clearly passed
        if any_pass:
            return True, False
        return False, any_deg
    if "mini" in rb and ("fail" in rb or "escalate" in rb):
        return False, False
    return None, False


async def run_judge_fix(
    *,
    answer: str,
    user_q: str,
    fix_hint: str,
    model_id: str | None,
    upstream_call: Any | None = None,
) -> tuple[str, int, int]:
    """One escalate/`judge_fix` rewrite. Returns (new_answer, pt, ct)."""
    mid = (model_id or "").strip()
    if not mid:
        return (answer or "").strip(), 0, 0
    if (os.environ.get("ZEUS_FUSION_JUDGE_FIX_HEURISTIC") or "").strip().lower() in (
        "1",
        "true",
        "on",
        "yes",
    ):
        hint = (fix_hint or "").strip()
        base = (answer or "").strip()
        fixed = f"{base}\n\n[judge_fix] {hint}".strip() if hint else f"{base}\n\n[judge_fix] revised"
        return fixed, 0, 12

    messages = [
        {
            "role": "system",
            "content": (
                "Ты judge_fix Zeus Fusion. Исправь ответ по fix_hint. "
                "Верни только исправленный ответ пользователю, без мета-разбора."
            ),
        },
        {
            "role": "user",
            "content": (
                f"User goal:\n{(user_q or '')[:2000]}\n\n"
                f"fix_hint:\n{(fix_hint or 'improve correctness')[:800]}\n\n"
                f"Previous answer:\n{(answer or '')[:6000]}"
            ),
        },
    ]
    try:
        if upstream_call is not None:
            data = await upstream_call(model=mid, messages=messages, stream=False, max_tokens=4096)
        else:
            from app import upstream

            data = await upstream.chat_completions(
                model=mid, messages=messages, stream=False, max_tokens=4096, temperature=0.2
            )
        from app import upstream as _up

        text = _up.extract_text(data) if isinstance(data, dict) else str(data or "")
        pt, ct = _up.extract_usage(data) if isinstance(data, dict) else (0, 0)
        return (text or answer or "").strip(), int(pt or 0), int(ct or 0)
    except Exception:  # noqa: BLE001
        return (answer or "").strip(), 0, 0


async def run_trusted_verify_loop(
    *,
    answer: str,
    user_q: str,
    messages: list[dict[str, Any]] | None = None,
    panel: list[str] | None = None,
    models_by_role: dict[str, str] | None = None,
    curator_model: str | None = None,
    early_exit: str | None = None,
    routed_by: str | None = None,
    branches: list[Any] | None = None,
    disaster: bool = False,
    soft_stop_already: bool = False,
    allow_green_without_mini: bool = False,
    max_escalate: int = MAX_ESCALATE_GLOBAL,
    upstream_call: Any | None = None,
    mini_verify_fn: Any | None = None,
    skip_log: bool = False,
    candidate_answers: list[tuple[str, str]] | None = None,
    tests_failed: bool | None = None,
    build_failed: bool | None = None,
) -> TrustedVerifyResult:
    """Mini signals + Log Analyst + Layer A tests + Gate → escalate≤2 → Soft-Stop.

    ``tests_failed=True`` (Studio Layer A / FR-10/11) forces RED and stays sticky
    across escalate attempts until Soft-Stop. ``None`` = N/A (hot skip).
    """
    from app.fusion.log_analyst import (
        has_error_trigger,
        pick_log_model,
        run_log_analyst,
        should_run_log_analyst,
    )
    from app.fusion.model_power import power_score
    from app.fusion.types import BranchUsage

    mbr = dict(models_by_role or {})
    stack = list(panel or [])
    for mid in mbr.values():
        if mid and mid not in stack:
            stack.append(mid)

    log_report: Any = "N/A"
    fix_hint = ""
    extra_branches: list[BranchUsage] = []

    mini_passed, mini_deg = extract_mini_signals_from_outcome(
        early_exit=early_exit,
        routed_by=routed_by,
        branches=branches,
        disaster=disaster,
    )
    if soft_stop_already:
        mini_passed = False if mini_passed is None else mini_passed

    # Mini model from user stack only — never invent DeepSeek into custom (AD-27)
    mid_mini = mbr.get("mini_verifier") if mbr.get("mini_verifier") in set(stack) else None
    if not mid_mini:
        for m in stack:
            if m:
                mid_mini = m
                break

    # FR-8: if Mini never ran (FULL/RACE), run once before Gate — unless FAST skip allowed
    if mini_passed is None and not allow_green_without_mini and (answer or "").strip():
        if not mid_mini:
            mini_passed = False
            mini_deg = True
        else:
            mini_fn0 = mini_verify_fn or run_mini_verifier
            try:
                try:
                    mini_res0 = await mini_fn0(
                        answer=answer, user_q=user_q, model=mid_mini
                    )
                except TypeError:
                    mini_res0 = await mini_fn0(answer=answer, user_q=user_q)
                mini_passed = bool(getattr(mini_res0, "passed", False))
                mini_deg = bool(getattr(mini_res0, "degraded", False)) and not mini_passed
                extra_branches.append(
                    BranchUsage(
                        model_id=mid_mini,
                        billable_state="completed",
                        prompt_tokens=0,
                        completion_tokens=0,
                        role="mini_verifier",
                        meta={
                            "passed": mini_passed,
                            "reason": str(
                                getattr(mini_res0, "reason", "") or "post_path_mini"
                            ),
                        },
                    )
                )
            except Exception:  # noqa: BLE001
                mini_passed = False
                mini_deg = True

    log_model = pick_log_model(stack, models_by_role=mbr)
    trigger = has_error_trigger(user_q=user_q, answer=answer, messages=messages)
    # Include message history so trigger and analyst see the same evidence
    _hist = ""
    if messages:
        _hist = "\n".join(str(m.get("content") or "") for m in messages[-4:])
    _log_tail = f"{user_q}\n\n{answer}\n\n{_hist}".strip()

    if skip_log:
        log_report = "N/A"
    elif should_run_log_analyst(
        stack_has_log_model=bool(log_model),
        has_error_trigger=trigger,
    ):
        la = await run_log_analyst(
            goal=user_q or _hist[:800],
            log_tail=_log_tail,
            model_id=log_model,
            upstream_call=upstream_call,
        )
        if la.skipped:
            log_report = "N/A"
        elif la.degraded or la.report is None:
            log_report = None  # called but bad → RED
            extra_branches.append(
                BranchUsage(
                    model_id=la.model_id or log_model or "log_analyst",
                    billable_state="completed" if (la.prompt_tokens or la.completion_tokens) else "cancelled_no_tokens",
                    prompt_tokens=la.prompt_tokens,
                    completion_tokens=la.completion_tokens,
                    role="log_analyst",
                    meta={"reason": la.reason, "degraded": True},
                )
            )
        else:
            log_report = la.report
            fix_hint = str(la.report.get("fix_hint") or "")
            extra_branches.append(
                BranchUsage(
                    model_id=la.model_id or log_model or "log_analyst",
                    billable_state="completed",
                    prompt_tokens=la.prompt_tokens,
                    completion_tokens=la.completion_tokens,
                    role="log_analyst",
                    meta={"reason": la.reason, "critical": la.report.get("critical")},
                )
            )
    else:
        log_report = "N/A"

    parse_deg = mini_deg or (log_report is None)

    def _gate(ans: str, mini_ok: bool | None) -> tuple[str, list[str]]:
        _ = ans  # answer text does not clear Layer A / build signals
        return compute_unified_gate(
            GateSignals(
                mini_passed=mini_ok,
                mini_degraded=mini_deg,
                log_report=log_report,
                parse_degraded=parse_deg and log_report is None,
                tests_failed=tests_failed,
                build_failed=build_failed,
                allow_green_without_mini=allow_green_without_mini,
            )
        )

    current = (answer or "").strip()
    gate, reasons = _gate(current, mini_passed)
    escalate_count = 0
    # AD-25: Soft-Stop candidates = post-merge/outcome + judge_fix only.
    # Ignore raw pre-merge doer chunks when a merge/outcome answer exists.
    post_merge = bool(current)
    if post_merge:
        candidates: list[tuple[str, str]] = [
            (curator_model or "answer", current)
        ]
    else:
        candidates = [
            (m, t)
            for m, t in (candidate_answers or [])
            if (t or "").strip()
        ]
        if current:
            candidates.append((curator_model or "answer", current))

    # judge_fix = max power_score in stack (FR-7), prefer role table if in stack
    judge_model = mbr.get("judge_fix") if mbr.get("judge_fix") in set(stack) else None
    if not judge_model and stack:
        judge_model = max(stack, key=power_score)
    judge_model = judge_model or curator_model

    while gate == "RED" and escalate_count < max(0, int(max_escalate)):
        escalate_count += 1
        new_ans, pt, ct = await run_judge_fix(
            answer=current,
            user_q=user_q,
            fix_hint=fix_hint or "Исправь критические ошибки в ответе.",
            model_id=judge_model,
            upstream_call=upstream_call,
        )
        if new_ans:
            current = new_ans
            candidates.append((judge_model or "judge_fix", current))
        extra_branches.append(
            BranchUsage(
                model_id=judge_model or "judge_fix",
                billable_state="completed" if (pt or ct or new_ans) else "cancelled_no_tokens",
                prompt_tokens=pt,
                completion_tokens=ct,
                role="judge_fix",
                meta={"escalate": escalate_count, "fix_hint": fix_hint[:200]},
            )
        )
        # Re-check mini on revised answer; clear sticky degrade on clean pass
        mini_fn = mini_verify_fn or run_mini_verifier
        try:
            if mid_mini:
                try:
                    mini_res = await mini_fn(
                        answer=current, user_q=user_q, model=mid_mini
                    )
                except TypeError:
                    mini_res = await mini_fn(answer=current, user_q=user_q)
            else:
                mini_res = await mini_fn(answer=current, user_q=user_q)
            mini_ok = bool(getattr(mini_res, "passed", False))
            if getattr(mini_res, "degraded", False):
                mini_deg = True
            elif mini_ok:
                mini_deg = False
        except Exception:  # noqa: BLE001
            mini_ok = False
            mini_deg = True
        # Re-evaluate / re-arm Log against fixed answer (FR-6 / AD-27)
        ans_has_err = has_error_trigger(user_q="", answer=current)
        should_relog = bool(log_model) and (
            (log_report not in ("N/A",) and log_report is not None)
            or (log_report == "N/A" and ans_has_err)
            or (log_report is None)
        )
        if should_relog:
            la2 = await run_log_analyst(
                goal=user_q or "",
                log_tail=current,
                model_id=log_model,
                upstream_call=upstream_call,
            )
            if la2.skipped:
                if not ans_has_err and isinstance(log_report, dict):
                    log_report = dict(log_report)
                    log_report["critical"] = False
            elif la2.degraded or la2.report is None:
                log_report = None  # called but bad → RED (do not keep stale critical)
            else:
                log_report = la2.report
                fix_hint = str(la2.report.get("fix_hint") or fix_hint)
        elif isinstance(log_report, dict) and log_report.get("critical") and not ans_has_err:
            log_report = dict(log_report)
            log_report["critical"] = False
        parse_deg = mini_deg or (log_report is None)
        gate, reasons = _gate(current, mini_ok)
        if gate == "GREEN":
            break

    soft_stop = False
    soft_model: str | None = None
    if soft_stop_already:
        # Brownfield soft-stop terminal cannot silently become GREEN
        gate = "RED"
        if "soft_stop" not in reasons:
            reasons = list(reasons) + ["soft_stop_terminal"]
        soft_stop = True
    if gate == "RED":
        # Soft-Stop: max power_score among post-merge candidates; tie → latest (AD-25)
        soft_stop = True
        if candidates:
            best_score = -1
            best_mid, best_text = candidates[0]
            for mid, text in candidates:
                if not (text or "").strip():
                    continue
                sc = power_score(mid)
                if sc >= best_score:
                    best_score = sc
                    best_mid, best_text = mid, text
            current = append_soft_stop_red_line(best_text)
            soft_model = best_mid
        else:
            current = append_soft_stop_red_line(current)
            soft_model = curator_model
        if "soft_stop" not in reasons:
            reasons = list(reasons) + ["soft_stop"]
        gate = "RED"

    return TrustedVerifyResult(
        answer=current,
        gate=gate,
        gate_reasons=reasons,
        escalate_count=escalate_count,
        soft_stop=soft_stop,
        log_report=log_report,
        soft_stop_model=soft_model,
        fix_hint=fix_hint,
        branches=extra_branches,
        meta={
            "max_escalate": max_escalate,
            "tests_failed": tests_failed,
            "build_failed": build_failed,
        },
    )
