"""Mini-Verifier (Epic 2) and Aspect-Verifier stubs (Epic 3).

Mini owns CASCADE early-exit: JSON ``{good_enough, confidence, reason}``.
Leader self-score never gates stop (FR-12).
"""

from __future__ import annotations

import json
import hashlib
import math
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

    mid = (model or os.environ.get("ZEUS_FUSION_MINI_MODEL") or "deepseek-v4-pro").strip()
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
    """Inputs for Unified Gate. ``None`` on tests/build = N/A (not critical).

    Machine signals (TZ §5.3) dominate «готово» when present.
    """

    mini_passed: bool | None = None
    mini_degraded: bool = False
    log_report: Any = "N/A"  # dict | "N/A" | None (called but unparsed)
    parse_degraded: bool = False
    tests_failed: bool | None = None
    build_failed: bool | None = None
    lint_failed: bool = False
    doer_self_score: float | None = None  # never forces GREEN (AD-5)
    allow_green_without_mini: bool = False
    # Machine truth from client hands / local exec
    patch_applied: bool | None = None
    files_touched_ok: bool | None = None
    command_exit_nonzero: bool | None = None
    compile_failed: bool | None = None  # py_compile / tsc
    ui_broken: bool | None = None  # vision ui_report


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


# Mini/parse/log-shape issues — advisory when doer already produced a usable answer
_SOFT_GATE_REASONS = frozenset(
    {
        "parse_degrade",
        "mini_fail",
        "mini_not_run",
        "log_parse_degraded",
        "log_missing_critical",
        "log_bad_critical",
    }
)


def answer_looks_usable(answer: str, user_q: str = "") -> bool:
    """Heuristic: doer delivered something shippable — don't Soft-Stop banner it."""
    t = (answer or "").strip()
    if len(t) < 24:
        return False
    if t.lstrip().startswith("⚠️") or "Проверка не пройдена" in t[:80]:
        return False
    low_q = (user_q or "").lower()
    low = t.lower()
    wants_code = any(
        x in low_q
        for x in (
            "код",
            "css",
            "html",
            "fix",
            "import",
            "функц",
            "```",
            ".py",
            "jwt",
            "кнопк",
            "hero",
            "landing",
            "лендинг",
            "review",
            "ревью",
            "баг",
        )
    )
    if wants_code:
        if "```" in t:
            return True
        if any(
            x in low
            for x in (
                "color:",
                "background",
                "import ",
                "def ",
                "<!doctype",
                "<html",
                "pip install",
                "race",
                "lock",
                "atomic",
            )
        ):
            return True
        return len(t) >= 80
    return len(t) >= 60


def compute_unified_gate(signals: GateSignals) -> tuple[str, list[str]]:
    """Aggregate criticals → RED|GREEN. Lint alone is never critical (FR-6).

    Hard machine fails (tests/build/compile/patch/ui) always RED.
    GREEN requires mini pass (or allow_green_without_mini) AND no machine red.
    """
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
    if signals.compile_failed is True:
        reasons.append("compile_failed")
    if signals.patch_applied is False:
        reasons.append("patch_not_applied")
    if signals.files_touched_ok is False:
        reasons.append("files_out_of_plan")
    if signals.command_exit_nonzero is True:
        reasons.append("command_exit_nonzero")
    if signals.ui_broken is True:
        reasons.append("ui_broken")
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


def machine_signals_from_client(meta: dict[str, Any] | None) -> dict[str, Any]:
    """Map client/zeus execution meta → GateSignals kwargs."""
    m = meta if isinstance(meta, dict) else {}
    exec_ = m.get("exec") if isinstance(m.get("exec"), dict) else m

    def _tri(key: str) -> bool | None:
        if key not in exec_ and key not in m:
            return None
        v = exec_.get(key, m.get(key))
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in ("true", "1", "yes", "on", "pass", "passed"):
                return True
            if normalized in ("false", "0", "no", "off", "fail", "failed"):
                return False
        if isinstance(v, (int, float)) and v in (0, 1):
            return bool(v)
        return None

    tests_ok = _tri("tests_ok")
    build_ok = _tri("build_ok")
    compile_ok = _tri("compile_ok")
    patch_ok = _tri("patch_applied")
    files_ok = _tri("files_touched_ok")
    exit_ok = _tri("command_ok")
    exit_nonzero: bool | None = None
    has_exit_code = "exit_code" in exec_ or "exit_code" in m
    if has_exit_code:
        raw_exit = exec_.get("exit_code", m.get("exit_code"))
        if isinstance(raw_exit, (int, float)) and not isinstance(raw_exit, bool):
            numeric_exit = float(raw_exit)
            if math.isfinite(numeric_exit):
                exit_nonzero = numeric_exit != 0
        elif isinstance(raw_exit, str):
            try:
                numeric_exit = float(raw_exit.strip())
                if math.isfinite(numeric_exit):
                    exit_nonzero = numeric_exit != 0
            except (TypeError, ValueError):
                pass
    ui_ok = _tri("ui_ok")

    return {
        "tests_failed": (False if tests_ok is True else True if tests_ok is False else None),
        "build_failed": (False if build_ok is True else True if build_ok is False else None),
        "compile_failed": (
            False if compile_ok is True else True if compile_ok is False else None
        ),
        "patch_applied": patch_ok,
        "files_touched_ok": files_ok,
        "command_exit_nonzero": (
            exit_nonzero
            if has_exit_code
            else False
            if exit_ok is True
            else True
            if exit_ok is False
            else None
        ),
        "ui_broken": (False if ui_ok is True else True if ui_ok is False else None),
    }


_RETURN_CODE_RE = re.compile(
    r"(?i)(?:<returncode>\s*|(?:exit|return)_?code\s*[=:]\s*)(-?\d+)"
)
_TEST_COMMAND_RE = re.compile(
    r"(?i)^(?:"
    r"(?:python(?:\d+(?:\.\d+)?)?\s+-m\s+)?(?:[\w./-]*/)?pytest\b|"
    r"(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?test\b|"
    r"(?:cargo|go)\s+test\b|"
    r"(?:python(?:\d+(?:\.\d+)?)?\s+-m\s+)?unittest\b|"
    r"tox\b|nox\b"
    r")"
)
_BUILD_COMMAND_RE = re.compile(
    r"(?i)(?:^|[;&|]\s*)(?:"
    r"(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?build\b|"
    r"cargo\s+build\b|go\s+build\b|"
    r"python(?:\d+(?:\.\d+)?)?\s+-m\s+py_compile\b"
    r")"
)
_MUTATING_TOOL_RE = re.compile(
    r"(?i)(?:edit|write|patch|apply_patch|replace|create_file|delete_file)"
)
_MUTATING_COMMAND_RE = re.compile(
    r"(?i)(?:^|[;&|]\s*)(?:"
    r"apply_patch\b|patch\b|"
    r"(?:cp|mv|rm|mkdir|touch|chmod|chown|ln)\b|"
    r"(?:sed|perl)\s+-i\b|tee\b|xargs\b|"
    r"(?:ruff|black|prettier|isort)\b.*(?:--fix|\s+\.)|"
    r"git\s+(?:apply|checkout|restore|reset|clean|stash|commit|merge|rebase)\b|"
    r"(?:pip|pip3|python(?:\d+(?:\.\d+)?)?\s+-m\s+pip)\s+(?:install|uninstall)\b|"
    r"(?:make|python(?:\d+(?:\.\d+)?)?\s+setup\.py)\b|"
    r"(?:^|[^<>])(?:>>|>)\s*[\w./-]+"
    r")"
)
# Writes hidden inside an interpreter one-liner or a heredoc still mutate the
# tree even though the leading token looks harmless.
_SCRIPTED_WRITE_RE = re.compile(
    r"(?i)(?:"
    r"<<\s*[\"']?\w+|"
    r"\.write(?:_text|_bytes|lines)?\s*\(|"
    r"open\s*\([^)]*[\"'][arw]\+?[bt]?[\"']|"
    r"(?:shutil|pathlib|os)\.(?:copy|move|remove|unlink|rename|makedirs|mkdir)|"
    r"fs\.(?:write|append|unlink|rm)"
    r")"
)
_REDIRECT_WRITE_RE = re.compile(r"(?:^|[^<>&\d])(?:>>|>)\s*[\w./-]+")
_READ_ONLY_HEAD_RE = re.compile(
    r"^(?:"
    r"ls|pwd|rg|grep|egrep|fgrep|cat|head|tail|wc|stat|file|which|type|"
    r"nl|tree|du|df|basename|dirname|realpath|readlink|"
    r"sort|uniq|cut|tr|diff|cmp|date|echo|"
    r"md5sum|sha1sum|sha256sum|"
    r"git\s+(?:status|diff|log|show|rev-parse|ls-files|branch|blame)|"
    r"python(?:\d+(?:\.\d+)?)?\s+--version|"
    r"(?:pip|pip3)\s+(?:show|list|freeze)"
    r")(?:\s|$)",
    re.IGNORECASE,
)
_FIND_MUTATION_RE = re.compile(
    r"(?i)(?:^|\s)-(?:delete|exec|execdir|ok|okdir|fls|fprint|fprintf)\b"
)
_PYTEST_FAILURE_RE = re.compile(
    r"(?im)(?:^|\n)(?:FAILED\b|ERROR\b|=+\s*\d+\s+failed\b|"
    r"\d+\s+failed(?:,|\s|$)|short test summary info)"
)
_SUSPICIOUS_WARNING_RE = re.compile(
    r"(?im)(?:^|\n).*(?:warning:|warnings summary|deprecated|resourcewarning)"
)
_MASKED_TEST_FAILURE_RE = re.compile(
    r"(?i)(?:"
    r"\|\|\s*(?:true\b|:|exit\s+0\b)|"
    r"\|&?\s*(?:true\b|:)|"
    r";\s*(?:true|exit\s+0)(?:\s*[;);&|]|\s*$)|"
    r"set\s+\+(?:e|o\s+errexit)"
    r")"
)
_SUBMIT_MARKER = "complete_task_and_submit_final_output"


def _safe_nonnegative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, parsed)


def _tool_output_payload(output: str) -> str:
    match = re.search(r"(?is)<output>(.*?)</output>", output)
    payload = match.group(1) if match else output
    payload = re.sub(
        r"(?is)<returncode>\s*-?\d+\s*</returncode>", "", payload
    )
    return payload.strip()


def sanitize_evidence_text(value: Any, *, max_chars: int = 3000) -> str:
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(value or ""))
    text = re.sub(
        r"(?i)\b(?:bearer\s+)?(?:zeus_|sk-|ghp_|github_pat_)[A-Za-z0-9._-]{12,}",
        "[REDACTED_SECRET]",
        text,
    )
    # An auth header carries "Scheme Credentials", so the value runs to the
    # end of the line rather than to the next space.
    text = re.sub(
        r"(?i)\b(authorization)\s*[=:]\s*[^\n\r'\"]+",
        r"\1=[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password|passwd)\s*[=:]\s*\S+",
        r"\1=[REDACTED]",
        text,
    )
    # Credentials embedded in a URL survive the key=value pass above.
    text = re.sub(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@", r"\1[REDACTED]@", text)
    return text[-max(0, max_chars) :]


def _command_runs_test(command: str) -> bool:
    for segment in re.split(r"\s*(?:&&|\|\||;|\|)\s*", command or ""):
        candidate = segment.strip()
        candidate = re.sub(
            r"^(?:(?:env\s+)?(?:[A-Za-z_]\w*=\S+\s+)+)", "", candidate
        )
        candidate = re.sub(r"^(?:env|sudo)\s+", "", candidate)
        candidate = re.sub(r"^timeout\s+\S+\s+", "", candidate)
        if _TEST_COMMAND_RE.search(candidate):
            return True
    return False


def _command_is_clearly_read_only(command: str) -> bool:
    """Inspection commands must not be mistaken for edits.

    Treating every unrecognized command as a write is what kept the diff
    permanently dirty, so the common read verbs are recognized explicitly and
    the write-ish escapes (redirects, in-place flags, scripted writes) are
    rejected up front.
    """
    text = command or ""
    if not text.strip():
        return False
    if (
        _REDIRECT_WRITE_RE.search(text)
        or _SCRIPTED_WRITE_RE.search(text)
        or re.search(r"[<>]\(", text)
    ):
        return False
    segments = [
        part.strip()
        for part in re.split(r"\s*(?:&&|\|\||;|\|)\s*", text)
        if part.strip()
    ]
    if not segments:
        return False
    for segment in segments:
        if re.match(r"^cd\s+\S+$", segment):
            continue
        if re.search(r"(?i)(?:^|\s)--output(?:=|\s)", segment):
            return False
        if re.match(r"^(?:sed|awk)\b", segment, flags=re.IGNORECASE):
            if re.search(r"(?i)(?:^|\s)-(?:-in-?place|\w*i)", segment):
                return False
            continue
        if re.match(r"^find\b", segment, flags=re.IGNORECASE):
            if _FIND_MUTATION_RE.search(segment):
                return False
            continue
        if not _READ_ONLY_HEAD_RE.match(segment):
            return False
    return True


def validate_test_command(command: str | None) -> str:
    """Allow one direct test command, never an LLM-authored shell program."""
    candidate = " ".join(str(command or "").strip().split())
    if not candidate or len(candidate) > 2000:
        return ""
    if re.search(r"[\n\r;&|><`]|\$\(|\${", candidate):
        return ""
    if re.match(r"^(?:sudo|doas|su|env)\b", candidate, flags=re.IGNORECASE):
        return ""
    if re.search(
        r"(?i)(?:^|\s)--(?:base|baset\w*|rootd\w*)(?:=|\s)",
        candidate,
    ):
        return ""
    return candidate if _command_runs_test(candidate) else ""


_SOURCE_PATH_RE = re.compile(r"^[\w][\w./-]*\.(?:py|pyi|js|ts|tsx|jsx|go|rs)$")


def _remember_source_path(evidence: dict[str, Any], path: str) -> None:
    candidate = str(path or "").strip()
    while candidate.startswith("./"):
        candidate = candidate[2:]
    # A path arrives from client-controlled diff text, so it may only ever be a
    # plain in-repository file: no escapes, no absolute targets.
    if (
        not candidate
        or len(candidate) > 200
        or candidate.startswith("/")
        or ".." in candidate.split("/")
        or not _SOURCE_PATH_RE.match(candidate)
    ):
        return
    known = [
        str(value)
        for value in evidence.get("changed_paths", [])
        if isinstance(value, str)
    ]
    if candidate in known:
        return
    evidence["changed_paths"] = [*known, candidate][-20:]


def _latest_change_seq(evidence: dict[str, Any]) -> int:
    """Newest sequence after which a green test must be re-run."""
    return max(
        _safe_nonnegative_int(evidence.get("diff_seq")),
        _safe_nonnegative_int(evidence.get("write_seq")),
    )


def _plan_line_candidates(line: str) -> list[str]:
    raw = line.strip()
    candidates = [match.strip() for match in re.findall(r"`([^`]+)`", raw)]
    bare = re.sub(r"^[-*+\d.)\s]+", "", raw).strip().strip("`")
    candidates.append(re.sub(r"^\$\s*", "", bare).strip())
    tail = re.search(r"(?i)\b((?:python\S*\s+-m\s+)?pytest\b.*)$", raw)
    if tail:
        candidates.append(tail.group(1).strip().strip("`"))
    return candidates


def plan_test_command(plan: str | None) -> str:
    """Recover a runnable test command from the leader's plan text."""
    for line in str(plan or "").splitlines():
        for candidate in _plan_line_candidates(line):
            validated = validate_test_command(candidate)
            if validated:
                return validated
    return ""


def conventional_test_commands(paths: list[str] | None) -> list[str]:
    """Derive conventional test targets for the files the diff touched."""
    candidates: list[str] = []
    for raw in paths or []:
        path = str(raw or "").strip()
        if not path.endswith((".py", ".pyi")):
            continue
        parts = [part for part in path.split("/") if part]
        if not parts:
            continue
        name = parts[-1]
        package = "/".join(parts[:-1])
        if name.startswith("test_") or "tests" in parts[:-1]:
            candidates.append(f"python -m pytest -q {path}")
            continue
        if package:
            candidates.append(f"python -m pytest -q {package}/tests/test_{name}")
            candidates.append(f"python -m pytest -q {package}/tests")
    unique: list[str] = []
    for candidate in candidates:
        validated = validate_test_command(candidate)
        if validated and validated not in unique:
            unique.append(validated)
    return unique[:6]


def derive_test_command(
    evidence: dict[str, Any] | None,
    *,
    plan_digest: str | None = None,
    remembered: list[str] | None = None,
) -> tuple[str, str]:
    """Resolve the next test command to request; never return an empty gate ask.

    Order: the verifier's plan, then commands this project already proved green,
    then the leader's plan, then the conventional test path for the changed
    files. Returns ``(command, source)``.
    """
    ev = evidence if isinstance(evidence, dict) else {}
    tried = {
        " ".join(str(value).split())
        for value in ev.get("test_commands_tried", [])
        if isinstance(value, str)
    }
    planned = validate_test_command(ev.get("test_plan_command"))
    # Re-asking for a command the client already ran without success just
    # repeats the same dead end, so exhausted candidates fall through.
    if planned and " ".join(planned.split()) not in tried:
        # Keep the original provenance so telemetry does not credit the verifier
        # for a command the deterministic chain produced.
        return planned, str(ev.get("test_plan_source") or "test_verifier")
    for raw in remembered or []:
        candidate = validate_test_command(raw)
        if candidate and " ".join(candidate.split()) not in tried:
            return candidate, "project_memory"
    from_plan = plan_test_command(plan_digest)
    if from_plan and " ".join(from_plan.split()) not in tried:
        return from_plan, "leader_plan"
    for candidate in conventional_test_commands(
        [
            str(value)
            for value in ev.get("changed_paths", [])
            if isinstance(value, str)
        ]
    ):
        if " ".join(candidate.split()) not in tried:
            return candidate, "changed_paths"
    return "", ""


def _tool_call_command(call: dict[str, Any]) -> tuple[str, str]:
    fn = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = str(fn.get("name") or call.get("name") or "")
    raw = fn.get("arguments", call.get("arguments"))
    args: dict[str, Any] = {}
    if isinstance(raw, dict):
        args = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                args = parsed
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    command = str(
        args.get("command")
        or args.get("cmd")
        or args.get("script")
        or args.get("patch")
        or args.get("path")
        or ""
    )
    return name, command


def _tool_return_code(message: dict[str, Any], output: str) -> int | None:
    try:
        structured = json.loads(output)
        if isinstance(structured, dict):
            for key in ("returncode", "return_code", "exit_code"):
                value = structured.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    return value
                if isinstance(value, float) and value.is_integer():
                    return int(value)
                if isinstance(value, str) and value.strip().lstrip("-").isdigit():
                    return int(value.strip())
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    for source in (
        message,
        message.get("meta") if isinstance(message.get("meta"), dict) else {},
    ):
        for key in ("returncode", "return_code", "exit_code"):
            value = source.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            if isinstance(value, float) and value.is_integer():
                return int(value)
            if isinstance(value, str) and value.strip().lstrip("-").isdigit():
                return int(value.strip())
    match = _RETURN_CODE_RE.search(output)
    return int(match.group(1)) if match else None


def collect_tool_evidence(
    messages: list[dict[str, Any]] | None,
    prior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministically persist diff/test/build evidence from client tool results.

    Sequence numbers are logical event counters, not wall-clock timestamps. Replayed
    OpenAI transcripts are idempotent through bounded fingerprints.
    """
    evidence = dict(prior or {})
    seen = [
        str(value)
        for value in evidence.get("tool_event_fingerprints", [])
        if isinstance(value, str)
    ][-512:]
    seen_set = set(seen)
    counter = max(
        _safe_nonnegative_int(evidence.get("tool_event_seq")),
        _safe_nonnegative_int(evidence.get("diff_seq")),
        _safe_nonnegative_int(evidence.get("test_seq")),
        _safe_nonnegative_int(evidence.get("build_seq")),
    )
    calls: dict[str, tuple[str, str]] = {}
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        if str(message.get("role") or "").lower() == "assistant":
            for call in message.get("tool_calls") or []:
                if isinstance(call, dict):
                    call_id = str(call.get("id") or "")
                    if call_id:
                        calls[call_id] = _tool_call_command(call)
            legacy_call = message.get("function_call")
            if isinstance(legacy_call, dict):
                legacy_id = str(message.get("id") or legacy_call.get("name") or "")
                if legacy_id:
                    calls[legacy_id] = _tool_call_command(legacy_call)
            continue
        if str(message.get("role") or "").lower() not in ("tool", "function"):
            continue
        output = str(message.get("content") or "")
        call_id = str(message.get("tool_call_id") or message.get("name") or "")
        tool_name, command = calls.get(
            call_id,
            (str(message.get("name") or ""), str(message.get("command") or "")),
        )
        fingerprint = hashlib.sha256(
            f"{call_id}\0{tool_name}\0{command}\0{output}".encode(
                "utf-8", errors="replace"
            )
        ).hexdigest()[:24]
        if fingerprint in seen_set:
            continue
        counter += 1
        seen.append(fingerprint)
        seen_set.add(fingerprint)
        return_code = _tool_return_code(message, output)
        output_payload = _tool_output_payload(output)
        low_name = tool_name.lower()
        is_test = _command_runs_test(command)
        is_build = bool(_BUILD_COMMAND_RE.search(command))
        is_diff = bool(
            re.search(r"(?i)\bgit\s+diff\b", command)
            or re.search(r"(?m)^diff --git ", output)
        )
        diff_nonempty = bool(
            re.search(r"(?m)^diff --git ", output_payload)
            or (
                is_diff
                and bool(output_payload.strip())
            )
        )
        shell_like = low_name in ("bash", "shell", "terminal", "exec", "command")
        # Only recognized writes invalidate the diff. Unrecognized commands are
        # merely untrusted for green-test freshness, which keeps inspection
        # commands from erasing a real diff.
        unknown_shell_write = bool(
            shell_like
            and return_code in (None, 0)
            and not is_test
            and not is_build
            and not is_diff
            and not _command_is_clearly_read_only(command)
        )
        mutates = bool(
            _MUTATING_TOOL_RE.search(low_name)
            or _MUTATING_COMMAND_RE.search(command)
            or _SCRIPTED_WRITE_RE.search(command)
            or _REDIRECT_WRITE_RE.search(command)
        )
        mutation_succeeded = mutates and return_code in (None, 0)
        if unknown_shell_write and not mutation_succeeded:
            evidence["write_seq"] = counter
        if mutation_succeeded:
            evidence["diff_seq"] = counter
            evidence["diff_dirty"] = True
            evidence["diff_nonempty"] = False
            for token in re.findall(r"[\w./-]+\.(?:py|pyi|js|ts|tsx|jsx|go|rs)\b", command):
                _remember_source_path(evidence, token)
        elif is_diff and diff_nonempty:
            diff_fingerprint = hashlib.sha256(
                output_payload.encode("utf-8", errors="replace")
            ).hexdigest()[:32]
            if diff_fingerprint != evidence.get("diff_fingerprint"):
                evidence["diff_seq"] = counter
            evidence["diff_fingerprint"] = diff_fingerprint
            evidence["diff_nonempty"] = True
            evidence["diff_dirty"] = False
            for _, changed in re.findall(
                r"(?m)^diff --git a/(\S+) b/(\S+)", output_payload
            ):
                _remember_source_path(evidence, changed)
        elif is_diff and not diff_nonempty and re.search(
            r"(?i)\bgit\s+diff(?:\s+--(?:no-ext-diff|binary|exit-code))*\s*$",
            command.strip(),
        ):
            evidence["diff_nonempty"] = False
            evidence["diff_dirty"] = False
            evidence.pop("diff_fingerprint", None)
        if is_test:
            failed_summary = bool(_PYTEST_FAILURE_RE.search(output))
            planned = str(evidence.get("test_plan_command") or "").strip()
            normalized_command = " ".join(command.split())
            normalized_plan = " ".join(planned.split())
            non_executing = bool(
                re.search(
                    r"(?i)(?:^|\s)(?:--version|--help|--collect-only)(?:\s|$)",
                    command,
                )
            )
            relevant = bool(normalized_plan) and not non_executing and (
                normalized_command == normalized_plan
                or normalized_command.endswith(f"&& {normalized_plan}")
            )
            masked_failure = bool(_MASKED_TEST_FAILURE_RE.search(command))
            green = (
                return_code == 0
                and not failed_summary
                and not masked_failure
                and relevant
            )
            tried = [
                str(value)
                for value in evidence.get("test_commands_tried", [])
                if isinstance(value, str)
            ]
            normalized_tried = " ".join(command.split())[:400]
            if normalized_tried and normalized_tried not in tried:
                tried.append(normalized_tried)
            evidence.update(
                {
                    "test_seq": counter,
                    "test_command": command[:2000],
                    "test_green": green,
                    "test_relevant": relevant,
                    "tests_failed": not green,
                    "test_commands_tried": tried[-10:],
                }
            )
        if is_build:
            green = return_code == 0
            evidence.update(
                {
                    "build_seq": counter,
                    "build_command": command[:2000],
                    "build_green": green,
                    "build_failed": not green,
                }
            )
        significant = bool(
            (return_code is not None and return_code != 0)
            or _PYTEST_FAILURE_RE.search(output)
            or re.search(r"(?im)(?:^|\n)\s*(?:traceback|fatal:|exception\b)", output)
            or _SUSPICIOUS_WARNING_RE.search(output)
            or is_test
            or is_build
        )
        event_failed = bool(
            (return_code is not None and return_code != 0)
            or (is_test and not evidence.get("test_green"))
            or (is_build and not evidence.get("build_green"))
            or _PYTEST_FAILURE_RE.search(output)
            or re.search(
                r"(?im)(?:^|\n)\s*(?:traceback\s*(?:\(|:)|fatal:)", output
            )
        )
        # A red flag describes the newest observation only. Without this decay a
        # single early failure kept the analyst attached to every later turn.
        evidence["last_event_failed"] = event_failed
        evidence["command_exit_nonzero"] = bool(
            return_code is not None and return_code != 0
        )
        evidence["last_tool_event"] = {
            "seq": counter,
            "tool": tool_name[:120],
            "command": sanitize_evidence_text(command, max_chars=1200),
            "return_code": return_code,
            "is_test": is_test,
            "is_build": is_build,
            "is_diff": is_diff,
            "diff_nonempty": diff_nonempty,
            "mutates_diff": mutation_succeeded,
            "failed": event_failed,
            "significant": significant,
            "output_tail": sanitize_evidence_text(output, max_chars=3000),
        }
    evidence["tool_event_seq"] = counter
    evidence["tool_event_fingerprints"] = seen[-512:]
    test_seq = _safe_nonnegative_int(evidence.get("test_seq"))
    evidence["fresh_green_test"] = bool(
        evidence.get("diff_nonempty")
        and evidence.get("test_green") is True
        and evidence.get("test_relevant") is True
        and test_seq > _latest_change_seq(evidence)
    )
    return evidence


def is_submit_tool_call(call: dict[str, Any] | None) -> bool:
    """Recognize client completion markers without depending on mini-swe names."""
    if not isinstance(call, dict):
        return False
    fn = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = str(fn.get("name") or call.get("name") or "").strip()
    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", name).replace("-", "_").lower()
    if bool(
        re.search(
            r"(?:^|_)(?:submit|finish|finalize|complete|completion)(?:_|$)",
            normalized,
        )
    ):
        return True
    _, command = _tool_call_command(call)
    raw_arguments = fn.get("arguments", call.get("arguments"))
    raw_text = (
        raw_arguments
        if isinstance(raw_arguments, str)
        else json.dumps(raw_arguments, ensure_ascii=False, default=str)
        if isinstance(raw_arguments, dict)
        else ""
    )
    if _SUBMIT_MARKER in f"{command}\n{raw_text}".lower():
        return True
    if re.search(
        r"(?i)(?:^|[;&|])\s*(?:(?:sh|bash|python(?:\d+(?:\.\d+)?)?)\s+)?"
        r"(?:\./|[\w./-]*/)?(?:submit|submit_and_exit|finalize|complete)"
        r"(?:\.(?:sh|py))?(?:\s|$)",
        command,
    ):
        return True
    return command.strip().lower() in {
        "submit",
        "finish",
        "finalize",
        "complete",
        "submit_and_exit",
    }


def is_mutating_tool_call(call: dict[str, Any] | None) -> bool:
    if not isinstance(call, dict):
        return False
    name, command = _tool_call_command(call)
    return bool(
        _MUTATING_TOOL_RE.search(name)
        or _MUTATING_COMMAND_RE.search(command)
        or re.search(r"(?:>>|>)\s*[\w./-]+", command)
    )


def pre_submit_gate(evidence: dict[str, Any] | None) -> tuple[str, list[str]]:
    """Require a non-empty diff and a relevant green test newer than that diff."""
    ev = evidence if isinstance(evidence, dict) else {}
    reasons: list[str] = []
    if not ev.get("diff_nonempty"):
        reasons.append("diff_empty")
    if ev.get("test_green") is not True:
        reasons.append("relevant_test_not_green")
    elif ev.get("test_relevant") is not True:
        reasons.append("test_not_relevant_to_diff")
    elif _safe_nonnegative_int(ev.get("test_seq")) <= _latest_change_seq(ev):
        reasons.append("green_test_stale_after_diff")
    return ("GREEN", ["fresh_green_test"]) if not reasons else ("RED", reasons)


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


_ARCHITECT_WATCH_SYSTEM = (
    "Ты Architect ZeusCode (главный мозг экипажа). Оцени ответ doer vs цель. "
    "НЕ пиши новый код целиком. Ответ — ТОЛЬКО JSON:\n"
    '{"ok":true|false,"score":0.0-1.0,"issues":["..."],"fix_hint":"..."}\n'
    "ok=false если ответ мимо цели, опасен, обрезан или явная халтура."
)

_TEST_SPOT_SYSTEM = (
    "Ты Test Author ZeusCode. По цели и ответу doer дай короткие checks. "
    "Ответ — ТОЛЬКО JSON:\n"
    '{"ok":true|false,"checks":["..."],"fix_hint":"..."}\n'
    "ok=false если явные дыры в контракте/acceptance."
)


def _extract_watch_json(raw: str | dict[str, Any] | None) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
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
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


async def run_architect_watch(
    *,
    answer: str,
    user_q: str,
    model_id: str | None,
    upstream_call: Any | None = None,
) -> tuple[bool, str, int, int]:
    """Opus (architect) evaluates doer output. Returns (ok, fix_hint, pt, ct)."""
    mid = (model_id or "").strip()
    if not mid or not (answer or "").strip():
        return True, "", 0, 0
    if (os.environ.get("ZEUS_FUSION_WATCH_HEURISTIC") or "").strip().lower() in (
        "1",
        "true",
        "on",
        "yes",
    ):
        ok = len((answer or "").strip()) >= 40
        return ok, ("" if ok else "answer_too_short"), 0, 4

    messages = [
        {"role": "system", "content": _ARCHITECT_WATCH_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Goal:\n{(user_q or '')[:2000]}\n\n"
                f"Doer answer:\n{(answer or '')[:7000]}"
            ),
        },
    ]
    try:
        if upstream_call is not None:
            data = await upstream_call(
                model=mid, messages=messages, stream=False, max_tokens=800
            )
        else:
            from app import upstream

            data = await upstream.chat_completions(
                model=mid,
                messages=messages,
                stream=False,
                max_tokens=800,
                temperature=0.1,
            )
        from app import upstream as _up

        text = _up.extract_text(data) if isinstance(data, dict) else str(data or "")
        pt, ct = _up.extract_usage(data) if isinstance(data, dict) else (0, 0)
        parsed = _extract_watch_json(text) or {}
        ok = bool(parsed.get("ok", True))
        hint = str(parsed.get("fix_hint") or "").strip()
        if not ok and not hint:
            issues = parsed.get("issues") or []
            hint = "; ".join(str(x) for x in issues[:4]) if issues else "architect_reject"
        return ok, hint[:800], int(pt or 0), int(ct or 0)
    except Exception:  # noqa: BLE001
        return True, "", 0, 0  # fail-open: don't block on watch outage


async def run_test_author_spotcheck(
    *,
    answer: str,
    user_q: str,
    model_id: str | None,
    upstream_call: Any | None = None,
) -> tuple[bool, str, int, int]:
    """GPT test_author spot-check. Returns (ok, fix_hint, pt, ct)."""
    mid = (model_id or "").strip()
    if not mid or not (answer or "").strip():
        return True, "", 0, 0
    if (os.environ.get("ZEUS_FUSION_WATCH_HEURISTIC") or "").strip().lower() in (
        "1",
        "true",
        "on",
        "yes",
    ):
        return True, "", 0, 2

    messages = [
        {"role": "system", "content": _TEST_SPOT_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Goal:\n{(user_q or '')[:1800]}\n\n"
                f"Answer:\n{(answer or '')[:5500]}"
            ),
        },
    ]
    try:
        if upstream_call is not None:
            data = await upstream_call(
                model=mid, messages=messages, stream=False, max_tokens=600
            )
        else:
            from app import upstream

            data = await upstream.chat_completions(
                model=mid,
                messages=messages,
                stream=False,
                max_tokens=600,
                temperature=0.1,
            )
        from app import upstream as _up

        text = _up.extract_text(data) if isinstance(data, dict) else str(data or "")
        pt, ct = _up.extract_usage(data) if isinstance(data, dict) else (0, 0)
        parsed = _extract_watch_json(text) or {}
        ok = bool(parsed.get("ok", True))
        hint = str(parsed.get("fix_hint") or "").strip()
        if not ok and not hint:
            hint = "test_author_reject"
        return ok, hint[:800], int(pt or 0), int(ct or 0)
    except Exception:  # noqa: BLE001
        return True, "", 0, 0


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
    crew_watch: bool = False,
    task_kind: str | None = None,
    soft_accept: bool = True,
    client_meta: dict[str, Any] | None = None,
    prior_oversight_complete: bool = False,
) -> TrustedVerifyResult:
    """Mini → (crew watch: Test Author + Opus) → Gate → Judge≤2 → Soft-Stop.

    ``crew_watch`` links the power crew: after Mini GREEN, GPT spot-check then
    Opus architect evaluate; rejects feed ``judge_fix`` (Opus). Light skips watch.

    ``soft_accept`` (default): if doer answer looks usable and only Mini/parse
    reasons are RED, accept GREEN without Soft-Stop banner / Opus judge spam.

    ``tests_failed=True`` (Studio Layer A / FR-10/11) forces RED and stays sticky
    across escalate attempts until Soft-Stop. ``None`` = N/A (hot skip).

    ``client_meta`` / ``zeus.exec`` — machine signals from client hands (TZ §5.3).
    """
    from app.fusion.log_analyst import (
        has_error_trigger,
        pick_log_model,
        run_log_analyst,
        should_run_log_analyst,
    )
    from app.fusion.model_power import power_score
    from app.fusion.types import BranchUsage

    mach = machine_signals_from_client(client_meta)
    if prior_oversight_complete:
        # Pipeline v1 already ran leader + verifier/test-author. Do not add a
        # fourth mini role or repeat architect/test-author oversight.
        allow_green_without_mini = True
    if tests_failed is None and mach.get("tests_failed") is not None:
        tests_failed = mach["tests_failed"]
    if build_failed is None and mach.get("build_failed") is not None:
        build_failed = mach["build_failed"]

    mbr = dict(models_by_role or {})
    stack = list(panel or [])
    for mid in mbr.values():
        if mid and mid not in stack:
            stack.append(mid)
    # Always keep curator/judge/architect on stack for Soft-Stop pick
    for key in ("architect", "judge_fix", "test_author", "mini_verifier"):
        mid = mbr.get(key)
        if mid and mid not in stack:
            stack.append(mid)
    if curator_model and curator_model not in stack:
        stack.append(curator_model)

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
            try:
                from app.fusion.error_bank import note_log_digest

                note_log_digest(la.report)
            except Exception:  # noqa: BLE001
                pass
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
                patch_applied=mach.get("patch_applied"),
                files_touched_ok=mach.get("files_touched_ok"),
                command_exit_nonzero=mach.get("command_exit_nonzero"),
                compile_failed=mach.get("compile_failed"),
                ui_broken=mach.get("ui_broken"),
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

    # judge_fix = Opus from role table (main brain); fallback max power
    judge_model = mbr.get("judge_fix") if mbr.get("judge_fix") in set(stack) else None
    if not judge_model:
        judge_model = mbr.get("architect") if mbr.get("architect") in set(stack) else None
    if not judge_model and stack:
        judge_model = max(stack, key=power_score)
    judge_model = judge_model or curator_model

    # Crew watch: Mini GREEN → Test Author → Opus Architect (skip light)
    tk = (task_kind or "").strip().lower() or "general"
    watch_on = (
        bool(crew_watch)
        and tk != "light"
        and bool(current)
        and not prior_oversight_complete
    )
    if watch_on and gate == "GREEN" and not soft_stop_already:
        ta_mid = mbr.get("test_author") if mbr.get("test_author") in set(stack) else None
        arch_mid = (
            mbr.get("architect")
            if mbr.get("architect") in set(stack)
            else (curator_model if curator_model in set(stack) else None)
        )
        if ta_mid and tk in ("code", "tests", "architecture", "review", "general", "ui"):
            ta_ok, ta_hint, ta_pt, ta_ct = await run_test_author_spotcheck(
                answer=current,
                user_q=user_q,
                model_id=ta_mid,
                upstream_call=upstream_call,
            )
            extra_branches.append(
                BranchUsage(
                    model_id=ta_mid,
                    billable_state="completed" if (ta_pt or ta_ct) else "cancelled_no_tokens",
                    prompt_tokens=ta_pt,
                    completion_tokens=ta_ct,
                    role="test_author",
                    meta={"ok": ta_ok, "watch": True},
                )
            )
            if not ta_ok:
                gate = "RED"
                reasons = list(reasons) + ["test_author_watch"]
                fix_hint = ta_hint or fix_hint or "Исправь по замечаниям Test Author."
        if gate == "GREEN" and arch_mid:
            aw_ok, aw_hint, aw_pt, aw_ct = await run_architect_watch(
                answer=current,
                user_q=user_q,
                model_id=arch_mid,
                upstream_call=upstream_call,
            )
            extra_branches.append(
                BranchUsage(
                    model_id=arch_mid,
                    billable_state="completed" if (aw_pt or aw_ct) else "cancelled_no_tokens",
                    prompt_tokens=aw_pt,
                    completion_tokens=aw_ct,
                    role="architect",
                    meta={"ok": aw_ok, "watch": True},
                )
            )
            if not aw_ok:
                gate = "RED"
                reasons = list(reasons) + ["architect_watch"]
                fix_hint = aw_hint or fix_hint or "Исправь по замечаниям Architect."

    soft_stop = False

    def _try_soft_accept() -> bool:
        nonlocal gate, reasons, soft_stop
        if (
            not soft_accept
            or gate != "RED"
            or soft_stop_already
            or tests_failed is True
            or build_failed is True
            or not answer_looks_usable(current, user_q)
        ):
            return False
        hard = [r for r in reasons if r not in _SOFT_GATE_REASONS]
        if hard:
            return False
        gate = "GREEN"
        reasons = list(reasons) + ["soft_accept_doer"]
        soft_stop = False
        return True

    # Accept usable doer before Opus judge spam (Mini veto is advisory)
    _try_soft_accept()

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

    soft_model: str | None = None
    if soft_stop_already:
        # Brownfield soft-stop terminal cannot silently become GREEN
        gate = "RED"
        if "soft_stop" not in reasons:
            reasons = list(reasons) + ["soft_stop_terminal"]
        soft_stop = True
    # Final soft-accept if judge loop still RED on soft reasons only
    _try_soft_accept()
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
