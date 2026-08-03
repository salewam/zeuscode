"""Sticky Leader/stack session store (Epic 4 / AD-7).

Stores only Leader, stack, and phase_meta — Path always comes from classify.
Keyed by ``X-Zeus-Session-Id`` header or ``zeus.session_id``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("zeus.fusion.session")

# Default sticky TTL (hours). Ops can override via Settings.FUSION_STICKY_TTL_HOURS.
DEFAULT_STICKY_TTL_HOURS = 24


@dataclass
class StickyState:
    """Persisted sticky row (Leader/stack only — never Path)."""

    session_id: str
    leader: str | None = None
    stack: list[str] = field(default_factory=list)
    phase_meta: dict[str, Any] = field(default_factory=dict)
    expires_at: datetime | None = None

    @property
    def expired(self) -> bool:
        if self.expires_at is None:
            return False
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp <= datetime.now(timezone.utc)


def extract_session_id(
    *,
    headers: dict[str, str] | None = None,
    zeus: dict[str, Any] | None = None,
    header_value: str | None = None,
) -> str | None:
    """Resolve session key from header / zeus.session_id (AD-7)."""
    if header_value and str(header_value).strip():
        return str(header_value).strip()[:128]
    if headers:
        for key in ("x-zeus-session-id", "X-Zeus-Session-Id", "X-ZEUS-SESSION-ID"):
            raw = headers.get(key)
            if raw and str(raw).strip():
                return str(raw).strip()[:128]
        # case-insensitive scan
        for k, v in headers.items():
            if k.lower() == "x-zeus-session-id" and str(v).strip():
                return str(v).strip()[:128]
    if isinstance(zeus, dict):
        sid = zeus.get("session_id")
        if sid and str(sid).strip():
            return str(sid).strip()[:128]
    return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_stack(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if str(x).strip()][:16]


def _parse_phase_meta(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


async def get_sticky(db: AsyncSession, session_id: str | None) -> StickyState | None:
    """Load non-expired sticky state. Path must NOT be read from here."""
    if not session_id:
        return None
    from app.models import FusionStickySession

    row = await db.get(FusionStickySession, session_id)
    if row is None:
        return None
    state = StickyState(
        session_id=row.session_id,
        leader=(row.leader or None),
        stack=_parse_stack(row.stack_json),
        phase_meta=_parse_phase_meta(row.phase_meta_json),
        expires_at=row.expires_at,
    )
    if state.expired:
        await db.delete(row)
        await db.commit()
        return None
    return state


async def put_sticky(
    db: AsyncSession,
    session_id: str | None,
    *,
    leader: str | None,
    stack: list[str] | None = None,
    phase_meta: dict[str, Any] | None = None,
    ttl_hours: float | None = None,
) -> StickyState | None:
    """Write sticky at request end with the Leader that actually answered (AD-16)."""
    if not session_id:
        return None
    from app.models import FusionStickySession

    try:
        from app.config import get_settings

        cfg_ttl = float(getattr(get_settings(), "FUSION_STICKY_TTL_HOURS", DEFAULT_STICKY_TTL_HOURS))
    except Exception:  # noqa: BLE001
        cfg_ttl = float(DEFAULT_STICKY_TTL_HOURS)
    hours = float(ttl_hours) if ttl_hours is not None else cfg_ttl
    expires = _utcnow() + timedelta(hours=max(0.1, hours))

    stack_list = [str(x).strip() for x in (stack or []) if str(x).strip()][:16]
    meta = dict(phase_meta or {})
    # Never persist Path as sticky authority
    meta.pop("path", None)
    meta.pop("policy_path", None)

    row = await db.get(FusionStickySession, session_id)
    if row is None:
        row = FusionStickySession(session_id=session_id)
        db.add(row)
    row.leader = (leader or "")[:120]
    row.stack_json = json.dumps(stack_list, ensure_ascii=False)
    row.phase_meta_json = json.dumps(meta, ensure_ascii=False)
    row.expires_at = expires
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    log.debug("sticky.put session=%s leader=%s", session_id, leader)
    return StickyState(
        session_id=session_id,
        leader=row.leader or None,
        stack=stack_list,
        phase_meta=meta,
        expires_at=expires,
    )


async def delete_sticky(db: AsyncSession, session_id: str | None) -> bool:
    if not session_id:
        return False
    from app.models import FusionStickySession

    row = await db.get(FusionStickySession, session_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def purge_expired_sticky(db: AsyncSession, *, limit: int = 200) -> int:
    """Best-effort cleanup of expired rows."""
    from app.models import FusionStickySession

    now = _utcnow()
    result = await db.execute(
        select(FusionStickySession)
        .where(FusionStickySession.expires_at < now)
        .limit(max(1, min(limit, 2000)))
    )
    rows = list(result.scalars().all())
    for row in rows:
        await db.delete(row)
    if rows:
        await db.commit()
    return len(rows)


def sticky_leader_hint(state: StickyState | None) -> str | None:
    """Hint for pick_leader — never a Path override."""
    if state is None or state.expired:
        return None
    leader = (state.leader or "").strip()
    return leader or None


def crew_session_from_phase_meta(phase_meta: dict[str, Any] | None):
    """Restore typed adaptive crew state from the existing sticky JSON."""
    from .crew import CrewSession

    meta = phase_meta if isinstance(phase_meta, dict) else {}
    raw = meta.get("crew")
    return CrewSession.from_dict(raw if isinstance(raw, dict) else None)


def merge_crew_phase_meta(
    phase_meta: dict[str, Any] | None,
    crew_state: dict[str, Any] | Any | None,
) -> dict[str, Any]:
    """Add crew state without dropping clarifier/plan sticky fields."""
    meta = dict(phase_meta or {})
    if crew_state is None:
        return meta
    raw = crew_state.to_dict() if hasattr(crew_state, "to_dict") else crew_state
    if isinstance(raw, dict):
        from .crew import CrewSession

        meta["crew"] = CrewSession.from_dict(raw).to_dict()
    return meta


def merge_sticky_phase_meta(
    current: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
    *,
    spent_internal_branches: int = 0,
) -> dict[str, Any]:
    """Deterministically merge one completed response into locked sticky state."""
    from .crew import CrewSession, TurnKind

    base = dict(current) if isinstance(current, dict) else {}
    patch = dict(incoming) if isinstance(incoming, dict) else {}
    old_clarify = base.get("clarify")
    old_plan_artifact = base.get("plan_artifact")
    incoming_crew_raw = patch.get("crew")
    incoming_crew = (
        CrewSession.from_dict(incoming_crew_raw)
        if isinstance(incoming_crew_raw, dict)
        else None
    )
    current_crew_raw = base.get("crew")
    current_crew = (
        CrewSession.from_dict(current_crew_raw)
        if isinstance(current_crew_raw, dict)
        else CrewSession()
    )
    new_task = bool(
        incoming_crew is not None
        and incoming_crew.turn_kind is TurnKind.BOOTSTRAP
    )
    if new_task:
        base.pop("clarify", None)
        base.pop("plan_artifact", None)

    for key, value in patch.items():
        if key in ("crew", "path", "policy_path"):
            continue
        if key == "clarify" and new_task and value == old_clarify:
            continue
        if key == "plan_artifact":
            content = value.get("content") if isinstance(value, dict) else None
            if not content or (new_task and value == old_plan_artifact):
                continue
        base[key] = value

    if incoming_crew is not None:
        spent = max(0, int(spent_internal_branches or 0))
        if new_task:
            incoming_crew.llm_calls_session = max(
                spent, incoming_crew.llm_calls_session
            )
            incoming_crew.total_internal_branches = max(
                spent, incoming_crew.total_internal_branches
            )
        elif isinstance(current_crew_raw, dict):
            incoming_crew.llm_calls_session = (
                current_crew.llm_calls_session + spent
                if spent
                else max(
                    current_crew.llm_calls_session,
                    incoming_crew.llm_calls_session,
                )
            )
            incoming_crew.total_internal_branches = (
                current_crew.total_internal_branches + spent
                if spent
                else max(
                    current_crew.total_internal_branches,
                    incoming_crew.total_internal_branches,
                )
            )
            incoming_crew.turn_count = max(
                current_crew.turn_count + 1,
                incoming_crew.turn_count,
            )
            incoming_crew.machine_evidence = {
                **current_crew.machine_evidence,
                **incoming_crew.machine_evidence,
            }
            if not incoming_crew.plan_digest:
                incoming_crew.plan_digest = current_crew.plan_digest
            incoming_crew.degraded = bool(
                current_crew.degraded or incoming_crew.degraded
            )
        base["crew"] = incoming_crew.to_dict()
    return base


async def atomic_merge_sticky(
    db: AsyncSession,
    session_id: str | None,
    *,
    leader: str | None,
    stack: list[str] | None = None,
    phase_meta: dict[str, Any] | None = None,
    spent_internal_branches: int = 0,
    ttl_hours: float | None = None,
) -> StickyState | None:
    """Lock, merge and commit sticky state once; no schema change required."""
    if not session_id:
        return None
    from app.models import FusionStickySession

    try:
        from app.config import get_settings

        cfg_ttl = float(
            getattr(
                get_settings(),
                "FUSION_STICKY_TTL_HOURS",
                DEFAULT_STICKY_TTL_HOURS,
            )
        )
    except Exception:  # noqa: BLE001
        cfg_ttl = float(DEFAULT_STICKY_TTL_HOURS)
    hours = float(ttl_hours) if ttl_hours is not None else cfg_ttl
    expires = _utcnow() + timedelta(hours=max(0.1, hours))

    stmt = (
        select(FusionStickySession)
        .where(FusionStickySession.session_id == session_id)
        .with_for_update()
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        row = FusionStickySession(session_id=session_id)
        db.add(row)
        current_meta: dict[str, Any] = {}
        current_stack: list[str] = []
    else:
        current_meta = _parse_phase_meta(row.phase_meta_json)
        current_stack = _parse_stack(row.stack_json)

    merged_meta = merge_sticky_phase_meta(
        current_meta,
        phase_meta,
        spent_internal_branches=spent_internal_branches,
    )
    stack_list = [
        str(item).strip()
        for item in (stack if stack is not None else current_stack)
        if str(item).strip()
    ][:16]
    row.leader = ((leader or row.leader or "")[:120])
    row.stack_json = json.dumps(stack_list, ensure_ascii=False)
    row.phase_meta_json = json.dumps(merged_meta, ensure_ascii=False)
    row.expires_at = expires
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    return StickyState(
        session_id=session_id,
        leader=row.leader or None,
        stack=stack_list,
        phase_meta=merged_meta,
        expires_at=expires,
    )
