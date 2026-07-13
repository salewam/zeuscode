from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import upstream
from app.catalog import get_model
from app.config import get_settings
from app.cost import estimate_upstream_usd, estimate_user_rub
from app.db import get_db
from app.deps import get_user_by_api_key
from app.model_policy import assert_model_allowed
from app.models import ApiKey, UsageLog, User

router = APIRouter(tags=["chat"])
settings = get_settings()


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatCompletionIn(BaseModel):
    model: str = Field(default="gemini-2.5-flash")
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionIn,
    auth: tuple[User, ApiKey] = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    user, api_key = auth
    if user.balance_usd <= 0:
        raise HTTPException(402, "Insufficient balance")

    messages = [m.model_dump() for m in body.messages]
    model = body.model or settings.DEFAULT_MODEL
    assert_model_allowed(user, model)

    try:
        studio_ids = {
            "ultra-mode",
            "ultra",
            "onestack-ultra",
            "studio-light",
            "studio-standard",
            "studio-ultra",
            "studio-premium",
        }
        if model in studio_ids:
            from app.orchestrate import normalize_mode, run_studio

            user_text = ""
            history = []
            for m in messages:
                if m.get("role") in ("user", "assistant") and m.get("content"):
                    history.append({"role": m["role"], "content": m["content"]})
                if m.get("role") == "user":
                    c = m.get("content", "")
                    user_text = c if isinstance(c, str) else str(c)
            hist = history[:-1] if history and history[-1]["role"] == "user" else history
            data = await run_studio(
                user_text=user_text or "Сделай минимальный рабочий пример.",
                intent="feature",
                mode=normalize_mode(model),
                history=hist,
            )
            mode = (data.get("onestack") or {}).get("mode") or "ultra"
            bill_model = data.get("_bill_model") or settings.ULTRA_MODEL
        else:
            if body.stream:
                raise HTTPException(400, "stream=true not supported yet")
            meta = get_model(model)
            if meta and not meta.get("ready"):
                raise HTTPException(
                    400,
                    f"Модель {model} в каталоге, но ещё не подключена. Выбери Gemini / Claude / studio-ultra.",
                )
            data = await upstream.chat_completions(model=model, messages=messages, stream=False)
            mode = "solo"
            bill_model = model if get_model(model) else settings.DEFAULT_MODEL
    except upstream.UpstreamError as e:
        raise HTTPException(e.status_code, str(e)) from e

    usage = data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)

    # Multi-agent: sum per-agent if present
    onestack = data.get("onestack") or {}
    agents = onestack.get("agents") or []
    if agents:
        upstream_cost = 0.0
        charged = 0.0
        for a in agents:
            mid = a.get("model") or bill_model
            pt = int(a.get("prompt_tokens") or 0)
            ct = int(a.get("completion_tokens") or 0)
            upstream_cost += estimate_upstream_usd(mid, pt, ct)
            charged += estimate_user_rub(mid, pt, ct)
        u_p, u_c = prompt, completion
        a_p = sum(int(a.get("prompt_tokens") or 0) for a in agents)
        a_c = sum(int(a.get("completion_tokens") or 0) for a in agents)
        if u_p + u_c > a_p + a_c:
            upstream_cost += estimate_upstream_usd(
                bill_model, max(u_p - a_p, 0), max(u_c - a_c, 0)
            )
            charged += estimate_user_rub(bill_model, max(u_p - a_p, 0), max(u_c - a_c, 0))
    else:
        upstream_cost = estimate_upstream_usd(bill_model, prompt, completion)
        charged = estimate_user_rub(bill_model, prompt, completion)

    if user.balance_usd < charged:
        raise HTTPException(402, f"Недостаточно средств (~{charged:.2f} ₽)")

    budget = float(api_key.budget_rub or 0)
    spent = float(api_key.spent_rub or 0)
    if budget > 0 and spent + charged > budget:
        left = max(0.0, budget - spent)
        raise HTTPException(
            402,
            f"Лимит ключа исчерпан (осталось ~{left:.2f} ₽ из {budget:.0f} ₽). "
            "Подними бюджет ключа в кабинете или создай новый.",
        )

    user.balance_usd = round(user.balance_usd - charged, 8)
    api_key.spent_rub = round(spent + charged, 8)
    log = UsageLog(
        user_id=user.id,
        api_key_id=api_key.id,
        model=data.get("model") or model,
        mode=mode,
        prompt_tokens=prompt,
        completion_tokens=completion,
        cost_upstream_usd=upstream_cost,
        cost_user_usd=charged,
        meta=str((data.get("onestack") or {})),
    )
    db.add(log)
    await db.commit()

    from app.routers.billing import alert_payload, month_spent_rub

    month_spent = await month_spent_rub(db, user.id)
    alerts = alert_payload(user, month_spent)

    data["onestack_billing"] = {
        "currency": "RUB",
        "charged_rub": round(charged, 4),
        "markup": settings.MARKUP,
        "balance_left_rub": round(user.balance_usd, 4),
        "key_spent_rub": round(float(api_key.spent_rub or 0), 4),
        "key_budget_rub": round(budget, 2),
        "alerts": {
            "low_balance": alerts["low_balance_triggered"],
            "monthly_budget": alerts["monthly_budget_triggered"],
            "monthly_budget_warning": alerts["monthly_budget_warning"],
        },
    }
    return data
