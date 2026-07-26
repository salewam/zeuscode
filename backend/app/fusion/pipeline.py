"""Pipeline enum + small-path orchestration helpers (Role Routing / AD-20..23).

``pipeline.py`` is the sole final writer of Onestack ``pipeline``.
``fusion/*`` must not import ``routers.*``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .model_power import TEST_AUTHOR_MIN, power_score
from .roles import RoleResolveResult, cap_doers

PipelineName = Literal["small", "v1", "fallback_single"]


@dataclass
class PipelineDecision:
    pipeline: PipelineName
    size: Literal["small", "large"]
    second_signal: bool
    serving_path_clamp: str | None = None  # e.g. force CASCADE for Mini
    doer_panel: list[str] = field(default_factory=list)
    curator_model: str | None = None
    reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


def pick_pipeline(
    *,
    size: str,
    second_signal: bool,
    product_mode: str,
    kill_switch: bool,
    roles: RoleResolveResult | None,
    forced_path: bool = False,
) -> PipelineDecision:
    """Hard trigger rules (AD-22). Epic 1 focuses on ``small``; v1/fallback later."""
    mode = (product_mode or "power").strip().lower()
    curator = roles.curator_model if roles else None
    stack = list(roles.stack) if roles else []
    has_strong = bool(roles and roles.has_strong)

    if kill_switch or mode == "simple":
        panel = cap_doers(stack, curator, max_doers=2) if stack else []
        # Keep FAST when kill or forced/legacy fast; else prefer CASCADE for Mini.
        if kill_switch or forced_path:
            clamp: str | None = "FAST" if kill_switch or forced_path else None
        else:
            clamp = "CASCADE"
        return PipelineDecision(
            pipeline="small",
            size="small" if size != "large" else "large",
            second_signal=False if kill_switch else bool(second_signal),
            serving_path_clamp=clamp,
            doer_panel=panel,
            curator_model=curator,
            reason="kill_or_simple",
            meta={"preserve_fast": bool(forced_path or kill_switch)},
        )

    large = (size or "").lower() == "large"
    if large and second_signal and mode in ("power", "custom"):
        if has_strong:
            # Epic 4: intent v1 → execute_pipeline_v1 (Brief→tests→doers→merge).
            # AD-20 / addendum K: never target RACE for Role Routing large — prefer FULL.
            panel = cap_doers(stack, curator, max_doers=3) if stack else []
            return PipelineDecision(
                pipeline="v1",
                size="large",
                second_signal=True,
                serving_path_clamp="FULL",
                doer_panel=panel,
                curator_model=curator,
                reason="large_2nd_strong",
                meta={"test_author_min": TEST_AUTHOR_MIN, "forbid_race": True},
            )
        panel = cap_doers(stack, curator, max_doers=1) if stack else []
        return PipelineDecision(
            pipeline="fallback_single",
            size="large",
            second_signal=True,
            serving_path_clamp="CASCADE",
            doer_panel=panel or ([curator] if curator else []),
            curator_model=curator,
            reason="large_2nd_no_strong",
        )

    # Default cheap path
    panel = cap_doers(stack, curator, max_doers=2) if stack else []
    clamp = None if forced_path else "CASCADE"
    return PipelineDecision(
        pipeline="small",
        size="large" if large else "small",
        second_signal=bool(second_signal),
        serving_path_clamp=clamp,
        doer_panel=panel,
        curator_model=curator,
        reason="default_small",
        meta={"max_doer_llms": 2, "preserve_fast": bool(forced_path)},
    )


def apply_small_path_clamps(
    *,
    serving_path: str,
    panel: list[str],
    leader: str | None,
    decision: PipelineDecision,
) -> tuple[str, list[str], str | None]:
    """Clamp Path/panel for pipeline=small (no RACE/FULL / ≤2 doers)."""
    path = (serving_path or "CASCADE").upper()
    if decision.pipeline == "small":
        preserve_forced = bool((decision.meta or {}).get("preserve_fast"))
        if path == "RACE":
            # AD-20: never serve RACE on RR small
            path = decision.serving_path_clamp or "CASCADE"
        elif path == "FULL":
            if decision.serving_path_clamp:
                path = decision.serving_path_clamp
            elif not preserve_forced:
                # Cheap small default demotes FULL → CASCADE; forced/legacy FULL kept
                path = "CASCADE"
        elif decision.serving_path_clamp == "FAST":
            path = "FAST"
        elif (
            path == "FAST"
            and decision.serving_path_clamp == "CASCADE"
            and not preserve_forced
        ):
            # Prefer CASCADE so Mini-Verifier runs on hot small path (FR-8)
            path = "CASCADE"
        # forced/legacy FAST: leave Path=FAST (Mini may be skipped; AD-9 kill/legacy)
        # Prefer decision.doer_panel even when empty — empty custom stack must not
        # reinflate exclusive power panel via `or cap_doers(panel)` (AD-21).
        new_panel = list(decision.doer_panel)
        if not new_panel and decision.curator_model:
            new_panel = cap_doers(panel, decision.curator_model, max_doers=2) if panel else [
                decision.curator_model
            ]
        # Empty doer stack → clear leader too (do not keep exclusive-fill leader)
        new_leader = decision.curator_model or (leader if new_panel else None)
        if new_leader and new_leader in new_panel:
            new_panel = [new_leader] + [m for m in new_panel if m != new_leader]
        return path, new_panel[:2], new_leader
    if decision.pipeline == "fallback_single":
        cur = decision.curator_model or leader
        fb_panel = list(decision.doer_panel)
        if not fb_panel and cur:
            fb_panel = [cur]
        return (
            decision.serving_path_clamp or "CASCADE",
            fb_panel[:1],
            cur,
        )
    # v1: Epic 4 owns orchestrator; still enforce AD-20 — never serve RACE as RR large
    if path == "RACE" or (decision.meta or {}).get("forbid_race"):
        path = decision.serving_path_clamp or "FULL"
        if path == "RACE":
            path = "FULL"
    new_panel = list(decision.doer_panel) or list(panel)
    new_leader = decision.curator_model or leader
    if new_leader and new_leader in new_panel:
        new_panel = [new_leader] + [m for m in new_panel if m != new_leader]
    return path, new_panel, new_leader


def write_pipeline(
    clf_meta: dict[str, Any] | None,
    pipeline: PipelineName,
    *,
    reason: str = "",
) -> dict[str, Any]:
    """AD-20 sole final writer helper for ``clf_meta['pipeline']`` (incl. v1→fallback degrade)."""
    meta = clf_meta if isinstance(clf_meta, dict) else {}
    meta["pipeline"] = pipeline
    if reason:
        meta["pipeline_reason"] = reason
    return meta


def stamp_role_routing_onestack(
    onestack: dict[str, Any],
    *,
    decision: PipelineDecision,
    roles: RoleResolveResult | None,
    gate: str | None = None,
    gate_reasons: list[str] | None = None,
    escalate_count: int = 0,
    soft_stop: bool = False,
    log_report: Any = None,
    soft_stop_model: str | None = None,
) -> dict[str, Any]:
    """Additive FR-14 / AD-28 fields. Mutates and returns ``onestack``."""
    os_ = onestack if isinstance(onestack, dict) else {}
    write_pipeline(os_, decision.pipeline, reason=decision.reason)
    os_["size"] = decision.size
    os_["second_signal"] = bool(decision.second_signal)
    os_["curator_model"] = decision.curator_model
    os_["role_table"] = roles.role_table if roles else "v1"
    os_["roles"] = list(roles.roles) if roles else []
    os_["models_by_role"] = dict(roles.models_by_role) if roles else {}
    if gate is not None:
        os_["gate"] = gate
    if gate_reasons is not None:
        os_["gate_reasons"] = list(gate_reasons)
    os_["escalate_count"] = int(escalate_count)
    os_["soft_stop"] = bool(soft_stop)
    if log_report is not None:
        os_["log_report"] = log_report
    if soft_stop_model:
        os_["soft_stop_model"] = soft_stop_model
    if decision.curator_model:
        os_["leader"] = decision.curator_model
    os_["pipeline_reason"] = decision.reason
    return os_


# AD-29: pipeline.py owns v1 orchestration surface (impl lives in pipeline_v1).
from .pipeline_v1 import execute_pipeline_v1 as execute_pipeline_v1  # noqa: E402


def count_doer_llm_branches(agents: list[dict[str, Any]]) -> int:
    n = 0
    for a in agents or []:
        role = str(a.get("role") or "")
        if role in ("panel", "agent", "doer", "doer_logic", "doer_ui") and a.get("ok") is not False:
            # count attempts with tokens or ok answers
            if int(a.get("prompt_tokens") or 0) or int(a.get("completion_tokens") or 0) or a.get("ok"):
                n += 1
    return n


def strongest_in_stack(stack: list[str]) -> str | None:
    if not stack:
        return None
    return max(stack, key=power_score)
