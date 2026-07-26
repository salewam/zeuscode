from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, hash_api_key, hash_password, verify_password
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import ApiKey, User
from app.routers.keys import public_v1_base_url

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    balance_rub: float
    api_key: str | None = None
    base_url: str | None = None
    key_created: bool = False


async def _create_default_key(db: AsyncSession, user: User) -> tuple[ApiKey, str]:
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
    return key, raw


@router.post("/register", response_model=TokenOut)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    exists = await db.execute(select(User).where(User.email == body.email.lower()))
    if exists.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        balance_usd=settings.TRIAL_RUB,  # column stores RUB
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    _, raw = await _create_default_key(db, user)
    token = create_access_token(user.id, user.email)
    return TokenOut(
        access_token=token,
        balance_rub=user.balance_usd,
        api_key=raw,
        base_url=public_v1_base_url(),
        key_created=True,
    )


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    try:
        from app.kie_credits import sync_user_balance_from_kie

        await sync_user_balance_from_kie(user)
        await db.commit()
        await db.refresh(user)
    except Exception:  # noqa: BLE001
        pass
    token = create_access_token(user.id, user.email)
    return TokenOut(access_token=token, balance_rub=round(float(user.balance_usd or 0), 4))


@router.get("/me")
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    bal_meta: dict = {"credits": None, "synced": False}
    try:
        from app.kie_credits import sync_user_balance_from_kie

        bal_meta = await sync_user_balance_from_kie(user)
        await db.commit()
        await db.refresh(user)
    except Exception:  # noqa: BLE001
        pass
    from app.fusion import DEFAULT_PRODUCT_MODE, normalize_product_mode, parse_fusion_models_json
    from app.fusion.metrics import normalize_effort

    credits = bal_meta.get("credits", bal_meta.get("kie_credits"))
    synced = bool(bal_meta.get("synced") or bal_meta.get("kie_synced"))
    return {
        "id": user.id,
        "email": user.email,
        "balance_rub": round(float(user.balance_usd or 0), 4),
        "model_family": getattr(user, "model_family", None) or "",
        "fusion_pref": normalize_product_mode(getattr(user, "fusion_pref", None))
        or DEFAULT_PRODUCT_MODE,
        "fusion_models": parse_fusion_models_json(getattr(user, "fusion_models", None)),
        "fusion_effort": normalize_effort(getattr(user, "fusion_effort", None)),
        "fusion_kill_switch": bool(getattr(user, "fusion_kill_switch", 0)),
        "credits": credits,
        "synced": synced,
    }
