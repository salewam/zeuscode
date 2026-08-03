"""Pipeline enum + orchestration helpers (Role Routing / AD-20..23).

``pipeline.py`` is the sole final writer of Onestack ``pipeline``.
``fusion/*`` must not import ``routers.*``.

Crew state selects only a named pipeline. Legacy serving-path fields are static
compatibility metadata; kill-switch remains the emergency single-model path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .roles import RoleResolveResult, role_execute_panel
from .crew import CrewDecision, TurnKind

PipelineName = Literal[
    "v1", "tool_bootstrap", "incremental", "session_soft_stop", "fallback_single"
]


@dataclass
class PipelineDecision:
    pipeline: PipelineName
    size: Literal["small", "large"]
    second_signal: bool
    serving_path_clamp: str | None = None
    doer_panel: list[str] = field(default_factory=list)
    curator_model: str | None = None  # Soft-Stop / Judge / v1 architect
    execute_leader: str | None = None
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
    crew: CrewDecision | None = None,
    tool_enabled: bool = False,
) -> PipelineDecision:
    """Choose bootstrap or incremental execution from adaptive crew state.

    AD-32: ``curator_model`` = face/Brief/Judge; ``execute_leader`` = curator on v1.
    """
    mode = (product_mode or "power").strip().lower()
    curator = roles.curator_model if roles else None
    large = (size or "").lower() == "large"
    tk = str((roles.meta or {}).get("task_kind") or "general") if roles else "general"
    crew_watch = bool((roles.meta or {}).get("crew_watch")) if roles else False
    crew_linked = bool((roles.meta or {}).get("crew_linked")) if roles else False

    if kill_switch:
        panel, exec_lead = role_execute_panel(roles, pipeline="small", max_doers=1)
        return PipelineDecision(
            pipeline="fallback_single",
            size="small" if size != "large" else "large",
            second_signal=False,
            doer_panel=panel,
            curator_model=curator,
            execute_leader=exec_lead,
            reason="kill_switch",
            meta={
                "emergency": True,
                "crew_watch": False,
                "crew_linked": False,
                "max_doer_llms": 1,
            },
        )

    if crew and crew.max_internal_branches <= 0:
        return PipelineDecision(
            pipeline="session_soft_stop",
            size="large" if crew.crew_size >= 4 else "small",
            second_signal=False,
            curator_model=curator,
            reason="session_soft_cap",
            meta={
                "max_internal_branches": 0,
                "active_roles": [],
                "crew_size": crew.crew_size,
                "crew_tier": crew.tier,
                "crew_watch": False,
            },
        )

    if crew and crew.turn_kind is TurnKind.BOOTSTRAP and tool_enabled:
        panel, exec_lead = role_execute_panel(roles, pipeline="small", max_doers=1)
        return PipelineDecision(
            pipeline="tool_bootstrap",
            size="large" if crew.crew_size >= 4 else "small",
            second_signal=bool(second_signal),
            doer_panel=panel[:1],
            curator_model=curator,
            execute_leader=exec_lead or (panel[0] if panel else None),
            reason="adaptive_tool_bootstrap",
            meta={
                "max_doer_llms": 1,
                "max_internal_branches": crew.max_internal_branches,
                "crew_watch": False,
                "crew_linked": True,
                "crew_size": crew.crew_size,
                "crew_tier": crew.tier,
                "active_roles": (
                    ["leader", "specialist", "doer"]
                    if crew.crew_size >= 4
                    else ["leader", "doer"]
                ),
                "forbid_race": True,
            },
        )

    if crew and crew.turn_kind in (TurnKind.TOOL_LOOP, TurnKind.EXEC_FEEDBACK):
        panel, exec_lead = role_execute_panel(roles, pipeline="small", max_doers=1)
        return PipelineDecision(
            pipeline="incremental",
            size="large" if crew.crew_size >= 4 else "small",
            second_signal=bool(second_signal),
            doer_panel=panel[:1],
            curator_model=curator,
            execute_leader=exec_lead or (panel[0] if panel else None),
            reason=f"adaptive_{crew.turn_kind.value}",
            meta={
                "max_doer_llms": 1,
                "max_internal_branches": min(3, crew.max_internal_branches),
                "crew_watch": False,
                "crew_linked": True,
                "crew_size": crew.crew_size,
                "crew_tier": crew.tier,
                "active_roles": list(crew.active_roles),
                "forbid_race": True,
            },
        )

    panel, exec_lead = role_execute_panel(roles, pipeline="v1")
    if crew is not None:
        selected_doer = crew.role_assignments.get("doer")
        panel = [selected_doer] if selected_doer else panel[:1]
        exec_lead = selected_doer or exec_lead
    return PipelineDecision(
        pipeline="v1",
        size="large" if large else "small",
        second_signal=bool(second_signal),
        doer_panel=panel,
        curator_model=curator,
        execute_leader=exec_lead or curator,
        reason=(
            f"adaptive_{crew.tier}_bootstrap"
            if crew is not None
            else "always_crew"
        ),
        meta={
            "max_doer_llms": 1 if crew is not None else max(2, len(panel) if panel else 2),
            "execute_neq_curator": bool(
                exec_lead and curator and exec_lead != curator
            ),
            "crew_watch": False if crew is not None else crew_watch or (tk != "light"),
            "crew_linked": crew_linked or (tk != "light"),
            "soft_accept": False,
            "product_mode": mode,
            "task_kind": tk,
            "forbid_race": True,
            "crew_size": crew.crew_size if crew else 3,
            "crew_tier": crew.tier if crew else "standard",
            "active_roles": list(crew.active_roles) if crew else [],
            "max_internal_branches": crew.max_internal_branches if crew else 6,
        },
    )


def apply_small_path_clamps(
    *,
    serving_path: str,
    panel: list[str],
    leader: str | None,
    decision: PipelineDecision,
) -> tuple[str, list[str], str | None]:
    """Compatibility helper: select the crew panel without mutating path labels."""
    path = (serving_path or "CASCADE").upper()
    if decision.pipeline in ("tool_bootstrap", "incremental"):
        new_panel = list(decision.doer_panel)
        if not new_panel and decision.execute_leader:
            new_panel = [decision.execute_leader]
        new_leader = (
            decision.execute_leader
            or (new_panel[0] if new_panel else None)
            or (leader if new_panel else None)
        )
        if new_leader and new_leader in new_panel:
            new_panel = [new_leader] + [m for m in new_panel if m != new_leader]
        elif new_panel:
            new_leader = new_panel[0]
        return path, new_panel[:1], new_leader
    if decision.pipeline == "fallback_single":
        cur = decision.execute_leader or decision.curator_model or leader
        fb_panel = list(decision.doer_panel)
        if not fb_panel and cur:
            fb_panel = [cur]
        return (
            path,
            fb_panel[:1],
            cur,
        )
    # v1 crew: curator-led panel; the static compatibility label passes through.
    new_panel = list(decision.doer_panel)
    if not new_panel and decision.execute_leader:
        new_panel = [decision.execute_leader]
    new_leader = (
        decision.execute_leader
        or decision.curator_model
        or (new_panel[0] if new_panel else None)
    )
    if not new_panel:
        return path, [], None
    if new_leader and new_leader in new_panel:
        new_panel = [new_leader] + [m for m in new_panel if m != new_leader]
    elif new_panel:
        new_leader = new_panel[0]
    return path, new_panel, new_leader


def write_pipeline(
    clf_meta: dict[str, Any] | None,
    pipeline: PipelineName,
    *,
    reason: str = "",
) -> dict[str, Any]:
    """AD-20 sole final writer helper for ``clf_meta['pipeline']``."""
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
    os_["execute_leader"] = decision.execute_leader
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
            if (
                int(a.get("prompt_tokens") or 0)
                or int(a.get("completion_tokens") or 0)
                or a.get("ok")
            ):
                n += 1
    return n
