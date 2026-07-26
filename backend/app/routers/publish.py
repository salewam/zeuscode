"""Publish free public site links: POST /api/publish → https://zeuscode.ru/go/<slug>/."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_api_key
from app.config import get_settings
from app.db import get_db
from app.fusion.publish_gate import PublishRegressionError, gate_publish_html
from app.models import ApiKey, User
from app.publish import publish_html, public_base_url, site_dir

router = APIRouter(tags=["publish"])


class PublishIn(BaseModel):
    html: str = Field(min_length=20)
    title: str | None = None
    slug: str | None = None


class PublishOut(BaseModel):
    ok: bool = True
    url: str
    slug: str
    title: str | None = None


async def _optional_api_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    raw = authorization.split(" ", 1)[1].strip()
    if not (raw.startswith("zeus_") or raw.startswith("osk_")):
        return None
    digest = hash_api_key(raw)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.revoked == 0)
    )
    key = result.scalar_one_or_none()
    if not key:
        return None
    return await db.get(User, key.user_id)


@router.post("/api/publish", response_model=PublishOut)
@router.post("/v1/sites/publish", response_model=PublishOut)
async def publish_site(
    body: PublishIn,
    user: User | None = Depends(_optional_api_user),
) -> dict[str, Any]:
    # FR26 publish regression gate — blocks silent badge/HTML breakage
    settings = get_settings()
    try:
        html = gate_publish_html(
            body.html,
            enabled=bool(getattr(settings, "FUSION_PUBLISH_REGRESSION_GATE", True)),
        )
    except PublishRegressionError as exc:
        raise HTTPException(400, f"publish regression: {exc}") from exc
    meta = {"user_id": user.id} if user else {}
    info = publish_html(html, title=body.title, slug=body.slug, meta=meta)
    return {
        "ok": True,
        "url": info["url"],
        "slug": info["slug"],
        "title": info.get("title"),
    }


@router.get("/api/publish/info")
async def publish_info() -> dict[str, Any]:
    return {
        "ok": True,
        "base": f"{public_base_url()}/go/",
        "badge": "Сделано на ZeusCode",
        "hint": "POST /api/publish {html, title?} → {url}",
    }


@router.get("/go/{slug}")
@router.get("/go/{slug}/")
async def serve_site_index(slug: str):
    d = site_dir(slug)
    if not d:
        raise HTTPException(404, "Site not found")
    return FileResponse(d / "index.html", media_type="text/html; charset=utf-8")


@router.get("/go/{slug}/{path:path}")
async def serve_site_asset(slug: str, path: str):
    d = site_dir(slug)
    if not d:
        raise HTTPException(404, "Site not found")
    clean = path.replace("\\", "/").lstrip("/")
    if ".." in clean.split("/"):
        raise HTTPException(400, "bad path")
    target = (d / clean).resolve()
    if not str(target).startswith(str(d.resolve())):
        raise HTTPException(400, "bad path")
    if not target.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(target)
