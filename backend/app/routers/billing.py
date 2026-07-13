from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.catalog import MODELS
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import ApiKey, Project, UsageLog, User

router = APIRouter(prefix="/billing", tags=["billing"])
settings = get_settings()


def _public_v1_base_url() -> str:
    return settings.APP_PUBLIC_URL.strip().rstrip("/") + "/v1"


class TopupIn(BaseModel):
    amount_rub: float = Field(ge=100, le=100_000, default=500)
    method: str = Field(default="card")  # card | cryptobot


class AlertSettingsIn(BaseModel):
    low_balance_alert: bool | None = None
    low_balance_threshold_rub: float | None = Field(default=None, ge=0, le=1_000_000)
    monthly_budget_rub: float | None = Field(default=None, ge=0, le=10_000_000)


def _month_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def month_spent_rub(db: AsyncSession, user_id: int) -> float:
    result = await db.execute(
        select(func.coalesce(func.sum(UsageLog.cost_user_usd), 0.0)).where(
            UsageLog.user_id == user_id,
            UsageLog.created_at >= _month_start_utc(),
        )
    )
    return float(result.scalar_one())


def alert_payload(user: User, month_spent: float) -> dict:
    threshold = float(user.low_balance_threshold_rub or 50)
    alert_on = bool(user.low_balance_alert)
    balance = float(user.balance_usd or 0)
    monthly = float(user.monthly_budget_rub or 0)
    low = alert_on and balance <= threshold
    month_over = monthly > 0 and month_spent >= monthly
    month_warn = monthly > 0 and month_spent >= monthly * 0.8
    return {
        "low_balance_alert": alert_on,
        "low_balance_threshold_rub": round(threshold, 2),
        "monthly_budget_rub": round(monthly, 2),
        "month_spent_rub": round(month_spent, 4),
        "low_balance_triggered": low,
        "monthly_budget_triggered": month_over,
        "monthly_budget_warning": month_warn and not month_over,
        "email_note": (
            "Уведомление на email появится после подключения почты. "
            "Сейчас алерт виден в кабинете."
        ),
    }


@router.get("/plans")
async def plans():
    return {
        "currency": "RUB",
        "markup": settings.MARKUP,
        "trial_rub": settings.TRIAL_RUB,
        "packages": [
            {"id": "starter", "amount_rub": 500, "label": "Старт"},
            {"id": "dev", "amount_rub": 2000, "label": "Для разработки"},
            {"id": "team", "amount_rub": 5000, "label": "Для команды"},
        ],
        "methods": [
            {"id": "card", "title": "Карта РФ", "status": "soon"},
            {"id": "cryptobot", "title": "USDT · CryptoBot", "status": "soon"},
        ],
    }


@router.post("/topup")
async def topup_intent(body: TopupIn, user: User = Depends(get_current_user)):
    """MVP: инструкции пополнения. Реальная оплата — следующим этапом."""
    return {
        "ok": True,
        "user_id": user.id,
        "amount_rub": body.amount_rub,
        "method": body.method,
        "status": "manual",
        "currency": "RUB",
        "instructions": (
            "Пока пополнение вручную. Напиши в Telegram саппорт и укажи ID аккаунта. "
            "Скоро: карта РФ и USDT через CryptoBot."
        ),
        "telegram": "@zeuscode_support",
    }


@router.get("/settings")
async def get_settings_alerts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    spent = await month_spent_rub(db, user.id)
    return alert_payload(user, spent)


@router.patch("/settings")
async def patch_settings_alerts(
    body: AlertSettingsIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.low_balance_alert is not None:
        user.low_balance_alert = 1 if body.low_balance_alert else 0
    if body.low_balance_threshold_rub is not None:
        user.low_balance_threshold_rub = float(body.low_balance_threshold_rub)
    if body.monthly_budget_rub is not None:
        user.monthly_budget_rub = float(body.monthly_budget_rub)
    await db.commit()
    await db.refresh(user)
    spent = await month_spent_rub(db, user.id)
    return alert_payload(user, spent)


@router.get("/summary")
async def billing_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    spent = await db.execute(
        select(func.coalesce(func.sum(UsageLog.cost_user_usd), 0.0)).where(
            UsageLog.user_id == user.id
        )
    )
    calls = await db.execute(
        select(func.count()).select_from(UsageLog).where(UsageLog.user_id == user.id)
    )
    keys = await db.execute(
        select(func.count())
        .select_from(ApiKey)
        .where(ApiKey.user_id == user.id, ApiKey.revoked == 0)
    )
    projects = await db.execute(
        select(func.count()).select_from(Project).where(Project.user_id == user.id)
    )
    month_spent = await month_spent_rub(db, user.id)
    alerts = alert_payload(user, month_spent)
    return {
        "currency": "RUB",
        "balance_rub": round(user.balance_usd, 4),
        "spent_rub": round(float(spent.scalar_one()), 4),
        "requests": int(calls.scalar_one()),
        "api_keys": int(keys.scalar_one()),
        "projects": int(projects.scalar_one()),
        "markup": settings.MARKUP,
        "base_url": _public_v1_base_url(),
        "models_ready": sum(1 for m in MODELS if m.get("ready")),
        "models_total": len(MODELS),
        "alerts": alerts,
    }


@router.get("/dashboard")
async def billing_dashboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Главная: лимиты, проекты, модели, история, график трат."""
    summary = await billing_summary(user=user, db=db)

    projects_q = await db.execute(
        select(Project)
        .where(Project.user_id == user.id)
        .options(selectinload(Project.chats))
        .order_by(Project.updated_at.desc())
        .limit(8)
    )
    projects = [
        {
            "id": p.id,
            "title": p.title,
            "chats_count": len(p.chats or []),
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in projects_q.scalars().all()
    ]

    models_q = await db.execute(
        select(
            UsageLog.model,
            func.count().label("calls"),
            func.coalesce(func.sum(UsageLog.cost_user_usd), 0.0).label("spent"),
        )
        .where(UsageLog.user_id == user.id)
        .group_by(UsageLog.model)
        .order_by(func.sum(UsageLog.cost_user_usd).desc())
        .limit(8)
    )
    models_used = [
        {
            "model": row.model,
            "calls": int(row.calls),
            "spent_rub": round(float(row.spent), 4),
        }
        for row in models_q.all()
    ]

    recent_q = await db.execute(
        select(UsageLog)
        .where(UsageLog.user_id == user.id)
        .order_by(UsageLog.id.desc())
        .limit(8)
    )
    recent = [
        {
            "id": r.id,
            "model": r.model,
            "mode": r.mode,
            "cost_user_rub": round(r.cost_user_usd, 4),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in recent_q.scalars().all()
    ]

    now = datetime.now(timezone.utc)
    days = []
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).date()
        days.append(day.isoformat())

    logs_q = await db.execute(
        select(UsageLog.created_at, UsageLog.cost_user_usd).where(
            UsageLog.user_id == user.id,
            UsageLog.created_at >= now - timedelta(days=7),
        )
    )
    by_day: dict[str, float] = {d: 0.0 for d in days}
    for created, cost in logs_q.all():
        if not created:
            continue
        key = (
            created.astimezone(timezone.utc).date().isoformat()
            if created.tzinfo
            else created.date().isoformat()
        )
        if key in by_day:
            by_day[key] += float(cost or 0)

    spend_chart = [{"day": d, "spent_rub": round(by_day[d], 4)} for d in days]
    spent_today = by_day.get(now.date().isoformat(), 0.0)
    daily_limit = max(settings.TRIAL_RUB, 300.0)
    alerts = summary["alerts"]
    monthly = float(alerts["monthly_budget_rub"] or 0)

    return {
        **summary,
        "projects_active": projects,
        "models_used": models_used,
        "recent": recent,
        "spend_chart": spend_chart,
        "limits": {
            "balance_rub": round(user.balance_usd, 4),
            "spent_rub": summary["spent_rub"],
            "spent_today_rub": round(spent_today, 4),
            "daily_soft_rub": daily_limit,
            "month_spent_rub": alerts["month_spent_rub"],
            "monthly_budget_rub": monthly,
            "requests": summary["requests"],
            "api_keys": summary["api_keys"],
        },
    }
