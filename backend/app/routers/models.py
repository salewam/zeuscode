from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import decode_access_token, hash_api_key
from app.catalog import public_catalog, reload_catalog
from app.claude_gateway import gateway_picker_models
from app.config import get_settings
from app.db import get_db
from app.a6_sync import sync_a6_catalog
from app.model_policy import filter_catalog_for_user
from app.models import ApiKey, User
from app.polza_sync import sync_polza_prices

router = APIRouter(tags=["models"])
settings = get_settings()


async def _optional_user(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Cabinet JWT or Zeus API key (Bearer / x-api-key) — full catalog on one key."""
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif x_api_key and x_api_key.strip():
        token = x_api_key.strip()
    if not token:
        return None
    payload = decode_access_token(token)
    if payload and "sub" in payload:
        return await db.get(User, int(payload["sub"]))
    # OpenCode / Cline / Claude / Codex send the product API key on /v1/models
    ok_fmt = (
        token.startswith("zeus_")
        or token.startswith("osk_")
        or (len(token) >= 32 and all(c in "0123456789abcdefABCDEF" for c in token))
    )
    if not ok_fmt:
        return None
    digest = hash_api_key(token)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.revoked == 0)
    )
    key = result.scalar_one_or_none()
    if not key:
        return None
    return await db.get(User, key.user_id)


@router.get("/models")
@router.get("/v1/models")
async def list_models(
    ready: bool | None = Query(default=None, description="Filter ready-only models"),
    provider: str | None = Query(default=None),
    modality: str | None = Query(default=None, description="chat|image|video|music"),
    q: str | None = Query(default=None),
    limit: int | None = Query(
        default=None,
        description="Claude Code gateway discovery sends limit=1000",
    ),
    anthropic_version: str | None = Header(default=None, alias="anthropic-version"),
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
    # Claude Code: GET /v1/models?limit=1000 — only claude*|anthropic* ids enter /model picker.
    # Expose every ready chat model under anthropic.zeuscode/<id> when needed.
    gateway = limit is not None or bool(anthropic_version)
    if gateway:
        data = gateway_picker_models(rows)
        if limit is not None and limit > 0:
            data = data[:limit]
        return {
            "object": "list",
            "data": data,
            "has_more": False,
            "first_id": data[0]["id"] if data else None,
            "last_id": data[-1]["id"] if data else None,
            "count": len(data),
            "owned_by": "zeuscode",
        }
    return {
        "object": "list",
        "markup": settings.MARKUP,
        "count": len(rows),
        "model_family": (getattr(user, "model_family", None) or "") if user else "",
        "data": [
            # OpenAI aliases для Orca совместимости
            {
                "id": "gpt-4",
                "object": "model",
                "owned_by": "zeuscode",
                "display_name": "ZeusCode · GPT-4 (3 models)",
                "title": "GPT-4 (ZeusCode)",
                "provider": "zeuscode",
                "ready": True,
                "modality": "chat",
                "supported_endpoint_types": ["openai"],
            },
            {
                "id": "gpt-4-turbo",
                "object": "model",
                "owned_by": "zeuscode",
                "display_name": "ZeusCode · GPT-4 Turbo (3 models)",
                "title": "GPT-4 Turbo (ZeusCode)",
                "provider": "zeuscode",
                "ready": True,
                "modality": "chat",
                "supported_endpoint_types": ["openai"],
            },
            {
                "id": "gpt-4o",
                "object": "model",
                "owned_by": "zeuscode",
                "display_name": "ZeusCode · GPT-4o (3 models)",
                "title": "GPT-4o (ZeusCode)",
                "provider": "zeuscode",
                "ready": True,
                "modality": "chat",
                "supported_endpoint_types": ["openai"],
            },
            # Остальные модели из каталога
            *[
                {
                    "id": r["id"],
                    "object": "model",
                    "owned_by": r["provider"].lower(),
                    "display_name": (
                        r["title"]
                        if str(r.get("title") or "").startswith("ZeusCode")
                        else f"ZeusCode · {r.get('title') or r['id']}"
                    ),
                    **r,
                }
                for r in rows
            ],
        ],
    }


@router.post("/models/sync")
@router.post("/v1/models/sync")
async def sync_models_from_upstream():
    """Pull A6 catalog, then align user RUB prices with Polza.ai when possible."""
    payload = await sync_a6_catalog()
    polza = await sync_polza_prices()
    reload_catalog()
    rows = public_catalog()
    by_mod: dict[str, int] = {}
    for r in rows:
        m = r.get("modality") or "chat"
        by_mod[m] = by_mod.get(m, 0) + 1
    return {
        "ok": True,
        "source": "a6",
        "fetched_at": payload.get("synced_at") or payload.get("fetched_at"),
        "models_n": payload.get("n") or payload.get("models_n"),
        "catalog_n": len(rows),
        "by_modality": by_mod,
        "ready_n": sum(1 for r in rows if r.get("ready")),
        "polza": polza,
    }
