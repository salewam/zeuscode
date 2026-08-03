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

ROLE_TABLE_VERSION = "single-crew-v1"

# Face / architect / judge — Opus 4.6 (4.8 убран из роутинга).
FACE_MODEL_POWER = "claude-opus-4-6"

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

# role × mode → (primary, fallback)
# 2026-07-30 A6: gpt-5.4/luna DOWN → gpt-5.4-mini; gemini-3* EMPTY → grok-4.3;
# deepseek-v4-flash EMPTY → deepseek-v4-pro.
_ROLE_MODE_TABLE: dict[str, dict[ProductMode, tuple[str, ...]]] = {
    "doer_ui": {
        "simple": ("gpt-5.4", "gpt-5.4-mini", "claude-haiku-4-5"),
        "power": ("gpt-5.4", "gpt-5.4-mini", "claude-opus-4-6"),
        "custom": (),
    },
    "design_critic": {
        "simple": ("grok-4.5", "grok-4.3", "claude-haiku-4-5"),
        "power": ("grok-4.5", "grok-4.3", "claude-haiku-4-5"),
        "custom": (),
    },
    "doer_logic": {
        "simple": ("gpt-5.4", "gpt-5.4-mini", "claude-haiku-4-5"),
        "power": ("gpt-5.4", "gpt-5.4-mini", "claude-opus-4-6"),
        "custom": (),
    },
    # Target schools: Gemini / Grok / DeepSeek.
    "researcher_a": {
        "simple": ("gemini-3.1-pro-preview", "gemini-3-pro-preview", "grok-4.3"),
        "power": ("gemini-3.1-pro-preview", "gemini-3-pro-preview", "grok-4.3"),
        "custom": (),
    },
    "researcher_b": {
        "simple": ("grok-4.3", "claude-haiku-4-5"),
        "power": ("grok-4.3", "claude-haiku-4-5"),
        "custom": (),
    },
    "researcher_c": {
        "simple": ("deepseek-v4-pro",),
        "power": ("deepseek-v4-pro",),
        "custom": (),
    },
    "analyst": {
        "simple": ("deepseek-v4-pro",),
        "power": ("deepseek-v4-pro", "claude-haiku-4-5"),
        "custom": (),
    },
    "log_analyst": {
        "simple": ("deepseek-v4-pro",),
        "power": ("deepseek-v4-pro", "claude-haiku-4-5"),
        "custom": (),
    },
    "mini_verifier": {
        "simple": ("claude-haiku-4-5", "deepseek-v4-pro"),
        "power": ("claude-haiku-4-5", "deepseek-v4-pro"),
        "custom": (),
    },
    "architect": {
        "simple": ("claude-opus-4-6", "gpt-5.4-mini"),
        "power": ("claude-opus-4-6", "gpt-5.4-mini"),
        "custom": (),
    },
    "test_author": {
        "simple": ("grok-4.5", "grok-4.3", "claude-haiku-4-5"),
        "power": ("grok-4.5", "grok-4.3", "claude-haiku-4-5"),
        "custom": (),
    },
    "judge_fix": {
        "simple": ("claude-haiku-4-5", "grok-4.3"),
        "power": ("claude-opus-4-6", "gpt-5.4-mini"),
        "custom": (),
    },
    "clarifier": {
        "simple": ("claude-haiku-4-5", "grok-4.3"),
        "power": ("grok-4.3", "claude-haiku-4-5"),
        "custom": (),
    },
}

# Stack = меню ролей (панель на turn ≤ 3).
_PRESET_STACKS: dict[ProductMode, tuple[str, ...]] = {
    "simple": (
        "claude-opus-4-6",
        "gpt-5.4",
        "gpt-5.4-mini",
        "deepseek-v4-pro",
        "grok-4.5",
        "grok-4.3",
        "claude-haiku-4-5",
    ),
    "power": (
        "claude-opus-4-6",
        "gemini-3.1-pro-preview",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.3-codex-spark",
        "deepseek-v4-pro",
        "grok-4.5",
        "grok-4.3",
        "claude-haiku-4-5",
        "gemini-3-pro-preview",
        "claude-sonnet-4-6",
    ),
    "custom": (),
}


def max_panel_size() -> int:
    try:
        from app.config import get_settings

        return max(1, min(3, int(getattr(get_settings(), "FUSION_MAX_PANEL", 3) or 3)))
    except Exception:  # noqa: BLE001
        return 3

# omp-style client aliases → internal RR role (None = special pick)
_ALIAS_TO_ROLE: dict[str, str | None] = {
    "default": "doer_logic",
    "smol": "mini_verifier",
    "slow": "architect",
    "plan": "architect",
    "designer": "doer_ui",
    "commit": "mini_verifier",
    "task": "doer_logic",
    "advisor": "judge_fix",
    "tiny": "mini_verifier",
    "vision": None,
}

# Public labels for /me + TG docs (omp Ctrl+P parity)
MODEL_ALIAS_INFO: tuple[dict[str, str], ...] = (
    {"id": "default", "title": "Default", "hint": "Основная работа (doer)"},
    {"id": "smol", "title": "Fast", "hint": "Mini / быстрый слой (в power = DeepSeek Pro)"},
    {"id": "slow", "title": "Thinking", "hint": "Сильная модель (architect ≥950)"},
    {"id": "plan", "title": "Architect", "hint": "План / Brief"},
    {"id": "designer", "title": "Designer", "hint": "UI / лендинг"},
    {"id": "commit", "title": "Commit", "hint": "Короткие правки / сообщения"},
    {"id": "task", "title": "Subtask", "hint": "Воркеры pipeline v1"},
    {"id": "advisor", "title": "Advisor", "hint": "Второй взгляд (judge / Soft-Stop)"},
    {"id": "tiny", "title": "Tiny", "hint": "Фон / классификация"},
    {"id": "vision", "title": "Vision", "hint": "Картинки (если есть в стеке)"},
)


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
    model_aliases: dict[str, str] = field(default_factory=dict)
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
            if len(out) >= max_panel_size():
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
    prefer_cheap: bool = False,
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
    healthy = [m for m in stack if m not in dead]
    if not healthy:
        return None, True
    # Mini/log: never silently promote Opus when DeepSeek key is missing
    if prefer_cheap:
        return min(healthy, key=lambda m: (power_score(m), healthy.index(m))), True
    return healthy[0], True


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
        dead = set(unhealthy or ())
        family_by_role = {
            "architect": ("claude",),
            "doer_logic": ("gpt",),
            "test_author": ("grok",),
            "log_analyst": ("deepseek",),
        }
        families = family_by_role.get(role, ())
        mid = next(
            (
                model
                for family in families
                for model in stack
                if model not in dead and family in model.lower()
            ),
            None,
        )
        if not families:
            mid = next((model for model in stack if model not in dead), None)
        if role == "doer_ui" and stack:
            # Prefer gemini-class, then GPT, else curator
            for pref in (
                "gpt-5.4-mini",
                "grok-4.3",
                "deepseek-v4-pro",
                "claude-haiku-4-5",
            ):
                if pref in stack and pref not in set(unhealthy or ()):
                    mid = pref
                    break
        if role == "clarifier" and stack:
            from .clarifier import pick_clarifier_model

            mid = pick_clarifier_model(stack, unhealthy=unhealthy, curator=mid)
        return RoleAssignment(role=role, model_id=mid, fallback_used=False)

    mid, fb = _pick_from_stack(
        candidates,
        stack,
        unhealthy=unhealthy,
        prefer_cheap=role in ("mini_verifier", "log_analyst"),
    )
    if role == "clarifier" and stack:
        from .clarifier import pick_clarifier_model

        picked = pick_clarifier_model(stack, unhealthy=unhealthy, curator=mid)
        if picked:
            fb = bool(candidates) and picked != candidates[0]
            mid = picked
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
    """Resolve one ZeusCode crew roster.

    ``task_kind`` remains telemetry/UI compatibility only; it cannot change the
    coding runtime topology or choose a model by power score.
    """
    mode: ProductMode = (
        product_mode if product_mode in ("simple", "power", "custom") else "power"
    )
    stack = resolve_stack(mode, panel=panel, custom_models=custom_models)
    kind = normalize_task_kind(task_kind)
    doer_role = "doer_logic"
    roles = ["architect", doer_role]
    if include_verify:
        roles.extend(["log_analyst", "test_author"])

    models_by_role: dict[str, str] = {}
    assignments: list[RoleAssignment] = []
    for role in roles:
        a = assign_role_model(role, mode, stack, unhealthy=unhealthy)
        assignments.append(a)
        if a.model_id:
            models_by_role[role] = a.model_id

    oversight = {
        role: models_by_role[role]
        for role in ("architect", "test_author")
        if role in models_by_role
    }
    curator = models_by_role.get("architect")
    if not curator:
        # Compatibility fallback is table order, not a power-score decision.
        curator = next((m for m in stack if m not in set(unhealthy or ())), None)

    # AD-23: only healthy models count as ≥ TEST_AUTHOR_MIN (dead opus ≠ "has strong")
    dead = set(unhealthy or ())
    healthy = [m for m in stack if m not in dead]
    has_strong = any(power_score(m) >= TEST_AUTHOR_MIN for m in healthy)
    aliases = resolve_model_aliases(mode, stack, unhealthy=unhealthy)
    # Live crew watch on every non-light coding/work task
    crew_watch = False
    return RoleResolveResult(
        product_mode=mode,
        stack=stack,
        curator_model=curator,
        roles=roles,
        models_by_role=models_by_role,
        model_aliases=aliases,
        assignments=assignments,
        has_strong=has_strong,
        meta={
            "task_kind": kind,
            "doer_role": doer_role,
            "test_author_min": TEST_AUTHOR_MIN,
            "healthy_n": len(healthy),
            "crew_linked": bool(oversight),
            "oversight": oversight,
            "crew_watch": crew_watch,
            "unhealthy": sorted(dead),
        },
    )


def cap_doers(stack: list[str], curator: str | None, *, max_doers: int = 2) -> list[str]:
    """Keep curator first, then next-strongest; length ≤ max_doers (AD-31).

    For pipeline=v1 / Soft-Stop. Small-path execute panels use
    ``role_execute_panel`` instead (doer-first, curator out of hot path).
    """
    if not stack:
        return []
    ordered = sorted(
        stack,
        key=lambda m: (-power_score(m), stack.index(m)),
    )
    if curator and curator in ordered:
        ordered = [curator] + [m for m in ordered if m != curator]
    return ordered[: max(1, int(max_doers))]


def role_execute_panel(
    roles: RoleResolveResult | None,
    *,
    pipeline: str,
    max_doers: int | None = None,
) -> tuple[list[str], str | None]:
    """Build execute panel + leader from roles (fixes Leader≠role on small).

    - ``small``: doer first (flash/pro/gemini per task); curator NOT forced in.
    - ``fallback_single``: curator one-shot.
    - ``v1``: curator-led cap_doers (Brief→tests→doers).

    Returns ``(panel, execute_leader)``. ``roles.curator_model`` stays Soft-Stop/Judge.
    """
    if not roles or not roles.stack:
        return [], None
    pipe = (pipeline or "small").strip().lower()
    curator = roles.curator_model
    kind = str((roles.meta or {}).get("task_kind") or "general")
    doer_role = str((roles.meta or {}).get("doer_role") or "doer_logic")
    doer = (roles.models_by_role or {}).get(doer_role)

    if pipe == "fallback_single":
        dead = {str(x) for x in ((roles.meta or {}).get("unhealthy") or [])}
        healthy_stack = [m for m in roles.stack if m not in dead]
        mid = (
            (curator if curator in healthy_stack else None)
            or (doer if doer in healthy_stack else None)
            or (healthy_stack[0] if healthy_stack else None)
        )
        return ([mid] if mid else []), mid

    if pipe == "v1":
        # Thin v1: curator (Brief/Judge) + primary doer — never seat unhealthy models.
        dead = {str(x) for x in ((roles.meta or {}).get("unhealthy") or [])}
        healthy_stack = [m for m in roles.stack if m not in dead]
        n = 2 if max_doers is None else max(1, int(max_doers))
        panel: list[str] = []
        if curator and curator in healthy_stack:
            panel.append(curator)
        if doer and doer in healthy_stack and doer not in panel:
            panel.append(doer)
        if len(panel) < n:
            for mid in cap_doers(list(healthy_stack), curator, max_doers=n):
                if mid not in panel and mid not in dead:
                    panel.append(mid)
                if len(panel) >= n:
                    break
        panel = panel[:n]
        lead = (curator if curator in panel else None) or (panel[0] if panel else None)
        return panel, lead

    # small — single doer by default (bench max_branches + latency).
    # Backup only when caller asks max_doers≥2.
    if max_doers is not None:
        n = max(1, int(max_doers))
    else:
        n = 1
    panel: list[str] = []
    if doer and doer in roles.stack:
        panel.append(doer)
    # Optional backup from same role table (not curator unless that's the only left)
    mode: ProductMode = roles.product_mode
    cands = (_ROLE_MODE_TABLE.get(doer_role) or {}).get(mode) or ()
    for mid in cands:
        if mid in roles.stack and mid not in panel:
            panel.append(mid)
        if len(panel) >= n:
            break
    if not panel and curator:
        panel = [curator]
    elif not panel and roles.stack:
        panel = [roles.stack[0]]
    panel = panel[:n]
    lead = panel[0] if panel else None
    return panel, lead


def _pick_vision_model(stack: list[str], *, unhealthy: set[str] | None = None) -> str | None:
    dead = set(unhealthy or ())
    ready = [m for m in stack if m and m not in dead] or list(stack)
    for pref in ("gpt-5.4-mini", "grok-4.3", "deepseek-v4-pro", "claude-opus-4-6"):
        if pref in ready:
            return pref
    for m in ready:
        low = m.lower()
        if "gemini" in low or "gpt" in low or "vision" in low:
            return m
    return ready[0] if ready else None


def pick_vision_model(stack: list[str], *, unhealthy: set[str] | None = None) -> str | None:
    """Public alias for vision role pick (UI live verify / omp alias)."""
    return _pick_vision_model(stack, unhealthy=unhealthy)


def resolve_model_aliases(
    product_mode: str,
    stack: list[str],
    *,
    unhealthy: set[str] | None = None,
) -> dict[str, str]:
    """Map omp-style aliases (smol/slow/plan/…) → model ids from user stack."""
    mode: ProductMode = (
        product_mode if product_mode in ("simple", "power", "custom") else "power"
    )
    if not stack:
        return {}
    dead = set(unhealthy or ())
    out: dict[str, str] = {}
    for alias, role in _ALIAS_TO_ROLE.items():
        mid: str | None = None
        if alias == "vision":
            mid = _pick_vision_model(stack, unhealthy=unhealthy)
        elif role:
            a = assign_role_model(role, mode, stack, unhealthy=unhealthy)
            mid = a.model_id
            if not mid and role in ("architect", "test_author"):
                mid = pick_curator(stack, unhealthy=unhealthy)
            if not mid and alias in ("smol", "tiny", "commit"):
                cheap = [m for m in stack if m not in dead] or list(stack)
                mid = min(cheap, key=power_score)
            if not mid:
                mid = pick_curator(stack, unhealthy=unhealthy)
        if mid:
            out[alias] = mid
    return out
