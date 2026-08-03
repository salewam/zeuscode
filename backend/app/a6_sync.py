"""Pull A6 /v1/models into catalog rows (adapter=a6, ready=True)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger("zeus.a6_sync")
DATA_DIR = Path(__file__).resolve().parent / "data"
A6_MODELS_PATH = DATA_DIR / "a6_models.json"
# Себес A6, снятый по списаниям баланса (scripts/a6_price_probe.py).
A6_MEASURED_PATH = DATA_DIR / "a6_prices_measured.json"
# Порог правдоподобия: замер выше — это загрязнение окна отложенным списанием,
# а не реальный тариф. Такие строки не применяем, ждём перезамера.
_MAX_PLAUSIBLE_IN_USD = 200.0
_MAX_PLAUSIBLE_OUT_USD = 400.0

_SKIP = (
    "image",
    "realtime",
    "audio",
    "imagine",
    "whisper",
    "tts",
    "embedding",
    "moderation",
)


def _is_chat(model_id: str) -> bool:
    mid = (model_id or "").lower()
    return not any(k in mid for k in _SKIP)


def _family(model_id: str) -> str:
    mid = model_id.lower()
    if mid.startswith("gemini"):
        return "gemini"
    if mid.startswith("claude"):
        return "claude"
    if mid.startswith("gpt") or mid.startswith("codex"):
        return "gpt"
    if mid.startswith("grok"):
        return "grok"
    if mid.startswith("deepseek"):
        return "deepseek"
    if mid.startswith("kimi"):
        return "kimi"
    if mid.startswith("qwen"):
        return "qwen"
    if mid.startswith("glm"):
        return "glm"
    if mid.startswith("minimax"):
        return "minimax"
    return "other"


def _provider(model_id: str) -> str:
    fam = _family(model_id)
    return {
        "gemini": "Google",
        "claude": "Anthropic",
        "gpt": "OpenAI",
        "grok": "xAI",
        "deepseek": "DeepSeek",
        "kimi": "Moonshot",
        "qwen": "Alibaba",
        "glm": "Zhipu",
        "minimax": "MiniMax",
    }.get(fam, "A6")


async def fetch_a6_model_ids() -> list[str]:
    cfg = get_settings()
    key = (cfg.A6_API_KEY or "").strip()
    if not key:
        return []
    base = (cfg.A6_BASE_URL or "https://a6api.com/v1").rstrip("/")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{base}/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        r.raise_for_status()
        data = r.json()
    return [str(m["id"]) for m in (data.get("data") or []) if m.get("id")]


def rows_from_ids(ids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for mid in sorted(set(ids)):
        if not _is_chat(mid):
            continue
        out.append(
            {
                "id": mid,
                "title": mid,
                "provider": _provider(mid),
                "family": _family(mid),
                "modality": "chat",
                "adapter": "a6",
                "upstream_model": mid,
                "ready": True,
                "description": f"A6 upstream · {mid}",
                "input_usd": 0.0,
                "output_usd": 0.0,
                "cache_input_usd": None,
                "unit": "₽ / 1M токенов",
                "source": "a6",
                "pricing_source": "a6-live",
            }
        )
    return out


def load_measured_prices() -> dict[str, tuple[float, float]]:
    """model → (in_usd_per_1m, out_usd_per_1m); только достоверные замеры."""
    if not A6_MEASURED_PATH.exists():
        return {}
    try:
        raw = json.loads(A6_MEASURED_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, tuple[float, float]] = {}
    for row in raw.get("rows") or []:
        mid = str(row.get("model") or "").strip()
        if not mid or row.get("error") or row.get("suspect"):
            continue
        try:
            in_usd = float(row.get("in_usd_per_1m") or 0)
            out_usd = float(row.get("out_usd_per_1m") or 0)
        except (TypeError, ValueError):
            continue
        if in_usd <= 0 or out_usd <= 0:
            continue
        if in_usd > _MAX_PLAUSIBLE_IN_USD or out_usd > _MAX_PLAUSIBLE_OUT_USD:
            continue
        out[mid] = (in_usd, out_usd)
    return out


def apply_measured_prices(rows: list[dict[str, Any]]) -> int:
    """Проставить измеренный себес A6. Строки без замера не трогаем."""
    measured = load_measured_prices()
    if not measured:
        return 0
    n = 0
    for row in rows:
        price = measured.get(str(row.get("id") or ""))
        if price is None:
            continue
        row["input_usd"], row["output_usd"] = price
        # RUB считается из себеса через MARKUP × USD_RUB (app/cost.py)
        row.pop("input_rub", None)
        row.pop("output_rub", None)
        row["pricing_source"] = "a6-measured"
        n += 1
    return n


def load_a6_models() -> list[dict[str, Any]]:
    if not A6_MODELS_PATH.exists():
        return []
    try:
        raw = json.loads(A6_MODELS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(raw, dict):
        return list(raw.get("models") or [])
    if isinstance(raw, list):
        return raw
    return []


async def sync_a6_catalog() -> list[dict[str, Any]]:
    ids = await fetch_a6_model_ids()
    models = rows_from_ids(ids)
    priced = apply_measured_prices(models)
    log.info("A6_SYNC measured_prices=%s/%s", priced, len(models))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "n": len(models),
        "models": models,
    }
    A6_MODELS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    log.info("A6_SYNC models=%s path=%s", len(models), A6_MODELS_PATH)
    return models
