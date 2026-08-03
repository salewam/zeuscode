"""Read-only Advisor pass (omp-inspired watchdog) — never rewrites the answer.

Severity: nit | concern | blocker. Surfaces via Onestack + thinking; Gate/Judge
remain the rewrite path. ``fusion/*`` must not import ``routers.*``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

AdvisorSeverity = Literal["nit", "concern", "blocker"]

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

_ADVISOR_SYSTEM = (
    "Ты Advisor ZeusCode — read-only watchdog. НЕ пиши код и НЕ переписывай ответ. "
    "Сравни ответ doer с задачей (и планом, если есть). Ответ — ТОЛЬКО JSON:\n"
    '{"severity":"nit|concern|blocker","note":"1–3 коротких предложения на русском"}\n'
    "nit = мелочь; concern = риск/пробел; blocker = ответ мимо ТЗ или опасен. "
    "Без prose вне JSON."
)


@dataclass
class AdvisorResult:
    severity: AdvisorSeverity
    note: str
    model_id: str | None = None
    skipped: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "note": self.note,
            "model_id": self.model_id,
            "skipped": self.skipped,
            **({"meta": self.meta} if self.meta else {}),
        }


def _heuristic() -> bool:
    return (os.environ.get("ZEUS_FUSION_ADVISOR_HEURISTIC") or "").strip().lower() in (
        "1",
        "true",
        "on",
        "yes",
    )


def should_run_advisor(
    *,
    product_mode: str,
    kill_switch: bool,
    zeus: dict[str, Any] | None,
    answer: str,
) -> bool:
    if kill_switch:
        return False
    if (product_mode or "").lower() == "simple":
        return False
    if not (answer or "").strip():
        return False
    z = zeus if isinstance(zeus, dict) else {}
    if z.get("advisor") is False or str(z.get("advisor") or "").lower() in (
        "0",
        "false",
        "off",
        "no",
    ):
        return False
    if z.get("advisor") is True or str(z.get("advisor") or "").lower() in (
        "1",
        "true",
        "on",
        "yes",
    ):
        return True
    # Env / settings opt-in (default off — hot path speed)
    env = (os.environ.get("ZEUS_FUSION_ADVISOR") or "").strip().lower()
    if env in ("1", "true", "on", "yes"):
        return True
    if env in ("0", "false", "off", "no"):
        return False
    try:
        from app.config import get_settings

        if bool(getattr(get_settings(), "FUSION_ADVISOR_DEFAULT", False)):
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def pick_advisor_model(
    *,
    stack: list[str],
    models_by_role: dict[str, str] | None = None,
    model_aliases: dict[str, str] | None = None,
    curator: str | None = None,
) -> str | None:
    mbr = models_by_role or {}
    aliases = model_aliases or {}
    ready = set(stack or [])
    for mid in (
        aliases.get("advisor"),
        mbr.get("judge_fix"),
        aliases.get("smol"),
        mbr.get("mini_verifier"),
        curator,
    ):
        if not mid:
            continue
        if not ready or mid in ready:
            return mid
    if stack:
        # Prefer mid-band, not always curator (cost)
        from .model_power import power_score

        mid_band = [m for m in stack if 700 <= power_score(m) <= 940]
        if mid_band:
            return max(mid_band, key=power_score)
        return stack[0]
    return curator


def _extract_json(raw: str | dict[str, Any] | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
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
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _normalize_severity(raw: Any) -> AdvisorSeverity:
    s = str(raw or "nit").strip().lower()
    if s in ("blocker", "block", "critical", "red"):
        return "blocker"
    if s in ("concern", "warn", "warning", "yellow"):
        return "concern"
    return "nit"


def _heuristic_advice(user_q: str, answer: str) -> dict[str, Any]:
    q = (user_q or "").lower()
    a = (answer or "").lower()
    if len(answer or "") < 40:
        return {
            "severity": "blocker",
            "note": "Ответ слишком короткий — похоже, задача не закрыта.",
        }
    if any(w in q for w in ("лендинг", "landing", "сайт")) and not any(
        w in a for w in ("html", "<!doctype", "<html", "section", "hero")
    ):
        return {
            "severity": "concern",
            "note": "В задаче лендинг/сайт, в ответе мало признаков вёрстки.",
        }
    return {"severity": "nit", "note": "Ответ выглядит связным с запросом."}


async def run_advisor_pass(
    *,
    answer: str,
    user_q: str,
    model_id: str | None,
    plan_artifact: dict[str, Any] | str | None = None,
    upstream_call: Any | None = None,
) -> AdvisorResult:
    """One read-only advisor turn. Never mutates ``answer``."""
    if not model_id and not _heuristic():
        return AdvisorResult(
            severity="nit",
            note="",
            skipped=True,
            meta={"reason": "no_advisor_model"},
        )

    plan_txt = ""
    if isinstance(plan_artifact, dict):
        plan_txt = str(
            plan_artifact.get("content") or plan_artifact.get("dev_plan") or ""
        )[:3000]
    elif isinstance(plan_artifact, str):
        plan_txt = plan_artifact[:3000]

    if _heuristic() or not model_id:
        data = _heuristic_advice(user_q, answer)
        return AdvisorResult(
            severity=_normalize_severity(data.get("severity")),
            note=str(data.get("note") or "")[:500],
            model_id=model_id,
            completion_tokens=6,
            meta={"heuristic": True},
        )

    user_blob = (
        f"Задача:\n{(user_q or '')[:2500]}\n\n"
        f"Ответ doer:\n{(answer or '')[:6000]}\n"
    )
    if plan_txt:
        user_blob += f"\nУтверждённый план:\n{plan_txt}\n"

    msgs = [
        {"role": "system", "content": _ADVISOR_SYSTEM},
        {"role": "user", "content": user_blob},
    ]
    try:
        if upstream_call is not None:
            data = await upstream_call(
                model_id, msgs, temperature=0.1, max_tokens=400
            )
        else:
            from app.fusion.panel import _default_upstream

            data = await _default_upstream(
                model_id, msgs, temperature=0.1, max_tokens=400
            )
        text = str((data or {}).get("text") or "")
        pt = int((data or {}).get("prompt_tokens") or 0)
        ct = int((data or {}).get("completion_tokens") or 0)
        parsed = _extract_json(text) or _heuristic_advice(user_q, answer)
        return AdvisorResult(
            severity=_normalize_severity(parsed.get("severity")),
            note=str(parsed.get("note") or "")[:500],
            model_id=model_id,
            prompt_tokens=pt,
            completion_tokens=ct,
        )
    except Exception as exc:  # noqa: BLE001
        return AdvisorResult(
            severity="nit",
            note="",
            model_id=model_id,
            skipped=True,
            meta={"error": str(exc)[:200]},
        )


def format_advisor_think_line(result: AdvisorResult) -> str | None:
    if result.skipped or not result.note:
        return None
    return f"│ advisor · {result.severity}: {result.note}"
