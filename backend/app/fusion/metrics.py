"""Fusion observability, shadow/canary compare, flags (Epic 4 / AD-9, NFR3).

``fusion/*`` must not import ``routers.*``. Routers/chat call these helpers.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

log = logging.getLogger("zeus.fusion.metrics")

PathName = Literal["FAST", "CASCADE", "RACE", "FULL"]

# ---------------------------------------------------------------------------
# Lexicon / baseline (AD-9, AD-13)
# ---------------------------------------------------------------------------

LEXICON_V1_ID = "lexicon_v1"

# Frozen inputs that form baseline_id. Bump components → new baseline_id.
_BASELINE_COMPONENTS = {
    "policy": "legacy_1v3_v1",
    "lexicon": LEXICON_V1_ID,
    "panel": "simple_power_custom_v1",
}


def compute_baseline_id(components: dict[str, str] | None = None) -> str:
    """Immutable hash(policy + lexicon_v1 + panel constants)."""
    parts = dict(_BASELINE_COMPONENTS)
    if components:
        parts.update({str(k): str(v) for k, v in components.items()})
    blob = "|".join(f"{k}={parts[k]}" for k in sorted(parts))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    return f"bl_{digest}"


DEFAULT_BASELINE_ID = compute_baseline_id()


# ---------------------------------------------------------------------------
# Runtime budgets (AD-12 / FR29) — numbers live in Settings; defaults here.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuntimeBudgets:
    """Presence of timeout/concurrency/retry/disaster/keepalive/rate/overflow."""

    global_timeout_s: float = 180.0
    panel_concurrency: int = 3
    race_concurrency: int = 3
    retry_max: int = 2
    retry_backoff_s: float = 0.4
    thinking_keepalive_s: float = 8.0
    rate_limit_rpm: int = 60
    overflow_context_chars: int = 120_000
    disaster_error_code: str = "fusion_disaster"
    sticky_ttl_hours: float = 24.0


def runtime_budgets_from_settings(settings: Any | None = None) -> RuntimeBudgets:
    if settings is None:
        try:
            from app.config import get_settings

            settings = get_settings()
        except Exception:  # noqa: BLE001
            return RuntimeBudgets()
    return RuntimeBudgets(
        global_timeout_s=float(getattr(settings, "FUSION_GLOBAL_TIMEOUT_S", 180.0)),
        panel_concurrency=int(getattr(settings, "FUSION_PANEL_CONCURRENCY", 3)),
        race_concurrency=int(getattr(settings, "FUSION_RACE_CONCURRENCY", 3)),
        retry_max=int(getattr(settings, "FUSION_RETRY_MAX", 2)),
        retry_backoff_s=float(getattr(settings, "FUSION_RETRY_BACKOFF_S", 0.4)),
        thinking_keepalive_s=float(getattr(settings, "FUSION_THINKING_KEEPALIVE_S", 8.0)),
        rate_limit_rpm=int(getattr(settings, "FUSION_RATE_LIMIT_RPM", 60)),
        overflow_context_chars=int(getattr(settings, "FUSION_OVERFLOW_CONTEXT_CHARS", 120_000)),
        disaster_error_code=str(
            getattr(settings, "FUSION_DISASTER_ERROR_CODE", "fusion_disaster")
        ),
        sticky_ttl_hours=float(getattr(settings, "FUSION_STICKY_TTL_HOURS", 24.0)),
    )


def structured_disaster_error(
    message: str,
    *,
    trace_id: str | None = None,
    code: str | None = None,
) -> dict[str, Any]:
    """AD-12 disaster error shape — never silent empty."""
    budgets = runtime_budgets_from_settings()
    return {
        "error": {
            "type": "fusion_disaster",
            "code": code or budgets.disaster_error_code,
            "message": message,
            "trace_id": trace_id or new_trace_id(),
        }
    }


# ---------------------------------------------------------------------------
# Flags: shadow / canary / kill (AD-9)
# ---------------------------------------------------------------------------

@dataclass
class FusionFlags:
    shadow: bool = False
    canary_pct: float = 0.0
    kill: bool = False
    baseline_id: str = DEFAULT_BASELINE_ID


def load_fusion_flags(settings: Any | None = None) -> FusionFlags:
    if settings is None:
        try:
            from app.config import get_settings

            settings = get_settings()
        except Exception:  # noqa: BLE001
            return FusionFlags()
    baseline = str(getattr(settings, "FUSION_BASELINE_ID", "") or "").strip()
    if not baseline:
        baseline = DEFAULT_BASELINE_ID
    pct = float(getattr(settings, "FUSION_CANARY_PCT", 0.0) or 0.0)
    pct = max(0.0, min(100.0, pct))
    return FusionFlags(
        shadow=bool(getattr(settings, "FUSION_SHADOW_MODE", False)),
        canary_pct=pct,
        kill=bool(getattr(settings, "FUSION_KILL_SWITCH", False)),
        baseline_id=baseline,
    )


def in_canary_cohort(user_id: int | None, canary_pct: float) -> bool:
    """Stable account-cohort canary (not random per request)."""
    if canary_pct <= 0:
        return False
    if canary_pct >= 100:
        return True
    if user_id is None:
        return False
    bucket = hashlib.sha256(f"fusion-canary:{user_id}".encode()).hexdigest()
    # 0..9999 → percent with 0.01 resolution
    rank = int(bucket[:8], 16) % 10_000
    return rank < int(canary_pct * 100)


def resolve_serving_path(
    *,
    candidate_path: str,
    baseline_path: str,
    flags: FusionFlags | None = None,
    user_id: int | None = None,
    user_kill_switch: bool = False,
) -> tuple[str, str]:
    """Return (serving_path, routed_by_flag_suffix).

    Shadow: serve baseline, log candidate.
    Canary: serve candidate only for cohort.
    Kill (global or account): clamp to FAST.
    """
    flags = flags or load_fusion_flags()
    cand = _norm_path(candidate_path)
    base = _norm_path(baseline_path) or "FAST"

    if flags.kill or user_kill_switch:
        return "FAST", "kill_switch"

    if flags.shadow:
        return base, "shadow_baseline"

    if flags.canary_pct > 0 and in_canary_cohort(user_id, flags.canary_pct):
        return cand, "canary"
    if flags.canary_pct > 0:
        return base, "canary_holdout"
    # No canary / shadow → serve candidate (new Path policy live)
    return cand, "serving"


def _norm_path(path: str | None) -> str:
    p = (path or "").strip().upper()
    if p in ("FAST", "CASCADE", "RACE", "FULL"):
        return p
    # legacy 1↔3 bridge
    if p in ("1", "SOLO", "FAST_LEGACY"):
        return "FAST"
    if p in ("3", "FULL_LEGACY", "PANEL"):
        return "FULL"
    return p


def legacy_baseline_path(mode_or_stack: str | None) -> str:
    """First canary baselines legacy 1↔3 (fast↔full)."""
    m = (mode_or_stack or "").strip().lower()
    if m in ("full", "3", "panel"):
        return "FULL"
    return "FAST"


def apply_serving_flags(
    *,
    candidate_path: str,
    baseline_path: str,
    zeus: dict[str, Any] | None = None,
    routed_by: str | None = None,
    phase: str | None = None,
    trace_id: str | None = None,
) -> tuple[str, str, str]:
    """AD-9 clamp: return (serving_path, policy_path, routed_by).

    ``policy_path`` stays the candidate; ``serving_path`` may be baseline under Shadow.
    """
    flags = load_fusion_flags()
    z = zeus if isinstance(zeus, dict) else {}
    uid_raw = z.get("user_id")
    try:
        user_id = int(uid_raw) if uid_raw is not None else None
    except (TypeError, ValueError):
        user_id = None
    cand = _norm_path(candidate_path) or "FAST"
    base = _norm_path(baseline_path) or "FAST"
    serving, flag_suffix = resolve_serving_path(
        candidate_path=cand,
        baseline_path=base,
        flags=flags,
        user_id=user_id,
        user_kill_switch=kill_switch_active(z),
    )
    if flags.shadow or flag_suffix in (
        "shadow_baseline",
        "canary",
        "canary_holdout",
    ):
        log_shadow_compare(
            candidate_path=cand,
            serving_path=serving,
            baseline_id=flags.baseline_id,
            routed_by=flag_suffix,
            phase=phase,
            trace_id=trace_id,
        )
    rb = (routed_by or "auto").strip() or "auto"
    if flag_suffix == "kill_switch":
        rb = "kill_switch"
    elif flag_suffix and flag_suffix != "serving":
        rb = f"{rb}+{flag_suffix}"
    return serving, cand, rb


# ---------------------------------------------------------------------------
# Effort + Kill-Switch prefs helpers (FR23) — precedence zeus.* > prefs > default
# ---------------------------------------------------------------------------

EFFORT_LEVELS = frozenset({"low", "normal", "high", "max"})


def normalize_effort(raw: Any | None) -> str:
    v = str(raw or "").strip().lower()
    if v in EFFORT_LEVELS:
        return v
    if v in ("auto", "", "default", "med", "medium"):
        return "normal"
    return "normal"


def apply_effort_kill_prefs(
    user: Any | None,
    zeus: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fill zeus.effort / zeus.kill_switch from user prefs when omitted."""
    out: dict[str, Any] = dict(zeus) if isinstance(zeus, dict) else {}
    if "effort" not in out or not str(out.get("effort") or "").strip():
        pref_effort = None
        if user is not None:
            pref_effort = getattr(user, "fusion_effort", None)
        out["effort"] = normalize_effort(pref_effort)
    else:
        out["effort"] = normalize_effort(out.get("effort"))

    if "kill_switch" not in out:
        if user is not None and bool(getattr(user, "fusion_kill_switch", 0)):
            out["kill_switch"] = True
        else:
            out["kill_switch"] = False
    else:
        out["kill_switch"] = bool(out.get("kill_switch"))

    # Global kill always surfaces on zeus so policy routed_by=kill_switch (AD-9).
    try:
        if load_fusion_flags().kill:
            out["kill_switch"] = True
    except Exception:  # noqa: BLE001
        pass
    return out


def kill_switch_active(zeus: dict[str, Any] | None, *, global_kill: bool | None = None) -> bool:
    flags = load_fusion_flags() if global_kill is None else None
    gk = flags.kill if global_kill is None else bool(global_kill)
    if gk:
        return True
    if isinstance(zeus, dict) and bool(zeus.get("kill_switch")):
        return True
    return False


def clamp_path_for_kill_switch(path: str, zeus: dict[str, Any] | None = None) -> str:
    if kill_switch_active(zeus):
        return "FAST"
    return _norm_path(path) or path


# ---------------------------------------------------------------------------
# trace_id + in-process counters (NFR3)
# ---------------------------------------------------------------------------

def new_trace_id() -> str:
    return uuid.uuid4().hex


def ensure_trace_id(raw: Any | None = None) -> str:
    s = str(raw or "").strip()
    if s:
        return s[:64]
    return new_trace_id()


@dataclass
class _MetricsState:
    path_by_phase: Counter = field(default_factory=Counter)
    escalate_total: int = 0
    requests_total: int = 0
    routed_by: Counter = field(default_factory=Counter)
    verifier_ok_streak: int = 0
    dead_models: Counter = field(default_factory=Counter)
    billing_drift: int = 0
    shadow_mismatch: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


_STATE = _MetricsState()


def reset_metrics_for_tests() -> None:
    with _STATE.lock:
        _STATE.path_by_phase.clear()
        _STATE.escalate_total = 0
        _STATE.requests_total = 0
        _STATE.routed_by.clear()
        _STATE.verifier_ok_streak = 0
        _STATE.dead_models.clear()
        _STATE.billing_drift = 0
        _STATE.shadow_mismatch = 0
        _TRACE_CTX.clear()
        _TRACE_ORDER.clear()
    reset_rate_limit_for_tests()
    reset_concurrency_semaphores_for_tests()


# Recent routing context by trace_id — feedback enrich (no Elo).
_TRACE_CTX: dict[str, dict[str, Any]] = {}
_TRACE_ORDER: list[str] = []
_TRACE_CTX_MAX = 500


def remember_trace_routing(
    trace_id: str | None,
    *,
    path: str = "",
    phase: str = "",
    leader: str = "",
    routed_by: str = "",
    model_ids: list[str] | None = None,
    baseline_id: str | None = None,
) -> None:
    tid = (trace_id or "").strip()
    if not tid:
        return
    payload = {
        "path": path,
        "phase": phase,
        "leader": leader,
        "routed_by": routed_by,
        "model_ids": list(model_ids or []),
        "baseline_id": baseline_id or load_fusion_flags().baseline_id,
    }
    with _STATE.lock:
        if tid not in _TRACE_CTX:
            _TRACE_ORDER.append(tid)
        _TRACE_CTX[tid] = payload
        while len(_TRACE_ORDER) > _TRACE_CTX_MAX:
            old = _TRACE_ORDER.pop(0)
            _TRACE_CTX.pop(old, None)


def lookup_trace_routing(trace_id: str | None) -> dict[str, Any] | None:
    tid = (trace_id or "").strip()
    if not tid:
        return None
    with _STATE.lock:
        ctx = _TRACE_CTX.get(tid)
        return dict(ctx) if ctx else None


class RateLimitExceeded(RuntimeError):
    """Fusion RPM budget exceeded (AD-12 light enforce)."""


_RATE_HITS: list[float] = []
_RATE_LOCK = threading.Lock()
_panel_sem: asyncio.Semaphore | None = None
_race_sem: asyncio.Semaphore | None = None


def check_rate_limit(*, now: float | None = None) -> None:
    """In-process RPM gate from Settings.FUSION_RATE_LIMIT_RPM."""
    budgets = runtime_budgets_from_settings()
    rpm = max(1, int(budgets.rate_limit_rpm))
    t = float(now if now is not None else time.time())
    with _RATE_LOCK:
        while _RATE_HITS and _RATE_HITS[0] < t - 60.0:
            _RATE_HITS.pop(0)
        if len(_RATE_HITS) >= rpm:
            raise RateLimitExceeded(
                f"fusion rate limit {rpm}/min exceeded"
            )
        _RATE_HITS.append(t)


def reset_rate_limit_for_tests() -> None:
    with _RATE_LOCK:
        _RATE_HITS.clear()


def panel_concurrency_semaphore() -> asyncio.Semaphore:
    """Lazy Semaphore for FULL panel branch concurrency (Settings)."""
    global _panel_sem
    if _panel_sem is None:
        n = max(1, int(runtime_budgets_from_settings().panel_concurrency))
        _panel_sem = asyncio.Semaphore(n)
    return _panel_sem


def race_concurrency_semaphore() -> asyncio.Semaphore:
    """Lazy Semaphore for RACE pair concurrency (Settings)."""
    global _race_sem
    if _race_sem is None:
        n = max(1, int(runtime_budgets_from_settings().race_concurrency))
        _race_sem = asyncio.Semaphore(n)
    return _race_sem


def reset_concurrency_semaphores_for_tests() -> None:
    global _panel_sem, _race_sem
    _panel_sem = None
    _race_sem = None


def observe_request(
    *,
    path: str,
    phase: str,
    routed_by: str,
    escalate_from: str | None = None,
    trace_id: str | None = None,
    leader: str | None = None,
    model_ids: list[str] | None = None,
    baseline_id: str | None = None,
) -> None:
    """Emit Path rates by Phase, escalate%, routed_by histogram."""
    p = _norm_path(path) or str(path)
    ph = (phase or "unknown").strip() or "unknown"
    rb = (routed_by or "unknown").strip() or "unknown"
    bl = baseline_id or load_fusion_flags().baseline_id
    with _STATE.lock:
        _STATE.requests_total += 1
        _STATE.path_by_phase[f"{ph}:{p}"] += 1
        _STATE.routed_by[rb] += 1
        if escalate_from:
            _STATE.escalate_total += 1
    remember_trace_routing(
        trace_id,
        path=p,
        phase=ph,
        leader=str(leader or ""),
        routed_by=rb,
        model_ids=model_ids,
        baseline_id=bl,
    )
    log.info(
        "fusion.observe trace_id=%s path=%s phase=%s routed_by=%s "
        "escalate_from=%s baseline_id=%s",
        trace_id or "-",
        p,
        ph,
        rb,
        escalate_from or "-",
        bl,
    )


def log_shadow_compare(
    *,
    candidate_path: str,
    serving_path: str,
    baseline_id: str | None = None,
    routed_by: str | None = None,
    trace_id: str | None = None,
    phase: str | None = None,
) -> None:
    """Shadow: log candidate vs baseline while serving stays baseline (AD-9)."""
    flags = load_fusion_flags()
    bl = baseline_id or flags.baseline_id
    cand = _norm_path(candidate_path)
    serve = _norm_path(serving_path)
    mismatch = cand != serve
    with _STATE.lock:
        if mismatch:
            _STATE.shadow_mismatch += 1
    log.info(
        "fusion.shadow trace_id=%s baseline_id=%s candidate=%s serving=%s "
        "mismatch=%s routed_by=%s phase=%s",
        trace_id or "-",
        bl,
        cand,
        serve,
        mismatch,
        routed_by or "-",
        phase or "-",
    )


def note_verifier_result(always_ok: bool) -> None:
    with _STATE.lock:
        if always_ok:
            _STATE.verifier_ok_streak += 1
        else:
            _STATE.verifier_ok_streak = 0


def note_dead_model(model_id: str) -> None:
    mid = (model_id or "").strip() or "unknown"
    with _STATE.lock:
        _STATE.dead_models[mid] += 1
    log.warning("fusion.dead_model model_id=%s", mid)


def note_billing_drift() -> None:
    with _STATE.lock:
        _STATE.billing_drift += 1
    log.warning("fusion.billing_drift count=%s", _STATE.billing_drift)


def snapshot_metrics() -> dict[str, Any]:
    with _STATE.lock:
        total = max(1, _STATE.requests_total)
        return {
            "requests_total": _STATE.requests_total,
            "path_by_phase": dict(_STATE.path_by_phase),
            "escalate_pct": round(100.0 * _STATE.escalate_total / total, 3),
            "routed_by": dict(_STATE.routed_by),
            "verifier_ok_streak": _STATE.verifier_ok_streak,
            "dead_models": dict(_STATE.dead_models),
            "billing_drift": _STATE.billing_drift,
            "shadow_mismatch": _STATE.shadow_mismatch,
            "baseline_id": load_fusion_flags().baseline_id,
            "ts": time.time(),
        }


# ---------------------------------------------------------------------------
# Alert stubs (NFR3) — documented thresholds; wire to Onestack later
# ---------------------------------------------------------------------------

ALERT_STUBS: dict[str, dict[str, Any]] = {
    "verifier_always_ok": {
        "signal": "verifier_ok_streak",
        "threshold": 50,
        "severity": "page",
        "action": "rollback canary; check Mini-Verifier / Aspect wiring",
    },
    "billing_drift": {
        "signal": "billing_drift",
        "threshold": 1,
        "severity": "page",
        "action": "freeze Path canary; reconcile FusionResult branches vs UsageLog",
    },
    "dead_models": {
        "signal": "dead_models",
        "threshold": 3,
        "severity": "ticket",
        "action": "mark Leader unhealthy; sticky may rotate on next pick_leader",
    },
}


def check_alert_stubs(snap: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return fired alert stubs (no external notifier in MVP)."""
    s = snap or snapshot_metrics()
    fired: list[dict[str, Any]] = []
    if int(s.get("verifier_ok_streak") or 0) >= ALERT_STUBS["verifier_always_ok"]["threshold"]:
        fired.append({"id": "verifier_always_ok", **ALERT_STUBS["verifier_always_ok"], "value": s["verifier_ok_streak"]})
    if int(s.get("billing_drift") or 0) >= ALERT_STUBS["billing_drift"]["threshold"]:
        fired.append({"id": "billing_drift", **ALERT_STUBS["billing_drift"], "value": s["billing_drift"]})
    dead_total = sum(int(v) for v in (s.get("dead_models") or {}).values())
    if dead_total >= ALERT_STUBS["dead_models"]["threshold"]:
        fired.append({"id": "dead_models", **ALERT_STUBS["dead_models"], "value": dead_total})
    return fired
