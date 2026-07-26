"""Validate Telegram Mini App initData (HMAC)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import HTTPException


def validate_webapp_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_s: int = 86400,
) -> dict:
    """Return parsed fields incl. user dict. Raises HTTPException on failure."""
    raw = (init_data or "").strip()
    token = (bot_token or "").strip()
    if not raw or not token:
        raise HTTPException(401, "Нет initData Telegram")

    parsed = dict(parse_qsl(raw, keep_blank_values=True))
    received = parsed.pop("hash", None)
    if not received:
        raise HTTPException(401, "Нет hash в initData")

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    calc = hmac.new(secret, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received):
        raise HTTPException(401, "Подпись Mini App неверна")

    try:
        auth_date = int(parsed.get("auth_date") or 0)
    except ValueError as e:
        raise HTTPException(401, "auth_date битый") from e
    if auth_date and max_age_s > 0 and (time.time() - auth_date) > max_age_s:
        raise HTTPException(401, "Сессия Mini App устарела — открой снова")

    user_raw = parsed.get("user") or "{}"
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as e:
        raise HTTPException(401, "user в initData битый") from e
    if not isinstance(user, dict) or not user.get("id"):
        raise HTTPException(401, "Нет telegram user id")

    return {"user": user, "auth_date": auth_date, "raw": parsed}
