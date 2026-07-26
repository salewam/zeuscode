"""Role→Model table + curator resolve (Role Routing Epic 1 / AD-21/32).

``fusion/*`` must not import ``routers.*``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .model_power import TEST_AUTHOR_MIN, power_score

ProductMode = Literal["simple", "power", "custom"]
TaskKind = Literal[
    "light", "ui", "tests", "review", "architecture", "code", "general"
]

ROLE_TABLE_VERSION = "v1"

# task_kind → default doer role (+ verify roles attached by pipeline)
_TASK_DEFAULT_DOER: dict[str, str] = {
    "light": "doer_logic",
    "ui": "doer_ui",
    "tests": "doer_logic",
    "review": "doer_logic",
    "architecture": "doer_logic",
    "code": "doer_logic",
    "general": "doer_logic",
}

# role × mode → (primary, fallback) — only ids from preset stacks / user custom
_ROLE_MODE_TABLE: dict[str, dict[ProductMode, tuple[str, ...]]] = {
    "doer_ui": {
        "simple": ("claude-haiku-4-5", "gemini-3-pro", "deepseek-v4-flash"),
        "power": ("gemini-3.1-pro", "claude-opus-4-8", "deepseek-v4-pro"),
        "custom": (),
    },
    "doer_logic": {
        "simple": ("gemini-3-pro", "deepseek-v4-flash", "claude-haiku-4-5"),
        "power": ("claude-opus-4-8", "deepseek-v4-pro", "gemini-3.1-pro"),
        "custom": (),
    },
    "log_analyst": {
        "simple": ("deepseek-v4-flash",),
        "power": ("deepseek-v4-pro", "deepseek-v4-flash"),
        "custom": (),
    },
    "mini_verifier": {
        "simple": ("deepseek-v4-flash", "claude-haiku-4-5"),
        "power": ("deepseek-v4-flash", "deepseek-v4-pro"),
        "custom": (),
    },
    "architect": {
        "simple": (),
        "power": ("claude-opus-4-8", "gemini-3.1-pro"),
        "custom": (),
    },
    "test_author": {
        "simple": (),
        "power": ("claude-opus-4-8", "gemini-3.1-pro"),
        "custom": (),
    },
    "judge_fix": {
        "simple": ("gemini-3-pro", "claude-haiku-4-5"),
        "power": ("claude-opus-4-8", "gemini-3.1-pro"),
        "custom": (),
    },
    # Pre-dev interviewer — Gemini-first (clarifier.py also has pick_clarifier_model)
    "clarifier": {
        "simple": ("gemini-3-pro", "claude-haiku-4-5"),
        "power": ("gemini-3.1-pro", "gemini-3-pro", "gemini-3-flash"),
        "custom": (),
    },
}

_PRESET_STACKS: dict[ProductMode, tuple[str, ...]] = {
    "simple": ("deepseek-v4-flash", "gemini-3-pro", "claude-haiku-4-5"),
    "power": ("claude-opus-4-8", "deepseek-v4-pro", "gemini-3.1-pro"),
    "custom": (),
}


@dataclass
class RoleAssignment:
    role: str
    model_id: str | None
    fallback_used: bool = False


@dataclass
class RoleResolveResult:
    product_mode: ProductMode
    stack: list[str]
    curator_model: str | None
    roles: list[str]
    models_by_role: dict[str, str]
    assignments: list[RoleAssignment] = field(default_factory=list)
    role_table: str = ROLE_TABLE_VERSION
    has_strong: bool = False  # any model ≥ TEST_AUTHOR_MIN
    meta: dict[str, Any] = field(default_factory=dict)


def normalize_task_kind(raw: str | None) -> TaskKind:
    t = (raw or "general").strip().lower()
    aliases = {
        "test": "tests",
        "plan": "architecture",
        "implement": "code",
        "debug": "code",
        "chat": "light",
        "docs": "light",
    }
    t = aliases.get(t, t)
    if t in _TASK_DEFAULT_DOER:
        return t  # type: ignore[return-value]
    return "general"


def resolve_stack(
    product_mode: str,
    *,
    panel: list[str] | None = None,
    custom_models: list[str] | None = None,
) -> list[str]:
    """User-chosen stack only — never invent out-of-stack models (AD-21)."""
    mode: ProductMode = (
        product_mode if product_mode in ("simple", "power", "custom") else "power"
    )
    if mode == "custom":
        src = list(custom_models or panel or [])
        out: list[str] = []
        for m in src:
            mid = (m or "").strip()
            if mid and mid not in out:
                out.append(mid)
            if len(out) >= 3:
                break
        return out
    preset = list(_PRESET_STACKS[mode])
    if panel:
        # Prefer panel order intersecting preset; keep preset membership
        inter = [m for m in panel if m in preset]
        if inter:
            rest = [m for m in preset if m not in inter]
            return inter + rest
    return preset


def pick_curator(stack: list[str], *, unhealthy: set[str] | None = None) -> str | None:
    """Curator = max power_score in stack; skip unhealthy when alternatives exist."""
    if not stack:
        return None
    dead = set(unhealthy or ())
    ready = [m for m in stack if m not in dead] or list(stack)
    return max(ready, key=lambda m: (power_score(m), ready.index(m)))


def _pick_from_stack(
    candidates: tuple[str, ...],
    stack: list[str],
    *,
    unhealthy: set[str] | None = None,
) -> tuple[str | None, bool]:
    dead = set(unhealthy or ())
    stack_set = set(stack)
    # Prefer table order, only if in user stack
    for mid in candidates:
        if mid in stack_set and mid not in dead:
            return mid, mid != candidates[0]
    # Fallback: any healthy in stack matching candidate family / any stack member
    for mid in stack:
        if mid not in dead and mid in candidates:
            return mid, True
    for mid in stack:
        if mid not in dead:
            return mid, True
    return (stack[0] if stack else None), True


def assign_role_model(
    role: str,
    product_mode: str,
    stack: list[str],
    *,
    unhealthy: set[str] | None = None,
) -> RoleAssignment:
    mode: ProductMode = (
        product_mode if product_mode in ("simple", "power", "custom") else "power"
    )
    table = _ROLE_MODE_TABLE.get(role) or {}
    candidates = table.get(mode) or ()
    if mode == "custom" or not candidates:
        # Custom: pick from stack by score for the role
        mid = pick_curator(stack, unhealthy=unhealthy) if role in (
            "architect",
            "test_author",
            "judge_fix",
            "doer_logic",
        ) else (stack[0] if stack else None)
        if role == "doer_ui" and stack:
            # Prefer gemini-class if present else curator
            for pref in ("gemini-3.1-pro", "gemini-3-pro", "claude-haiku-4-5"):
                if pref in stack and pref not in set(unhealthy or ()):
                    mid = pref
                    break
        if role == "clarifier" and stack:
            from .clarifier import pick_clarifier_model

            mid = pick_clarifier_model(stack, unhealthy=unhealthy, curator=mid)
        if role == "log_analyst":
            mid = None
            for m in stack:
                if "deepseek" in m.lower() and m not in set(unhealthy or ()):
                    mid = m
                    break
        return RoleAssignment(role=role, model_id=mid, fallback_used=False)

    mid, fb = _pick_from_stack(candidates, stack, unhealthy=unhealthy)
    # Score gates for strong roles
    if role in ("architect", "test_author") and mid and power_score(mid) < TEST_AUTHOR_MIN:
        strong = [m for m in stack if power_score(m) >= TEST_AUTHOR_MIN]
        if strong:
            mid = max(strong, key=power_score)
            fb = True
        else:
            mid = None
    return RoleAssignment(role=role, model_id=mid, fallback_used=fb)


def resolve_roles(
    *,
    product_mode: str,
    task_kind: str | None,
    panel: list[str] | None = None,
    custom_models: list[str] | None = None,
    unhealthy: set[str] | None = None,
    include_verify: bool = True,
) -> RoleResolveResult:
    mode: ProductMode = (
        product_mode if product_mode in ("simple", "power", "custom") else "power"
    )
    stack = resolve_stack(mode, panel=panel, custom_models=custom_models)
    curator = pick_curator(stack, unhealthy=unhealthy)
    kind = normalize_task_kind(task_kind)
    doer_role = _TASK_DEFAULT_DOER.get(kind, "doer_logic")
    roles = [doer_role]
    if include_verify:
        roles.extend(["mini_verifier"])
        # log_analyst is optional — only if stack has a log-capable model
        log_a = assign_role_model("log_analyst", mode, stack, unhealthy=unhealthy)
        if log_a.model_id:
            roles.append("log_analyst")

    models_by_role: dict[str, str] = {}
    assignments: list[RoleAssignment] = []
    for role in roles:
        a = assign_role_model(role, mode, stack, unhealthy=unhealthy)
        assignments.append(a)
        if a.model_id:
            models_by_role[role] = a.model_id

    # AD-23: only healthy models count as ≥ TEST_AUTHOR_MIN (dead opus ≠ "has strong")
    dead = set(unhealthy or ())
    healthy = [m for m in stack if m not in dead]
    has_strong = any(power_score(m) >= TEST_AUTHOR_MIN for m in healthy)
    return RoleResolveResult(
        product_mode=mode,
        stack=stack,
        curator_model=curator,
        roles=roles,
        models_by_role=models_by_role,
        assignments=assignments,
        has_strong=has_strong,
        meta={
            "task_kind": kind,
            "doer_role": doer_role,
            "test_author_min": TEST_AUTHOR_MIN,
            "healthy_n": len(healthy),
        },
    )


def cap_doers(stack: list[str], curator: str | None, *, max_doers: int = 2) -> list[str]:
    """Keep curator first, then next-strongest; length ≤ max_doers (AD-31)."""
    if not stack:
        return []
    ordered = sorted(
        stack,
        key=lambda m: (-power_score(m), stack.index(m)),
    )
    if curator and curator in ordered:
        ordered = [curator] + [m for m in ordered if m != curator]
    return ordered[: max(1, int(max_doers))]
