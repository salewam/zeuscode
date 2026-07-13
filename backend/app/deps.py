from fastapi import Cookie, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import decode_access_token, hash_api_key
from app.db import get_db
from app.models import ApiKey, User


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(401, "Invalid token")
    user = await db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "User not found")
    return user


async def get_current_user_preview(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
    zc_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Auth for iframe preview: Bearer, ?token=, or zc_token cookie (subresources)."""
    raw = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization.split(" ", 1)[1].strip()
    elif token:
        raw = token.strip()
    elif zc_token:
        raw = zc_token.strip()
    if not raw:
        raise HTTPException(401, "Missing auth for preview")
    payload = decode_access_token(raw)
    if not payload or "sub" not in payload:
        raise HTTPException(401, "Invalid token")
    user = await db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "User not found")
    return user


async def get_user_by_api_key(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, ApiKey]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing API key (Authorization: Bearer …)")
    raw = authorization.split(" ", 1)[1].strip()
    # zeus_/osk_ product keys, or raw hex seat keys (32–64 chars)
    ok_fmt = (
        raw.startswith("zeus_")
        or raw.startswith("osk_")
        or (len(raw) >= 32 and all(c in "0123456789abcdefABCDEF" for c in raw))
    )
    if not ok_fmt:
        raise HTTPException(401, "Invalid API key format")
    digest = hash_api_key(raw)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.revoked == 0)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(401, "Invalid or revoked API key")
    user = await db.get(User, key.user_id)
    if not user:
        raise HTTPException(401, "User not found")
    return user, key
