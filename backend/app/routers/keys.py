from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_api_key
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import ApiKey, User

router = APIRouter(prefix="/keys", tags=["keys"])


def public_v1_base_url() -> str:
    return get_settings().APP_PUBLIC_URL.strip().rstrip("/") + "/v1"


# Back-compat for imports; prefer public_v1_base_url() at runtime
BASE_URL_HINT = public_v1_base_url()


class KeyCreateIn(BaseModel):
    name: str = Field(default="default", max_length=120)
    budget_rub: float = Field(default=0, ge=0, le=1_000_000)


class KeyPatchIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    budget_rub: float | None = Field(default=None, ge=0, le=1_000_000)


class KeyOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    budget_rub: float
    spent_rub: float
    raw_key: str | None = None
    created_at: str
    base_url: str = "http://127.0.0.1:8080/v1"


def _key_dict(k: ApiKey, raw: str | None = None) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "key_prefix": k.key_prefix,
        "budget_rub": round(float(k.budget_rub or 0), 2),
        "spent_rub": round(float(k.spent_rub or 0), 4),
        "created_at": k.created_at.isoformat() if k.created_at else None,
        "base_url": public_v1_base_url(),
        "raw_key": raw,
    }


@router.get("")
async def list_keys(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked == 0).order_by(ApiKey.id.desc())
    )
    keys = result.scalars().all()
    return [_key_dict(k) for k in keys]


@router.post("/ensure")
async def ensure_key(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Create a default API key if the user has none. Raw key returned only when newly created."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked == 0).order_by(ApiKey.id.desc())
    )
    existing = result.scalars().first()
    if existing:
        return {**_key_dict(existing), "created": False, "raw_key": None}
    raw = ApiKey.generate_raw()
    key = ApiKey(
        user_id=user.id,
        name="default",
        key_prefix=raw[:12],
        key_hash=hash_api_key(raw),
        budget_rub=0.0,
        spent_rub=0.0,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    out = _key_dict(key, raw=raw)
    out["created"] = True
    out["warning"] = (
        "Ключ создан автоматически. Скопируй его сейчас — полный ключ больше не покажем."
    )
    return out


@router.post("")
async def create_key(
    body: KeyCreateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raw = ApiKey.generate_raw()
    key = ApiKey(
        user_id=user.id,
        name=body.name.strip() or "default",
        key_prefix=raw[:12],
        key_hash=hash_api_key(raw),
        budget_rub=float(body.budget_rub or 0),
        spent_rub=0.0,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    out = _key_dict(key, raw=raw)
    out["warning"] = (
        "ВАЖНО: ключ ZeusCode не работает с официальным OpenAI напрямую. "
        f"В любом OpenAI-compatible клиенте укажи Base URL = {public_v1_base_url()} и этот ключ."
    )
    return out


@router.patch("/{key_id}")
async def patch_key(
    key_id: int,
    body: KeyPatchIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    key = await db.get(ApiKey, key_id)
    if not key or key.user_id != user.id or key.revoked:
        raise HTTPException(404, "Key not found")
    if body.name is not None:
        key.name = body.name.strip() or key.name
    if body.budget_rub is not None:
        key.budget_rub = float(body.budget_rub)
    await db.commit()
    await db.refresh(key)
    return _key_dict(key)


@router.delete("/{key_id}")
async def revoke_key(
    key_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    key = await db.get(ApiKey, key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(404, "Key not found")
    key.revoked = 1
    await db.commit()
    return {"ok": True}
