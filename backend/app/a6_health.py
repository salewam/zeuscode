"""A6 primary (cheap ~30%) ↔ fallback (~70%) health — default for every model.

Applies to **all** chat models routed via ``upstream.chat_a6`` (research, panel,
judge, etc.). New catalog models inherit this path automatically.

Flow per model:
  1) On 30% key: try up to N live suppliers from pricing ``enable_groups`` order,
     skipping suppliers marked dead for this model+key (default TTL 2h).
  2) Each *transient* failed supplier is remembered as dead for that key lane
     (30% and 70% separately) so the next walk picks *new* groups, not the
     same corpses. Permanent 400/unknown-model errors do not poison health.
  3) If the live 30% walk fails → that model uses 70% key for
     ``A6_PRIMARY_COOLDOWN_S`` (default 15m).
  4) 70% key also walks live suppliers (not only auto) and marks dead the same way.
  5) After cooldown → try 30% again; dead TTL still skips recent failures.
  6) A successful 30% call clears model cooldown and sticks that supplier as
     preferred for the next cheap walk.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Literal

log = logging.getLogger("zeus.a6_health")

KeyLane = Literal["primary", "fallback"]

_lock = threading.Lock()
# Upstream model id → unix time until which cheap key is skipped.
_model_skip_until: dict[str, float] = {}
# (model, key_lane, supplier) → unix time until which supplier is skipped.
_dead_supplier_until: dict[tuple[str, str, str], float] = {}
# model → last-known-good supplier on the cheap (primary) key.
_preferred_primary: dict[str, str] = {}
_groups_cache: dict[str, list[str]] = {}
_groups_fetched_at: float = 0.0
_GROUPS_TTL_S = 600.0
# Default dead-supplier memory (overridden by settings when wired from upstream).
_DEFAULT_DEAD_TTL_S = 7200.0


def _now() -> float:
    return time.time()


def _purge_expired_locked(now: float | None = None) -> None:
    t = _now() if now is None else now
    dead_keys = [k for k, u in _dead_supplier_until.items() if u <= t]
    for k in dead_keys:
        _dead_supplier_until.pop(k, None)
    cool_keys = [m for m, u in _model_skip_until.items() if u <= t]
    for m in cool_keys:
        _model_skip_until.pop(m, None)


def reset_for_tests() -> None:
    """Clear all health state (tests only)."""
    with _lock:
        _model_skip_until.clear()
        _dead_supplier_until.clear()
        _preferred_primary.clear()
        _groups_cache.clear()
        global _groups_fetched_at
        _groups_fetched_at = 0.0


def is_model_cooling(model: str) -> bool:
    mid = (model or "").strip()
    if not mid:
        return False
    with _lock:
        _purge_expired_locked()
        until = _model_skip_until.get(mid, 0.0)
        return _now() < until


def should_try_primary(model: str) -> bool:
    """Cheap key first unless this model is in fallback cooldown."""
    return not is_model_cooling(model)


def mark_model_down(model: str, cooldown_s: float, *, reason: str = "") -> None:
    """No cheap supplier worked for this model — use 70% key for cooldown."""
    mid = (model or "").strip()
    if not mid:
        return
    # Floor 1s so unit tests can expire quickly; prod uses A6_PRIMARY_COOLDOWN_S≥30.
    until = _now() + max(1.0, float(cooldown_s))
    with _lock:
        prev = _model_skip_until.get(mid, 0.0)
        _model_skip_until[mid] = max(prev, until)
        left = max(0.0, _model_skip_until[mid] - _now())
    log.warning(
        "A6_MODEL_DOWN model=%s reason=%s cooldown_left=%.0fs",
        mid,
        reason or "fail",
        left,
    )


def mark_model_up(model: str, *, reason: str = "") -> None:
    mid = (model or "").strip()
    if not mid:
        return
    with _lock:
        _model_skip_until.pop(mid, None)
    log.info("A6_MODEL_UP model=%s reason=%s", mid, reason or "ok")


def mark_supplier_dead(
    model: str,
    supplier: str,
    *,
    key_lane: KeyLane = "primary",
    ttl_s: float = _DEFAULT_DEAD_TTL_S,
    reason: str = "",
) -> None:
    """Remember a dead supplier for this model+key so walks skip it (~2h)."""
    mid = (model or "").strip()
    group = (supplier or "").strip()
    lane = (key_lane or "primary").strip() or "primary"
    if not mid or not group or group == "auto":
        return
    until = _now() + max(1.0, float(ttl_s))
    with _lock:
        key = (mid, lane, group)
        prev = _dead_supplier_until.get(key, 0.0)
        _dead_supplier_until[key] = max(prev, until)
        left = max(0.0, _dead_supplier_until[key] - _now())
        # Drop sticky prefer if this supplier just died on primary.
        if lane == "primary" and _preferred_primary.get(mid) == group:
            _preferred_primary.pop(mid, None)
    log.warning(
        "A6_SUPPLIER_DEAD model=%s key=%s group=%s ttl_left=%.0fs reason=%s",
        mid,
        lane,
        group,
        left,
        reason or "fail",
    )


def is_supplier_dead(
    model: str,
    supplier: str,
    *,
    key_lane: KeyLane = "primary",
) -> bool:
    mid = (model or "").strip()
    group = (supplier or "").strip()
    lane = (key_lane or "primary").strip() or "primary"
    if not mid or not group:
        return False
    with _lock:
        _purge_expired_locked()
        return _now() < _dead_supplier_until.get((mid, lane, group), 0.0)


def mark_supplier_live(
    model: str,
    supplier: str,
    *,
    key_lane: KeyLane = "primary",
) -> None:
    """Sticky prefer on primary success; clear this supplier from dead list."""
    mid = (model or "").strip()
    group = (supplier or "").strip()
    lane = (key_lane or "primary").strip() or "primary"
    if not mid:
        return
    with _lock:
        if group and group != "auto":
            _dead_supplier_until.pop((mid, lane, group), None)
            if lane == "primary":
                _preferred_primary[mid] = group
    if group and group != "auto" and lane == "primary":
        log.info(
            "A6_SUPPLIER_LIVE model=%s key=%s group=%s (preferred)",
            mid,
            lane,
            group,
        )


def preferred_primary_supplier(model: str) -> str | None:
    mid = (model or "").strip()
    if not mid:
        return None
    with _lock:
        pref = _preferred_primary.get(mid)
        if not pref:
            return None
        if _now() < _dead_supplier_until.get((mid, "primary", pref), 0.0):
            return None
        return pref


def live_supplier_groups(
    groups: list[str],
    *,
    model: str,
    key_lane: KeyLane = "primary",
    limit: int = 3,
    prefer: str | None = None,
) -> list[str]:
    """Next N live suppliers from pricing order, skipping dead for model+key.

    Prefers a sticky live supplier first (cheap key), then walks the full
    pricing list so after failures we get *new* groups, not the same three.
    """
    n = max(1, int(limit))
    mid = (model or "").strip()
    lane = (key_lane or "primary").strip() or "primary"
    out: list[str] = []
    seen: set[str] = set()

    def _add(g: str) -> None:
        nonlocal out
        g = (g or "").strip()
        if not g or g in seen:
            return
        if g == "default" and any(x != "default" for x in groups):
            return
        if mid and is_supplier_dead(mid, g, key_lane=lane):  # type: ignore[arg-type]
            return
        seen.add(g)
        out.append(g)

    pref = (prefer or "").strip() or None
    if lane == "primary" and not pref:
        pref = preferred_primary_supplier(mid)
    if pref:
        _add(pref)
    for g in groups:
        if len(out) >= n:
            break
        _add(g)
    if not out and "default" in groups and not (
        mid and is_supplier_dead(mid, "default", key_lane=lane)  # type: ignore[arg-type]
    ):
        out = ["default"]
    return out[:n]


def snapshot() -> dict[str, Any]:
    now = _now()
    with _lock:
        _purge_expired_locked(now)
        cooling = {
            m: round(max(0.0, u - now), 1)
            for m, u in _model_skip_until.items()
            if u > now
        }
        dead = [
            {
                "model": m,
                "key": lane,
                "group": g,
                "ttl_left_s": round(max(0.0, u - now), 1),
            }
            for (m, lane, g), u in sorted(_dead_supplier_until.items())
            if u > now
        ]
        return {
            "cooling_models": cooling,
            "dead_suppliers": dead,
            "preferred_primary": dict(_preferred_primary),
            "groups_cached": len(_groups_cache),
            "groups_cache_age_s": (
                round(now - _groups_fetched_at, 1) if _groups_fetched_at else None
            ),
        }


# --- backward-compatible aliases (old global primary API) -------------------


def is_primary_cooling() -> bool:
    """True if any model is on fallback (legacy aggregate)."""
    with _lock:
        _purge_expired_locked()
        now = _now()
        return any(u > now for u in _model_skip_until.values())


def mark_primary_down(cooldown_s: float, *, reason: str = "") -> None:
    """Legacy: treat as global — prefer mark_model_down(model, …)."""
    mark_model_down("*", cooldown_s, reason=reason)


def mark_primary_up(*, reason: str = "") -> None:
    with _lock:
        _model_skip_until.clear()
        _dead_supplier_until.clear()
        _preferred_primary.clear()
    log.info("A6_PRIMARY_UP reason=%s", reason or "ok")


async def decide_try_primary(
    *,
    base: str,
    key: str,
    probe_model: str,
    cooldown_s: float,
    model: str | None = None,
) -> bool:
    """Legacy entry: per-model cooldown only — no haiku probe."""
    del base, key, probe_model, cooldown_s  # unused; recovery = next live call
    target = (model or "").strip() or "*"
    if target != "*" and is_model_cooling("*"):
        return False
    return should_try_primary(target)


async def get_enable_groups(
    *,
    pricing_base: str,
    model: str,
    timeout: float = 30.0,
) -> list[str]:
    """Supplier group ids for ``model`` from A6 ``/api/pricing`` (cached)."""
    global _groups_fetched_at
    mid = (model or "").strip()
    if not mid:
        return []
    now = _now()
    with _lock:
        if _groups_fetched_at and (now - _groups_fetched_at) < _GROUPS_TTL_S and mid in _groups_cache:
            return list(_groups_cache[mid])

    import httpx

    host = pricing_base.rstrip("/")
    if host.endswith("/v1"):
        host = host[: -len("/v1")]
    url = f"{host}/api/pricing"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url)
        data = r.json() if r.content else {}
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            log.warning("A6_PRICING_BAD status=%s", r.status_code)
            with _lock:
                return list(_groups_cache.get(mid, []))
        fresh: dict[str, list[str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("model_name") or "").strip()
            if not name:
                continue
            groups = [
                str(g).strip()
                for g in (row.get("enable_groups") or [])
                if str(g).strip()
            ]
            # Keep pricing order (A6 array order).
            seen: set[str] = set()
            ordered: list[str] = []
            for g in groups:
                if g not in seen:
                    seen.add(g)
                    ordered.append(g)
            fresh[name] = ordered
        with _lock:
            _groups_cache.clear()
            _groups_cache.update(fresh)
            _groups_fetched_at = _now()
            return list(_groups_cache.get(mid, []))
    except Exception as e:  # noqa: BLE001
        log.warning("A6_PRICING_FAIL err=%s", type(e).__name__)
        with _lock:
            return list(_groups_cache.get(mid, []))


def top_supplier_groups(groups: list[str], *, limit: int = 3) -> list[str]:
    """First N unique groups from pricing order (= top of A6 listing)."""
    n = max(1, int(limit))
    out: list[str] = []
    seen: set[str] = set()
    for g in groups:
        g = (g or "").strip()
        if not g or g in seen:
            continue
        # Prefer real suppliers over the catch-all "default" when ranking.
        if g == "default" and any(x != "default" for x in groups):
            continue
        seen.add(g)
        out.append(g)
        if len(out) >= n:
            break
    if not out and "default" in groups:
        out = ["default"]
    return out


def groups_for_primary_walk(groups: list[str], *, limit: int = 3) -> list[str]:
    """Backward-compatible alias → top N suppliers only (ignores dead registry)."""
    return top_supplier_groups(groups, limit=limit)
