"""Fusion feedback ingest + routing log (FR24) — no Elo writeback."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.fusion.metrics import ensure_trace_id
from app.models import FusionFeedbackEvent, User
from app.routers.tg_miniapp import tg_user_dep

router = APIRouter(tags=["fusion-feedback"])

FeedbackKind = Literal["up", "down", "regen", "👍", "👎"]


class FeedbackIn(BaseModel):
    trace_id: str = Field(min_length=1, max_length=64)
    event: str = Field(description="up | down | regen | 👍 | 👎")
    path: str | None = None
    phase: str | None = None
    leader: str | None = None
    routed_by: str | None = None
    model_ids: list[str] | None = None
    meta: dict[str, Any] | None = None


def _normalize_event(raw: str) -> str:
    v = (raw or "").strip().lower()
    if v in ("up", "👍", "+1", "thumbsup", "like"):
        return "up"
    if v in ("down", "👎", "-1", "thumbsdown", "dislike"):
        return "down"
    if v in ("regen", "regenerate", "retry"):
        return "regen"
    raise HTTPException(400, "event: up | down | regen")


async def _persist(
    db: AsyncSession,
    *,
    user: User | None,
    body: FeedbackIn,
) -> dict[str, Any]:
    event = _normalize_event(body.event)
    trace_id = ensure_trace_id(body.trace_id)
    # Server-side enrich from observe_request cache when client omits routing fields.
    from app.fusion.metrics import lookup_trace_routing

    ctx = lookup_trace_routing(trace_id) or {}
    path = (body.path or ctx.get("path") or "")[:20]
    phase = (body.phase or ctx.get("phase") or "")[:40]
    leader = (body.leader or ctx.get("leader") or "")[:120]
    routed_by = (body.routed_by or ctx.get("routed_by") or "")[:80]
    model_ids = body.model_ids if body.model_ids is not None else list(ctx.get("model_ids") or [])
    meta = dict(body.meta or {})
    if ctx.get("baseline_id") and "baseline_id" not in meta:
        meta["baseline_id"] = ctx["baseline_id"]
    row = FusionFeedbackEvent(
        user_id=user.id if user else None,
        trace_id=trace_id,
        event=event,
        path=path,
        phase=phase,
        leader=leader,
        routed_by=routed_by,
        model_ids_json=json.dumps(model_ids or [], ensure_ascii=False),
        meta_json=json.dumps(meta, ensure_ascii=False),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    try:
        from app.usage_analytics import log_product_event

        await log_product_event(
            db,
            event="feedback",
            user_id=user.id if user else None,
            source="cabinet",
            path=path,
            leader=leader,
            routed_by=routed_by,
            trace_id=trace_id,
            status_code=200,
            meta={"feedback": event, "phase": phase, "model_ids": model_ids},
        )
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": True,
        "id": row.id,
        "trace_id": trace_id,
        "event": event,
        "elo_writeback": False,
        "enriched": bool(ctx),
    }


@router.post("/me/fusion/feedback")
async def cabinet_feedback(
    body: FeedbackIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cabinet 👍/👎/regen ingest with routing context."""
    return await _persist(db, user=user, body=body)


@router.post("/tg/fusion/feedback")
async def tg_feedback(
    body: FeedbackIn,
    auth=Depends(tg_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """TG Mini App feedback ingest (same store, no Elo)."""
    user, _tg = auth
    return await _persist(db, user=user, body=body)


@router.post("/v1/fusion/feedback")
async def api_key_feedback(
    body: FeedbackIn,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Optional API-key path for Cursor clients; anonymous rejected."""
    from sqlalchemy import select

    from app.auth import hash_api_key
    from app.models import ApiKey

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer API key required")
    raw = authorization.split(" ", 1)[1].strip()
    digest = hash_api_key(raw)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.revoked == 0)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(401, "invalid API key")
    user = await db.get(User, key.user_id)
    return await _persist(db, user=user, body=body)
