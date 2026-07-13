"""Token pricing + markup for ZeusCode (user-facing currency: RUB).

User price preference:
1) model.input_rub / output_rub (synced from Polza.ai when available)
2) else upstream USD × MARKUP × USD_RUB
"""

from __future__ import annotations

from app.catalog import get_model, upstream_prices
from app.config import get_settings


def price_for(model: str) -> tuple[float, float]:
    prices = upstream_prices()
    if model in prices:
        return prices[model]
    for key, val in prices.items():
        if key in model or model in key:
            return val
    return (0.5, 1.5)


def rub_price_for(model: str) -> tuple[float, float] | None:
    meta = get_model(model) or {}
    if meta.get("input_rub") is None:
        return None
    return float(meta["input_rub"]), float(meta.get("output_rub") or 0)


def estimate_upstream_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = price_for(model)
    return (prompt_tokens / 1_000_000) * pin + (completion_tokens / 1_000_000) * pout


def usd_to_rub(amount_usd: float, rate: float | None = None) -> float:
    settings = get_settings()
    r = rate if rate is not None else settings.USD_RUB
    return amount_usd * r


def user_price(upstream_usd: float, markup: float | None = None) -> float:
    """Fallback: user charge in RUB = upstream USD × markup × USD_RUB."""
    settings = get_settings()
    m = markup if markup is not None else settings.MARKUP
    return usd_to_rub(upstream_usd * m)


def estimate_user_rub(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """User charge in RUB for token usage (Polza-aligned when possible)."""
    rub = rub_price_for(model)
    if rub is not None:
        pin, pout = rub
        return (prompt_tokens / 1_000_000) * pin + (completion_tokens / 1_000_000) * pout
    return user_price(estimate_upstream_usd(model, prompt_tokens, completion_tokens))
