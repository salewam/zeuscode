"""Telegram Mini App initData HMAC validation."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from app.telegram_webapp import validate_webapp_init_data


def _sign(fields: dict, bot_token: str) -> str:
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()


def test_validate_webapp_init_data_ok():
    token = "123456:ABC-DEF"
    user = {"id": 42, "first_name": "Test", "username": "tester"}
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps(user, separators=(",", ":")),
    }
    fields["hash"] = _sign(fields, token)
    # rebuild without hash in sign - already signed
    init = urlencode(fields)
    parsed = validate_webapp_init_data(init, token)
    assert parsed["user"]["id"] == 42
