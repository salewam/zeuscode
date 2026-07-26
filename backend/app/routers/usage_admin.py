"""Owner-facing product usage feed (JSONL + DB).

Auth: Authorization: Bearer <USAGE_ADMIN_TOKEN>
If USAGE_ADMIN_TOKEN is empty, endpoints return 404 (disabled).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import ProductUsageEvent
from app.usage_analytics import usage_dir

router = APIRouter(tags=["usage-admin"])


def _require_admin(authorization: str | None) -> None:
    token = (get_settings().USAGE_ADMIN_TOKEN or "").strip()
    if not token:
        raise HTTPException(404, "Not found")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer USAGE_ADMIN_TOKEN required")
    raw = authorization.split(" ", 1)[1].strip()
    if raw != token:
        raise HTTPException(403, "Forbidden")


@router.get("/admin/usage/recent")
async def usage_recent(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=1000),
    user_id: int | None = None,
    event: str | None = None,
):
    """Last N product events from SQLite."""
    _require_admin(authorization)
    q = select(ProductUsageEvent).order_by(desc(ProductUsageEvent.id)).limit(limit)
    if user_id is not None:
        q = q.where(ProductUsageEvent.user_id == user_id)
    if event:
        q = q.where(ProductUsageEvent.event == event[:40])
    rows = (await db.execute(q)).scalars().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            meta = json.loads(r.meta_json or "{}")
        except Exception:  # noqa: BLE001
            meta = {}
        out.append(
            {
                "id": r.id,
                "ts": r.created_at.isoformat() if r.created_at else None,
                "event": r.event,
                "source": r.source,
                "user_id": r.user_id,
                "key_prefix": r.key_prefix,
                "model": r.model,
                "stream": bool(r.stream),
                "session_id": r.session_id,
                "prompt_preview": r.prompt_preview,
                "path": r.path,
                "policy_path": r.policy_path,
                "leader": r.leader,
                "routed_by": r.routed_by,
                "trace_id": r.trace_id,
                "status_code": r.status_code,
                "latency_ms": r.latency_ms,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "cost_rub": r.cost_rub,
                "error": r.error,
                "meta": meta,
            }
        )
    return {"ok": True, "count": len(out), "events": out}


@router.get("/admin/usage/today")
async def usage_today(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
    day: str | None = Query(default=None, description="UTC YYYY-MM-DD"),
):
    """Tail of today's (or chosen day's) JSONL file under data/usage/."""
    _require_admin(authorization)
    d = (day or datetime.now(timezone.utc).strftime("%Y-%m-%d")).strip()
    path = usage_dir() / f"{d}.jsonl"
    if not path.is_file():
        return {"ok": True, "day": d, "path": str(path), "count": 0, "events": []}
    lines = path.read_text(encoding="utf-8").splitlines()
    tail = lines[-limit:] if len(lines) > limit else lines
    events: list[Any] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:  # noqa: BLE001
            events.append({"raw": line[:500]})
    return {
        "ok": True,
        "day": d,
        "path": str(path),
        "count": len(events),
        "total_lines": len(lines),
        "events": events,
    }


@router.get("/admin/usage/files")
async def usage_files(authorization: str | None = Header(default=None)):
    """List JSONL files in the usage folder."""
    _require_admin(authorization)
    folder = usage_dir()
    folder.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for p in sorted(folder.glob("*.jsonl"), reverse=True):
        try:
            st = p.stat()
            files.append(
                {
                    "name": p.name,
                    "path": str(p),
                    "bytes": st.st_size,
                    "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
        except Exception:  # noqa: BLE001
            continue
    return {"ok": True, "dir": str(folder), "files": files}
