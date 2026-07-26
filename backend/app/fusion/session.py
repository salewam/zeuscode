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
