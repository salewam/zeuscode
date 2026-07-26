"""Shared Fusion contracts (Epic 1+). Agents/stories must not fork these shapes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PathName = Literal["FAST", "CASCADE", "RACE", "FULL"]
ComplexityBand = Literal["light", "med", "heavy"]
PipelineName = Literal["small", "v1", "fallback_single"]
SizeName = Literal["small", "large"]
BillableState = Literal[
    "completed",
    "partial_stream",
    "cancelled_no_tokens",
    "cancelled_with_usage",
]

# Closed set — extend only via PRD FR-37 / path policy stories.
RoutedBy = str


@dataclass
class BranchUsage:
    model_id: str
    billable_state: BillableState
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # agent|judge|verifier|classifier|doer_*|mini_verifier|log_analyst|…
    role: str = "agent"
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def model(self) -> str:
        """AD-14 alias — spine names the field ``model``."""
        return self.model_id

    @property
    def usage(self) -> dict[str, int]:
        """AD-14 nested usage shape."""
        return {
            "prompt_tokens": int(self.prompt_tokens or 0),
            "completion_tokens": int(self.completion_tokens or 0),
        }


@dataclass
class FusionResult:
    """Execute→Bill handoff (AD-14). Chat bills from this; do not invent parallel charge paths."""

    path: PathName | str
    policy_path: PathName | str
    routed_by: RoutedBy
    phase: str
    complexity: ComplexityBand | str
    leader: str | None
    branches: list[BranchUsage]
    answer: str
    trace_id: str
    escalate_from: PathName | str | None = None
    # Brownfield bridge until chat fully consumes FusionResult:
    completion: dict[str, Any] | None = None
    onestack: dict[str, Any] = field(default_factory=dict)
    # Role Routing additive (AD-28) — also mirrored into onestack
    pipeline: PipelineName | str | None = None
    curator_model: str | None = None
    role_table: str | None = None
    roles: list[str] = field(default_factory=list)
    models_by_role: dict[str, str] = field(default_factory=dict)
    gate: str | None = None
    gate_reasons: list[str] = field(default_factory=list)
    escalate_count: int = 0
    soft_stop: bool = False
    task_kind: str | None = None
    size: SizeName | str | None = None
