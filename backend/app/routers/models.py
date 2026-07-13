from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import decode_access_token
from app.catalog import public_catalog, reload_catalog
from app.config import get_settings
from app.db import get_db
from app.kie_sync import sync_kie_catalog
from app.model_policy import filter_catalog_for_user
from app.models import User
from app.polza_sync import sync_polza_prices

router = APIRouter(tags=["models"])
settings = get_settings()


async def _optional_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    # JWT for cabinet; ignore API keys here (hex/zeus) — public catalog fallback
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    return await db.get(User, int(payload["sub"]))


@router.get("/models")
@router.get("/v1/models")
async def list_models(
    ready: bool | None = Query(default=None, description="Filter ready-only models"),
    provider: str | None = Query(default=None),
    modality: str | None = Query(default=None, description="chat|image|video|music"),
    q: str | None = Query(default=None),
    user: User | None = Depends(_optional_user),
):
    rows = filter_catalog_for_user(user, public_catalog())
    if ready is True:
        rows = [r for r in rows if r["ready"]]
    if provider:
        p = provider.lower()
        rows = [r for r in rows if r["provider"].lower() == p]
    if modality:
        mm = modality.lower()
        rows = [r for r in rows if (r.get("modality") or "chat").lower() == mm]
    if q:
        qq = q.lower()
        rows = [
            r
            for r in rows
            if qq in r["id"].lower()
            or qq in r["title"].lower()
            or qq in r["provider"].lower()
            or qq in (r.get("description") or "").lower()
            or qq in (r.get("modality") or "").lower()
        ]
    return {
        "object": "list",
        "markup": settings.MARKUP,
        "count": len(rows),
        "model_family": (getattr(user, "model_family", None) or "") if user else "",
        "data": [
            {
                "id": r["id"],
                "object": "model",
                "owned_by": r["provider"].lower(),
                **r,
            }
            for r in rows
        ],
    }


@router.post("/models/sync")
@router.post("/v1/models/sync")
async def sync_models_from_kie():
    """Pull Kie catalog, then align user RUB prices with Polza.ai."""
    payload = await sync_kie_catalog()
    polza = await sync_polza_prices()
    reload_catalog()
    rows = public_catalog()
    by_mod: dict[str, int] = {}
    for r in rows:
        m = r.get("modality") or "chat"
        by_mod[m] = by_mod.get(m, 0) + 1
    return {
        "ok": True,
        "fetched_at": payload.get("fetched_at"),
        "raw_rows": payload.get("raw_rows"),
        "models_n": payload.get("models_n"),
        "catalog_n": len(rows),
        "by_modality": by_mod,
        "ready_n": sum(1 for r in rows if r.get("ready")),
        "polza": polza,
    }
