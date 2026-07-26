import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.fusion import (
    DEFAULT_PRODUCT_MODE,
    PRODUCT_MODES,
    normalize_product_mode,
    parse_fusion_models_json,
)
from app.fusion.metrics import normalize_effort
from app.models import UsageLog, User

router = APIRouter(prefix="/me", tags=["me"])


class FusionPrefIn(BaseModel):
    mode: str = Field(description="simple | power | custom")
    models: list[str] | None = None
    effort: str | None = Field(default=None, description="low | normal | high | max")
    kill_switch: bool | None = Field(default=None, description="Force FAST Path when true")


@router.get("/fusion")
async def get_fusion_pref(user: User = Depends(get_current_user)):
    mode = normalize_product_mode(getattr(user, "fusion_pref", None)) or DEFAULT_PRODUCT_MODE
    models = parse_fusion_models_json(getattr(user, "fusion_models", None))
    effort = normalize_effort(getattr(user, "fusion_effort", None))
    kill_switch = bool(getattr(user, "fusion_kill_switch", 0))
    return {
        "mode": mode,
        "models": models,
        "effort": effort,
        "kill_switch": kill_switch,
        "modes": [
            {
                "id": "simple",
                "title": "Простой",
                "hint": "deepseek-v4-flash · gemini-3-pro · haiku-4-5 (умный 1↔3)",
            },
            {
                "id": "power",
                "title": "Мощный",
                "hint": "opus-4-8 · deepseek-v4-pro · gemini-3.1-pro (умный 1↔3)",
            },
            {
                "id": "custom",
                "title": "Свой набор",
                "hint": "Выбери до 3 моделей; роутинг 1↔3 внутри набора",
            },
        ],
        "effort_levels": ["low", "normal", "high", "max"],
    }


@router.put("/fusion")
async def put_fusion_pref(
    body: FusionPrefIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mode = normalize_product_mode(body.mode)
    if mode not in PRODUCT_MODES:
        raise HTTPException(400, "mode: simple | power | custom")
    models = parse_fusion_models_json(json.dumps(body.models or []))
    if mode == "custom" and not models:
        raise HTTPException(400, "custom: укажи 1–3 модели в models")
    user.fusion_pref = mode
    user.fusion_models = json.dumps(models, ensure_ascii=False) if models else ""
    if body.effort is not None:
        user.fusion_effort = normalize_effort(body.effort)
    if body.kill_switch is not None:
        user.fusion_kill_switch = 1 if body.kill_switch else 0
    await db.commit()
    await db.refresh(user)
    try:
        from app.usage_analytics import log_product_event

        await log_product_event(
            db,
            event="pref_change",
            user_id=user.id,
            source="cabinet",
            status_code=200,
            meta={
                "mode": mode,
                "models": models,
                "effort": normalize_effort(getattr(user, "fusion_effort", None)),
                "kill_switch": bool(getattr(user, "fusion_kill_switch", 0)),
            },
        )
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": True,
        "mode": mode,
        "models": models,
        "effort": normalize_effort(getattr(user, "fusion_effort", None)),
        "kill_switch": bool(getattr(user, "fusion_kill_switch", 0)),
    }


@router.get("/usage")
async def usage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    result = await db.execute(
        select(UsageLog)
        .where(UsageLog.user_id == user.id)
        .order_by(UsageLog.id.desc())
        .limit(min(limit, 200))
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "model": r.model,
            "mode": r.mode,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "cost_user_rub": round(r.cost_user_usd, 4),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
