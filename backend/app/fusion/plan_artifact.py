"""Plan artifact — omp-style plan as sticky/session object (not only chat text).

Scheme ``zeus://plan``. Stored in sticky ``phase_meta.plan_artifact`` and Onestack.
"""

from __future__ import annotations

import re
from typing import Any

PLAN_SCHEME = "zeus://plan"


def _slug_title(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return "plan"
    # first heading or first line
    m = re.search(r"^#\s+(.+)$", t, re.M)
    if m:
        t = m.group(1).strip()
    else:
        t = t.splitlines()[0].strip()
    t = re.sub(r"[^\w\s\-а-яА-ЯёЁ]+", "", t, flags=re.UNICODE)
    t = re.sub(r"\s+", "-", t).strip("-")[:64]
    return t or "plan"


def build_plan_artifact(
    *,
    content: str,
    spec_summary: str = "",
    title: str | None = None,
    source: str = "clarifier",
    original_goal: str = "",
) -> dict[str, Any]:
    body = (content or "").strip()
    if not body:
        return {}
    slug = _slug_title(title or body)
    return {
        "scheme": PLAN_SCHEME,
        "id": f"local://{slug}-plan.md",
        "title": slug.replace("-", " ").strip() or "plan",
        "content": body[:8000],
        "spec_summary": (spec_summary or "")[:4000],
        "original_goal": (original_goal or "")[:2000],
        "source": source,
        "version": 1,
    }


def plan_artifact_from_clarify_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    plan = str(state.get("dev_plan") or "").strip()
    if not plan:
        return {}
    return build_plan_artifact(
        content=plan,
        spec_summary=str(state.get("spec_summary") or ""),
        title=str(state.get("original_goal") or "plan")[:80],
        source="clarifier",
        original_goal=str(state.get("original_goal") or ""),
    )


def extract_plan_artifact(
    *,
    zeus: dict[str, Any] | None = None,
    onestack: dict[str, Any] | None = None,
    clarify_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    for src in (onestack, zeus):
        if isinstance(src, dict) and isinstance(src.get("plan_artifact"), dict):
            art = src["plan_artifact"]
            if art.get("content"):
                return art
    return plan_artifact_from_clarify_state(clarify_state)
