"""Telegram Mini App API — fusion picker + onboarding learn track."""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.fusion import (
    DEFAULT_PRODUCT_MODE,
    PRODUCT_MODES,
    is_fusion_model,
    normalize_product_mode,
    parse_fusion_models_json,
)
from app.catalog import public_catalog
from app.model_policy import filter_catalog_for_user
from app.routers.keys import public_v1_base_url
from app.telegram_accounts import (
    active_key_prefix,
    ensure_telegram_user,
    rotate_telegram_key,
)
from app.telegram_webapp import validate_webapp_init_data
from app.usage_analytics import log_user_action

router = APIRouter(prefix="/tg", tags=["telegram-miniapp"])
settings = get_settings()


def normalize_effort(raw: str | None) -> str:
    try:
        from app.fusion.metrics import normalize_effort as _ne

        return _ne(raw)
    except Exception:  # noqa: BLE001
        v = (str(raw or "normal")).strip().lower()
        return v if v in ("low", "normal", "high", "max") else "normal"


class FusionSaveIn(BaseModel):
    mode: str = Field(description="simple | power | custom")
    models: list[str] | None = None
    effort: str | None = Field(default=None, description="low | normal | high | max")
    kill_switch: bool | None = Field(default=None, description="Force FAST Path when true")


class OnboardingIn(BaseModel):
    done: bool = True
    track: str | None = Field(default=None, description="cursor | studio")


class AdvisorIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict[str, str]] | None = None


class ClientEventIn(BaseModel):
    """UI action from Mini App (tabs, copy, steps, chips)."""

    event: str = Field(min_length=1, max_length=40)
    meta: dict[str, Any] | None = None
    prompt_preview: str | None = Field(default=None, max_length=500)


def _init_from_header(authorization: str | None, x_tg_init_data: str | None) -> str:
    if x_tg_init_data and x_tg_init_data.strip():
        return x_tg_init_data.strip()
    if authorization and authorization.lower().startswith("tma "):
        return authorization[4:].strip()
    raise HTTPException(401, "Нужен заголовок X-Tg-Init-Data (Telegram Mini App)")


async def tg_user_dep(
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_tg_init_data: str | None = Header(default=None, alias="X-Tg-Init-Data"),
):
    init_data = _init_from_header(authorization, x_tg_init_data)
    parsed = validate_webapp_init_data(init_data, settings.TELEGRAM_BOT_TOKEN)
    tg = parsed["user"]
    tg_id = int(tg["id"])
    username = tg.get("username")
    first_name = tg.get("first_name")
    user, _raw, _new = await ensure_telegram_user(
        db, tg_id, username=username, first_name=first_name
    )
    await db.commit()
    await db.refresh(user)
    return user, tg


def _coding_models(user) -> list[dict[str, Any]]:
    rows = filter_catalog_for_user(user, public_catalog())
    out = []
    for m in rows:
        mid = str(m.get("id") or "")
        if not m.get("ready"):
            continue
        if (m.get("modality") or "chat") != "chat":
            continue
        if m.get("family") in ("studio", "ultra", "fusion"):
            continue
        if mid.startswith("studio-") or mid == "ultra-mode" or is_fusion_model(mid):
            continue
        out.append(
            {
                "id": mid,
                "title": m.get("title") or mid,
                "provider": m.get("provider") or "",
                "pricing": m.get("pricing") or {},
            }
        )
    return out


@router.get("/me")
async def tg_me(auth=Depends(tg_user_dep), db: AsyncSession = Depends(get_db)):
    user, tg = auth
    mode = normalize_product_mode(getattr(user, "fusion_pref", None)) or DEFAULT_PRODUCT_MODE
    models = parse_fusion_models_json(getattr(user, "fusion_models", None))
    prefix = await active_key_prefix(db, user)
    public = settings.APP_PUBLIC_URL.rstrip("/")
    await log_user_action(
        db,
        event="miniapp_open",
        user=user,
        source="tg_miniapp",
        meta={
            "onboarding_done": bool(getattr(user, "onboarding_done", 0)),
            "key_prefix": prefix or "",
            "mode": mode,
        },
    )
    return {
        "telegram": {
            "id": tg.get("id"),
            "username": tg.get("username"),
            "first_name": tg.get("first_name"),
        },
        "fusion": {
            "mode": mode,
            "models": models,
            "effort": normalize_effort(getattr(user, "fusion_effort", None)),
            "kill_switch": bool(getattr(user, "fusion_kill_switch", 0)),
            "modes": [
                {
                    "id": "simple",
                    "title": "Пользовательский",
                    "hint": "Три лёгкие нейронки · сами переключаются",
                },
                {
                    "id": "power",
                    "title": "Продвинутый",
                    "hint": "Три сильные нейронки · сами переключаются",
                },
                {
                    "id": "custom",
                    "title": "Набор",
                    "hint": "Собери до трёх нейронок сам",
                },
            ],
            "effort_levels": ["low", "normal", "high", "max"],
        },
        "catalog": _coding_models(user),
        "balance_rub": round(float(user.balance_usd or 0), 2),
        # Telegram onboarding: без пробных токенов
        "trial_rub": 0.0,
        "base_url": public_v1_base_url(),
        "studio_url": f"{public}/app",
        "key_prefix": prefix,
        "onboarding_done": bool(getattr(user, "onboarding_done", 0)),
        "model_hint": "zeuscode",
        "telegram_id": int(user.telegram_id or 0) or None,
        "telegram_username": (getattr(user, "telegram_username", None) or "") or None,
        "telegram_first_name": (getattr(user, "telegram_first_name", None) or "") or None,
    }


@router.put("/fusion")
async def tg_save_fusion(
    body: FusionSaveIn,
    auth=Depends(tg_user_dep),
    db: AsyncSession = Depends(get_db),
):
    user, _tg = auth
    mode = normalize_product_mode(body.mode)
    if mode not in PRODUCT_MODES:
        raise HTTPException(400, "mode: simple | power | custom")
    models = parse_fusion_models_json(json.dumps(body.models or []))
    allowed = {m["id"] for m in _coding_models(user)}
    models = [m for m in models if m in allowed][:3]
    if mode == "custom" and not models:
        raise HTTPException(400, "custom: выбери 1–3 модели")
    user.fusion_pref = mode
    user.fusion_models = json.dumps(models, ensure_ascii=False) if models else ""
    if body.effort is not None:
        user.fusion_effort = normalize_effort(body.effort)
    if body.kill_switch is not None:
        user.fusion_kill_switch = 1 if body.kill_switch else 0
    await db.commit()
    await db.refresh(user)
    await log_user_action(
        db,
        event="pref_change",
        user=user,
        source="tg_miniapp",
        meta={
            "mode": mode,
            "models": models,
            "effort": normalize_effort(getattr(user, "fusion_effort", None)),
            "kill_switch": bool(getattr(user, "fusion_kill_switch", 0)),
        },
    )
    return {
        "ok": True,
        "mode": mode,
        "models": models,
        "effort": normalize_effort(getattr(user, "fusion_effort", None)),
        "kill_switch": bool(getattr(user, "fusion_kill_switch", 0)),
    }


@router.post("/onboarding")
async def tg_onboarding(
    body: OnboardingIn,
    auth=Depends(tg_user_dep),
    db: AsyncSession = Depends(get_db),
):
    user, _tg = auth
    user.onboarding_done = 1 if body.done else 0
    await db.commit()
    track = (body.track or "").strip() or None
    await log_user_action(
        db,
        event="onboarding_done" if body.done else "onboarding_reset",
        user=user,
        source="tg_miniapp",
        meta={"track": track, "done": bool(body.done)},
    )
    return {
        "ok": True,
        "onboarding_done": bool(user.onboarding_done),
        "track": track,
    }


@router.post("/key/rotate")
async def tg_rotate_key(
    auth=Depends(tg_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Issue a fresh API key (old ones revoked). Raw shown once."""
    user, _tg = auth
    raw, prefix = await rotate_telegram_key(db, user)
    await log_user_action(
        db,
        event="key_rotate",
        user=user,
        source="tg_miniapp",
        meta={"key_prefix": prefix},
    )
    return {
        "ok": True,
        "api_key": raw,
        "key_prefix": prefix,
        "base_url": public_v1_base_url(),
        "model_hint": "zeuscode",
        "warning": "Скопируй ключ сейчас — повторно полный секрет не покажем.",
    }


@router.post("/advisor")
async def tg_advisor(
    body: AdvisorIn,
    auth=Depends(tg_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Friendly DeepSeek advisor — режимы, нейронки, веб-исследование."""
    from app.advisor import ask_advisor

    user, tg = auth
    name = (tg.get("first_name") or tg.get("username") or "").strip() or None
    mode = normalize_product_mode(getattr(user, "fusion_pref", None)) or DEFAULT_PRODUCT_MODE
    t0 = time.perf_counter()
    result = await ask_advisor(
        body.message,
        name=name,
        mode=mode,
        balance_rub=round(float(user.balance_usd or 0), 2),
        history=body.history,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    await log_user_action(
        db,
        event="advisor_ask",
        user=user,
        source="tg_miniapp",
        prompt_preview=(body.message or "")[:500],
        latency_ms=latency_ms,
        meta={
            "researched": bool(result.get("researched")),
            "research_query": result.get("research_query"),
            "answer_preview": str(result.get("answer") or "")[:280],
        },
    )
    return {
        "ok": True,
        "answer": result.get("answer") or "",
        "researched": bool(result.get("researched")),
        "research_query": result.get("research_query"),
    }


_ALLOWED_UI_EVENTS = {
    "miniapp_view",
    "ui_copy",
    "ui_platform",
    "ui_learn_step",
    "ui_chip",
    "ui_rekey",
    "ui_save_fusion",
    "ui_open_url",
    "ui_main_button",
}


@router.post("/events")
async def tg_client_event(
    body: ClientEventIn,
    auth=Depends(tg_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Log Mini App UI actions (tabs, copy, onboarding steps, chips)."""
    user, _tg = auth
    event = (body.event or "").strip().lower()[:40]
    if event not in _ALLOWED_UI_EVENTS:
        # still accept custom ui_* for forward-compat, reject junk
        if not event.startswith("ui_") and event != "miniapp_view":
            raise HTTPException(400, "unknown event")
    await log_user_action(
        db,
        event=event or "ui_event",
        user=user,
        source="tg_miniapp",
        prompt_preview=(body.prompt_preview or "")[:500],
        meta=body.meta or {},
    )
    return {"ok": True}
