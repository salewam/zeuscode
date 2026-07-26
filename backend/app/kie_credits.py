"""Live upstream credits — source of truth for Zeus balance display.

`GET /api/v1/chat/credit` returns numeric credits in `data`.
1 credit ≡ 1 ₽ on the Zeus balance.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger("zeus.credits")


async def fetch_kie_credits(timeout: float = 12.0) -> float | None:
    """Return live upstream credit balance or None if unreachable."""
    settings = get_settings()
    key = settings.upstream_api_key
    base = settings.upstream_base_url or ""
    if not key or not base:
        return None
    url = f"{base.rstrip('/')}/api/v1/chat/credit"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {key}"})
            if r.status_code != 200:
                log.warning("credit HTTP %s: %s", r.status_code, r.text[:200])
                return None
            payload: dict[str, Any] = r.json() if r.content else {}
            data = payload.get("data")
            if isinstance(data, (int, float)):
                return float(data)
            if isinstance(data, dict) and "credit" in data:
                return float(data["credit"])
            log.warning("credit unexpected payload: %s", str(payload)[:200])
            return None
    except Exception as e:  # noqa: BLE001
        log.warning("credit fetch failed: %s", e)
        return None


async def sync_user_balance_from_kie(user) -> dict[str, Any]:
    """Report upstream pool credits for ops — never overwrite per-user balance.

    Each Zeus user has their own balance_usd (RUB). The shared upstream wallet
    is only for platform capacity; mirroring it onto users broke billing.
    """
    credits = await fetch_kie_credits()
    balance = round(float(getattr(user, "balance_usd", 0) or 0), 4)
    return {
        "credits": round(float(credits), 4) if credits is not None else None,
        "synced": False,
        "balance_rub": balance,
        # legacy keys (no provider name in UI)
        "kie_credits": round(float(credits), 4) if credits is not None else None,
        "kie_synced": False,
    }
