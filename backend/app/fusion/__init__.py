"""Zeus Fusion public facade.

Callers keep ``from app.fusion import …``. Implementation lives in ``_monolith``
until Path modules (policy/panel/…) take over in later stories.
"""

from __future__ import annotations

from . import _monolith
from ._monolith import (  # noqa: F401
    DEFAULT_PRODUCT_MODE,
    FUSION_IDS,
    PUBLIC_FUSION_MODEL_ID,
    PRODUCT_MODES,
    _CLASSIFIER_TIMEOUT_S,
    _parse_classifier_json,
    apply_classifier_guardrails,
    apply_user_fusion_pref,
    classify_query,
    classify_smart,
    classify_task,
    classifier_features,
    is_fusion_model,
    iter_fusion,
    normalize_product_mode,
    order_panel_leader_first,
    parse_fusion_models_json,
    pick_leader,
    product_mode_from_model_id,
    regex_classify,
    resolve_mode,
    resolve_panel,
    resolve_routing,
    resolve_routing_ex,
    run_fusion,
    sanitize_messages,
)
from .types import BillableState, BranchUsage, FusionResult, PathName  # noqa: F401
from . import judge as judge  # noqa: F401
from . import log_analyst as log_analyst  # noqa: F401
from . import merge as merge  # noqa: F401
from . import metrics as metrics  # noqa: F401
from . import panel as panel  # noqa: F401
from . import pipeline as pipeline  # noqa: F401
from . import policy as policy  # noqa: F401
from . import roles as roles  # noqa: F401
from . import advisor as advisor  # noqa: F401
from . import clarifier as clarifier  # noqa: F401
from . import crew as crew  # noqa: F401
from . import task_card as task_card  # noqa: F401
from . import plan_artifact as plan_artifact  # noqa: F401
from . import session as session  # noqa: F401
from . import verify as verify  # noqa: F401
from .model_power import TEST_AUTHOR_MIN, power_score  # noqa: F401
from .pipeline import pick_pipeline  # noqa: F401
from .roles import (  # noqa: F401
    MODEL_ALIAS_INFO,
    resolve_model_aliases,
    resolve_roles,
    resolve_stack,
)
from .metrics import (  # noqa: F401
    DEFAULT_BASELINE_ID,
    apply_effort_kill_prefs,
    apply_serving_flags,
    clamp_path_for_kill_switch,
    ensure_trace_id,
    load_fusion_flags,
    log_shadow_compare,
    new_trace_id,
    observe_request,
    resolve_serving_path,
    runtime_budgets_from_settings,
)
from .session import (  # noqa: F401
    StickyState,
    extract_session_id,
    get_sticky,
    put_sticky,
    sticky_leader_hint,
)
from .crew import CrewDecision, CrewSession, TurnKind, select_crew  # noqa: F401
from .task_card import TaskCard, parse_task_card  # noqa: F401

# Same module object as ``_monolith.upstream`` so
# ``patch("app.fusion.upstream.chat_completions")`` still hits live calls.
upstream = _monolith.upstream

# --- Epic 1 append-only re-exports (stories 1.2–1.4) ---
from .brief import SatelliteBrief, build_satellite_brief, satellite_messages_from_brief  # noqa: E402, F401
from ._monolith import (  # noqa: E402, F401
    agents_to_branches,
    build_fusion_result,
    fusion_result_to_dict,
    infer_billable_state,
    prepare_messages_for_policy,
    scrub_messages,
    scrub_secrets,
    stack_to_path,
)

__all__ = [
    "BillableState",
    "BranchUsage",
    "CrewDecision",
    "CrewSession",
    "DEFAULT_BASELINE_ID",
    "DEFAULT_PRODUCT_MODE",
    "FUSION_IDS",
    "PUBLIC_FUSION_MODEL_ID",
    "FusionResult",
    "PRODUCT_MODES",
    "PathName",
    "StickyState",
    "TurnKind",
    "TaskCard",
    "_CLASSIFIER_TIMEOUT_S",
    "_parse_classifier_json",
    "apply_classifier_guardrails",
    "apply_effort_kill_prefs",
    "apply_serving_flags",
    "apply_user_fusion_pref",
    "classify_query",
    "classify_smart",
    "classify_task",
    "classifier_features",
    "clamp_path_for_kill_switch",
    "ensure_trace_id",
    "extract_session_id",
    "get_sticky",
    "is_fusion_model",
    "iter_fusion",
    "judge",
    "load_fusion_flags",
    "log_shadow_compare",
    "metrics",
    "new_trace_id",
    "normalize_product_mode",
    "observe_request",
    "order_panel_leader_first",
    "panel",
    "parse_fusion_models_json",
    "pick_leader",
    "policy",
    "product_mode_from_model_id",
    "put_sticky",
    "regex_classify",
    "resolve_mode",
    "resolve_panel",
    "resolve_routing",
    "resolve_routing_ex",
    "resolve_serving_path",
    "select_crew",
    "parse_task_card",
    "task_card",
    "run_fusion",
    "runtime_budgets_from_settings",
    "sanitize_messages",
    "session",
    "sticky_leader_hint",
    "upstream",
    "verify",
    # Epic 1
    "SatelliteBrief",
    "agents_to_branches",
    "build_fusion_result",
    "build_satellite_brief",
    "fusion_result_to_dict",
    "infer_billable_state",
    "prepare_messages_for_policy",
    "satellite_messages_from_brief",
    "scrub_messages",
    "scrub_secrets",
    "stack_to_path",
    # Role Routing Epic 1
    "TEST_AUTHOR_MIN",
    "log_analyst",
    "merge",
    "pipeline",
    "pick_pipeline",
    "power_score",
    "resolve_roles",
    "roles",
]
