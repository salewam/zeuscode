"""Typed adaptive ZeusCode crew state and deterministic selection."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .policy import detect_adaptive_signals
from .task_card import task_card_tier
from .verify import collect_tool_evidence, machine_signals_from_client

CREW_ROSTER: tuple[str, ...] = ("leader", "doer", "analyst", "verifier")


def _model_family(model_id: str) -> str:
    low = (model_id or "").lower()
    for family in ("claude", "gpt", "deepseek", "gemini", "grok", "kimi"):
        if family in low:
            return family
    return low.split("-", 1)[0]


class TurnKind(str, Enum):
    BOOTSTRAP = "bootstrap"
    TOOL_LOOP = "tool_loop"
    EXEC_FEEDBACK = "exec_feedback"


def _session_soft_cap() -> int:
    try:
        return max(64, int(os.environ.get("ZEUS_CREW_SESSION_SOFT_CAP") or 512))
    except (TypeError, ValueError):
        return 512


@dataclass
class CrewDecision:
    turn_kind: TurnKind
    crew_size: int
    tier: str
    active_roles: list[str]
    role_assignments: dict[str, str]
    reason: str
    max_internal_branches: int
    remaining_internal_branches: int
    degraded: bool = False
    distinct_model_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_kind": self.turn_kind.value,
            "crew_size": self.crew_size,
            "tier": self.tier,
            "active_roles": list(self.active_roles),
            "role_assignments": dict(self.role_assignments),
            "reason": self.reason,
            "max_internal_branches": self.max_internal_branches,
            "remaining_internal_branches": self.remaining_internal_branches,
            "degraded": self.degraded,
            "distinct_model_count": self.distinct_model_count,
        }


@dataclass
class CrewSession:
    turn_kind: TurnKind = TurnKind.BOOTSTRAP
    crew_size: int = 2
    tier: str = "compact"
    roles: list[str] = field(default_factory=lambda: ["leader", "doer"])
    role_assignments: dict[str, str] = field(default_factory=dict)
    reason: str = "new_task"
    machine_evidence: dict[str, Any] = field(default_factory=dict)
    # Per-turn cap. Reset on every request; never exhausts a long agent task.
    max_internal_branches: int = 3
    remaining_internal_branches: int = 3
    llm_calls_session: int = 0
    total_internal_branches: int = 0
    session_soft_cap: int = 512
    plan_digest: str = ""
    task_card: dict[str, Any] = field(default_factory=dict)
    analyst_evidence_hash: str = ""
    turn_count: int = 0
    degraded: bool = False
    distinct_model_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 3,
            "turn_kind": self.turn_kind.value,
            "crew_size": max(2, min(4, int(self.crew_size))),
            "tier": self.tier,
            "roles": list(self.roles),
            "role_assignments": dict(self.role_assignments),
            "reason": self.reason,
            "machine_evidence": dict(self.machine_evidence),
            "max_internal_branches": int(self.max_internal_branches),
            "remaining_internal_branches": int(self.remaining_internal_branches),
            "llm_calls_session": int(self.llm_calls_session),
            "total_internal_branches": int(self.total_internal_branches),
            "session_soft_cap": int(self.session_soft_cap),
            "plan_digest": str(self.plan_digest or "")[:6000],
            "task_card": dict(self.task_card) if isinstance(self.task_card, dict) else {},
            "analyst_evidence_hash": str(self.analyst_evidence_hash or "")[:128],
            "turn_count": int(self.turn_count),
            "degraded": bool(self.degraded),
            "distinct_model_count": int(self.distinct_model_count),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "CrewSession":
        from .task_card import _sanitize_card_text, parse_task_card

        data = raw if isinstance(raw, dict) else {}
        try:
            kind = TurnKind(str(data.get("turn_kind") or TurnKind.BOOTSTRAP.value))
        except ValueError:
            kind = TurnKind.BOOTSTRAP
        tier = "serious" if data.get("tier") == "serious" else "compact"
        max_budget = (
            4
            if kind is TurnKind.BOOTSTRAP and tier == "serious"
            else 2
            if kind is TurnKind.BOOTSTRAP
            else 3
        )
        remaining = max_budget
        try:
            session_calls = max(0, int(data.get("llm_calls_session") or 0))
        except (TypeError, ValueError):
            session_calls = 0
        try:
            total_branches = max(
                session_calls, int(data.get("total_internal_branches") or 0)
            )
        except (TypeError, ValueError):
            total_branches = session_calls
        # Server policy, never a client-controlled persisted value.
        soft_cap = _session_soft_cap()
        raw_assignments = data.get("role_assignments")
        if not isinstance(raw_assignments, dict):
            raw_assignments = {}
        assignments = {
            str(k): str(v)[:160]
            for k, v in raw_assignments.items()
            if str(k) in {
                "leader",
                "doer",
                "analyst",
                "verifier",
                "log_analyst",
                "test_verifier",
            }
            and isinstance(v, str)
            and v.strip()
        }
        core = {
            "leader": assignments.get("leader", ""),
            "doer": assignments.get("doer", ""),
            "analyst": assignments.get("analyst")
            or assignments.get("log_analyst", ""),
            "verifier": assignments.get("verifier")
            or assignments.get("test_verifier", ""),
        }
        families = {_model_family(model) for model in core.values() if model}
        distinct_count = len(families)
        degraded = any(not core[role] for role in CREW_ROSTER) or distinct_count < 4
        raw_card = data.get("task_card")
        restored_card = (
            parse_task_card(
                raw_card,
                user_q=str(raw_card.get("goal") or ""),
                tier=tier,
                degraded=bool(raw_card.get("degraded")),
                critique_applied=bool(raw_card.get("critique_applied")),
            ).to_dict()
            if isinstance(raw_card, dict) and raw_card
            else {}
        )
        return cls(
            turn_kind=kind,
            crew_size=4,
            tier=tier,
            roles=list(CREW_ROSTER),
            role_assignments={**assignments, **core},
            reason=str(data.get("reason") or "restored"),
            machine_evidence=(
                dict(data.get("machine_evidence") or {})
                if isinstance(data.get("machine_evidence"), dict)
                else {}
            ),
            max_internal_branches=max_budget,
            remaining_internal_branches=remaining,
            llm_calls_session=session_calls,
            total_internal_branches=total_branches,
            session_soft_cap=soft_cap,
            plan_digest=_sanitize_card_text(data.get("plan_digest"))[:6000],
            task_card=restored_card,
            analyst_evidence_hash=str(data.get("analyst_evidence_hash") or "")[:128],
            turn_count=(
                max(0, int(data.get("turn_count") or 0))
                if str(data.get("turn_count") or "0").lstrip("-").isdigit()
                else 0
            ),
            degraded=degraded,
            distinct_model_count=distinct_count,
        )


def merge_machine_evidence(
    current: dict[str, Any] | None,
    client_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge only present tri-state machine evidence; never erase older facts."""
    merged = dict(current or {})
    for key, value in machine_signals_from_client(client_meta).items():
        if value is not None:
            merged[key] = value
    return merged


def _assignment_models(
    models_by_role: dict[str, str] | None, *, risk_profile: str = ""
) -> dict[str, str]:
    src = dict(models_by_role or {})
    leader = src.get("architect") or src.get("judge_fix") or ""
    doer = src.get("doer_logic") or src.get("doer_ui") or ""
    log_analyst = src.get("log_analyst") or src.get("mini_verifier") or ""
    test_verifier = src.get("test_author") or src.get("design_critic") or ""
    return {
        "leader": leader,
        "doer": doer,
        "analyst": log_analyst,
        "specialist": test_verifier,
        "log_analyst": log_analyst,
        "test_verifier": test_verifier,
    }


def select_crew(
    *,
    user_q: str,
    messages: list[dict[str, Any]] | None = None,
    zeus: dict[str, Any] | None = None,
    prior: CrewSession | None = None,
    models_by_role: dict[str, str] | None = None,
    unhealthy: set[str] | None = None,
    available_models: list[str] | None = None,
    tool_enabled: bool = False,
) -> tuple[CrewDecision, CrewSession]:
    """Select the single sticky crew; only event-required roles become active."""
    signals = detect_adaptive_signals(user_q=user_q, messages=messages, zeus=zeus)
    kind = TurnKind(signals["turn_kind"])
    recovered_without_state = kind is not TurnKind.BOOTSTRAP and prior is None
    if recovered_without_state:
        kind = TurnKind.BOOTSTRAP
    previous = prior or CrewSession()
    observed_evidence = collect_tool_evidence(
        messages,
        merge_machine_evidence(
            previous.machine_evidence if prior is not None else {},
            zeus if isinstance(zeus, dict) else None,
        ),
    )
    fresh = _assignment_models(models_by_role)
    dead = set(unhealthy or ())
    available = [m for m in list(available_models or ()) if m and m not in dead]

    def pick(role: str, families: tuple[str, ...]) -> str:
        sticky = str(previous.role_assignments.get(role) or "")
        candidates = [
            str(fresh.get(role) or ""),
            sticky,
            *available,
        ]
        for family in families:
            found = next(
                (
                    model
                    for model in candidates
                    if model and model not in dead and _model_family(model) == family
                ),
                "",
            )
            if found:
                return found
        # Role ownership is explicit. Missing GPT/Grok/DeepSeek/Opus degrades
        # the crew instead of silently handing that responsibility elsewhere.
        return ""

    selected = {
        "leader": pick("leader", ("claude",)),
        "doer": pick("doer", ("gpt",)),
        "analyst": pick("analyst", ("deepseek",)),
        "verifier": pick("test_verifier", ("grok",)),
    }
    # Compatibility aliases consumed by runtime/API telemetry.
    selected["log_analyst"] = selected["analyst"]
    selected["test_verifier"] = selected["verifier"]
    roles = list(CREW_ROSTER)
    size = len(roles)
    distinct_count = len({_model_family(selected[r]) for r in roles if selected[r]})
    degraded = any(not selected[role] for role in roles) or distinct_count < len(roles)
    if kind is TurnKind.BOOTSTRAP:
        tier = task_card_tier(user_q=user_q, zeus=zeus)
        active = ["leader", "doer"]
        reason = "recovered_tool_bootstrap" if recovered_without_state else "new_task_card"
        budget = 4 if tier == "serious" else 2
    else:
        tier = previous.tier if previous.tier in ("compact", "serious") else "compact"
        latest = (
            observed_evidence.get("last_tool_event")
            if isinstance(observed_evidence.get("last_tool_event"), dict)
            else {}
        )
        diff_event = bool(
            latest.get("diff_nonempty")
            or latest.get("mutates_diff")
            or (
                observed_evidence.get("diff_seq")
                and not observed_evidence.get("fresh_green_test")
            )
        )
        needs_test_plan = diff_event and not observed_evidence.get("test_plan_command")
        if signals.get("exec_failed"):
            active = ["analyst"]
            if needs_test_plan:
                active.append("verifier")
            active.append("doer")
            reason = "fresh_failed_machine_evidence"
        elif needs_test_plan:
            active, reason = ["verifier", "doer"], "diff_requires_test_plan"
        else:
            active, reason = ["doer"], "sticky_tool_continuation"
        if "verifier" in active and not selected["verifier"]:
            active.remove("verifier")
            reason = "deterministic_test_fallback"
        budget = 3
    soft_cap_hit = (
        prior is not None
        and previous.total_internal_branches >= previous.session_soft_cap
    )
    if soft_cap_hit:
        active = []
        budget = 0
        reason = "session_soft_cap"
    elif prior is not None:
        remaining_session = max(
            0,
            int(previous.session_soft_cap)
            - int(previous.total_internal_branches),
        )
        budget = min(budget, remaining_session)
    decision = CrewDecision(
        turn_kind=kind,
        crew_size=size,
        tier=tier,
        active_roles=active,
        role_assignments=selected,
        reason=reason,
        max_internal_branches=budget,
        remaining_internal_branches=budget,
        degraded=degraded,
        distinct_model_count=distinct_count,
    )
    session = CrewSession(
        turn_kind=kind,
        crew_size=size,
        tier=tier,
        roles=roles,
        role_assignments=selected,
        reason=reason,
        machine_evidence=observed_evidence,
        max_internal_branches=budget,
        remaining_internal_branches=budget,
        llm_calls_session=(
            previous.llm_calls_session
            if kind is not TurnKind.BOOTSTRAP and prior is not None
            else 0
        ),
        total_internal_branches=(
            previous.total_internal_branches
            if kind is not TurnKind.BOOTSTRAP and prior is not None
            else 0
        ),
        session_soft_cap=(
            previous.session_soft_cap
            if kind is not TurnKind.BOOTSTRAP and prior is not None
            else _session_soft_cap()
        ),
        plan_digest=(
            previous.plan_digest
            if kind is not TurnKind.BOOTSTRAP and prior is not None
            else ""
        ),
        task_card=(
            dict(previous.task_card)
            if kind is not TurnKind.BOOTSTRAP and prior is not None
            else {}
        ),
        analyst_evidence_hash=(
            previous.analyst_evidence_hash
            if kind is not TurnKind.BOOTSTRAP and prior is not None
            else ""
        ),
        turn_count=previous.turn_count + 1,
        degraded=degraded,
        distinct_model_count=distinct_count,
    )
    return decision, session
