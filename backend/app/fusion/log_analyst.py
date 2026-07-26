"""DeepSeek Log Analyst (Epic 2 / AD-27 / FR-5).

Call only when user stack has a log-capable model AND an error trigger.
Skip ⇒ ``log_report=N/A`` (not RED). Bad/missing ``critical`` ⇒ Gate RED.
``fusion/*`` must not import ``routers.*``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

# NFR-2: brief-sized input; ~400 tokens out soft ceiling
_MAX_GOAL_CHARS = 800
_MAX_LOG_CHARS = 3500
_MAX_FILES = 8
_MAX_OUT_TOKENS = 400

_ERROR_TRIGGER_RE = re.compile(
    r"(?i)(traceback|exception|error:|typeerror|referenceerror|syntaxerror|"
    r"ModuleNotFoundError|ENOENT|undefined is not|cannot find module|"
    r"failed|ошибка|исключение|stack trace)"
)

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

_LOG_SYSTEM = (
    "Ты Log Analyst Zeus Fusion. Ответ — ТОЛЬКО JSON объект с ключами "
    '{"critical": bool, "summary": str, "fix_hint": str, "confidence": 0..1}. '
    "critical=true если traceback/runtime ломает цель пользователя. "
    "Не управляй doers, не пиши тесты, не переписывай Brief."
)


@dataclass
class LogAnalystResult:
    skipped: bool
    reason: str
    report: dict[str, Any] | None = None
    model_id: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    degraded: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def called(self) -> bool:
        return not self.skipped


def is_log_capable_model(model_id: str | None) -> bool:
    mid = (model_id or "").strip().lower()
    if not mid:
        return False
    return "deepseek" in mid


def pick_log_model(
    stack: list[str] | None,
    *,
    models_by_role: dict[str, str] | None = None,
) -> str | None:
    mbr = models_by_role or {}
    preferred = mbr.get("log_analyst")
    if preferred and is_log_capable_model(preferred):
        return preferred
    for mid in stack or []:
        if is_log_capable_model(mid):
            return mid
    return None


def has_error_trigger(
    *,
    user_q: str = "",
    answer: str = "",
    messages: list[dict[str, Any]] | None = None,
    force: bool = False,
) -> bool:
    if force:
        return True
    blobs = [user_q or "", answer or ""]
    if messages:
        for m in messages:
            blobs.append(str(m.get("content") or ""))
    text = "\n".join(blobs)
    return bool(_ERROR_TRIGGER_RE.search(text))


def should_run_log_analyst(
    *,
    stack_has_log_model: bool,
    has_error_trigger: bool,
) -> bool:
    """FR-5/5Б: need log-capable model in stack AND error trigger."""
    return bool(stack_has_log_model and has_error_trigger)


def brief_log_input(
    *,
    goal: str,
    log_tail: str,
    files: list[str] | None = None,
) -> tuple[str, str, list[str]]:
    g = (goal or "").strip()[:_MAX_GOAL_CHARS]
    # Prefer the error-rich tail of the log
    raw = (log_tail or "").strip()
    if len(raw) > _MAX_LOG_CHARS:
        raw = raw[-_MAX_LOG_CHARS:]
    fl = [str(f).strip() for f in (files or []) if str(f).strip()][:_MAX_FILES]
    return g, raw, fl


def parse_log_analyst_json(raw: str | dict[str, Any] | None) -> dict[str, Any] | None:
    """Parse Log Analyst JSON. None on schema/parse fail (→ Gate RED when called)."""
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
    if "critical" not in data:
        return None
    crit = data.get("critical")
    if not isinstance(crit, bool):
        if crit in (0, 1, "0", "1", "true", "false", "True", "False"):
            crit = str(crit).lower() in ("1", "true")
        else:
            return None
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "critical": bool(crit),
        "summary": str(data.get("summary") or "")[:500],
        "fix_hint": str(data.get("fix_hint") or "")[:800],
        "confidence": max(0.0, min(1.0, conf)),
    }


async def run_log_analyst(
    *,
    goal: str,
    log_tail: str,
    files: list[str] | None = None,
    model_id: str | None = None,
    upstream_call: Any | None = None,
    skip_reason: str | None = None,
) -> LogAnalystResult:
    """Run DeepSeek Log Analyst JSON contract (AD-27)."""
    if skip_reason:
        return LogAnalystResult(skipped=True, reason=skip_reason, report=None)

    mid = (model_id or "").strip()
    if not mid or not is_log_capable_model(mid):
        return LogAnalystResult(skipped=True, reason="no_log_model", report=None)

    g, tail, fl = brief_log_input(goal=goal, log_tail=log_tail, files=files)
    if not tail and not _ERROR_TRIGGER_RE.search(g):
        return LogAnalystResult(skipped=True, reason="no_error_trigger", report=None)

    # Offline/heuristic for tests
    if (os.environ.get("ZEUS_FUSION_LOG_HEURISTIC") or "").strip().lower() in (
        "1",
        "true",
        "on",
        "yes",
    ):
        crit = bool(_ERROR_TRIGGER_RE.search(tail) or _ERROR_TRIGGER_RE.search(g))
        return LogAnalystResult(
            skipped=False,
            reason="heuristic",
            report={
                "critical": crit,
                "summary": "heuristic log scan",
                "fix_hint": "fix the traceback root cause" if crit else "",
                "confidence": 0.85 if crit else 0.4,
            },
            model_id=mid,
            meta={"heuristic": True},
        )

    files_line = ", ".join(fl) if fl else "(none)"
    messages = [
        {"role": "system", "content": _LOG_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Goal:\n{g}\n\nFiles:\n{files_line}\n\nLog tail:\n{tail or g}"
            ),
        },
    ]
    try:
        if upstream_call is not None:
            data = await upstream_call(
                model=mid,
                messages=messages,
                stream=False,
                max_tokens=_MAX_OUT_TOKENS,
            )
        else:
            from app import upstream

            data = await upstream.chat_completions(
                model=mid,
                messages=messages,
                stream=False,
                max_tokens=_MAX_OUT_TOKENS,
                temperature=0.0,
            )
        raw = ""
        pt = ct = 0
        if isinstance(data, dict):
            from app import upstream as _up

            raw = _up.extract_text(data)
            pt, ct = _up.extract_usage(data)
        else:
            raw = str(data or "")
        parsed = parse_log_analyst_json(raw)
        if parsed is None:
            return LogAnalystResult(
                skipped=False,
                reason="parse_degraded",
                report=None,
                model_id=mid,
                prompt_tokens=pt,
                completion_tokens=ct,
                degraded=True,
            )
        return LogAnalystResult(
            skipped=False,
            reason="ok",
            report=parsed,
            model_id=mid,
            prompt_tokens=pt,
            completion_tokens=ct,
        )
    except Exception as e:  # noqa: BLE001
        return LogAnalystResult(
            skipped=False,
            reason=f"call_failed:{e}"[:180],
            report=None,
            model_id=mid,
            degraded=True,
        )
