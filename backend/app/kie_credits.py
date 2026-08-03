"""Upstream credits helper — Kie.ai credit API removed.

Kept for import compatibility with auth/billing; always returns no sync.
"""

from __future__ import annotations

from typing import Any


async def fetch_kie_credits(timeout: float = 12.0) -> float | None:
    """Kie credit endpoint removed — always None."""
    _ = timeout
    return None


async def sync_user_balance_from_kie(user) -> dict[str, Any]:
    """Report local user balance only (no upstream wallet sync)."""
    balance = round(float(getattr(user, "balance_usd", 0) or 0), 4)
    return {
        "credits": None,
        "synced": False,
        "balance_rub": balance,
        "kie_credits": None,
        "kie_synced": False,
    }
