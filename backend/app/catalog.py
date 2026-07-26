"""ZeusCode model catalog — Studio presets + synced upstream models.

Prices: upstream USD; user sees × MARKUP × USD_RUB (₽).
Kie models live in app/data/kie_models.json (see kie_sync.sync_kie_catalog).
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings

# Local ZeusCode products (not from Kie)
STUDIO_MODELS: list[dict[str, Any]] = [
    {
        "id": "deepseek-chat",
        "title": "DeepSeek Chat",
        "provider": "DeepSeek",
        "family": "deepseek",
        "modality": "chat",
        "adapter": "deepseek",
        "upstream_model": "deepseek-chat",
        "badge": "cheap",
        "description": "Прямой DeepSeek API. Хорош для кода и агентов.",
        "input_usd": 0.28,
        "output_usd": 0.42,
        "cache_input_usd": None,
        "ready": True,
        "unit": "₽ / 1M токенов",
        "source": "deepseek",
    },
    {
        "id": "deepseek-v4-flash",
        "title": "DeepSeek V4 Flash",
        "provider": "DeepSeek",
        "family": "deepseek",
        "modality": "chat",
        "adapter": "deepseek",
        "upstream_model": "deepseek-v4-flash",
        "badge": "cheap",
        "description": "Быстрый DeepSeek V4 Flash.",
        "input_usd": 0.14,
        "output_usd": 0.28,
        "cache_input_usd": None,
        "ready": True,
        "unit": "₽ / 1M токенов",
        "source": "deepseek",
    },
    {
        "id": "deepseek-v4-pro",
        "title": "DeepSeek V4 Pro",
        "provider": "DeepSeek",
        "family": "deepseek",
        "modality": "chat",
        "adapter": "deepseek",
        "upstream_model": "deepseek-v4-pro",
        "description": "Сильный DeepSeek V4 Pro.",
        "input_usd": 0.55,
        "output_usd": 2.19,
        "cache_input_usd": None,
        "ready": True,
        "unit": "₽ / 1M токенов",
        "source": "deepseek",
    },
    {
        "id": "zeuscode",
        "title": "ZeusCode",
        "provider": "ZeusCode",
        "family": "fusion",
        "modality": "chat",
        "adapter": "fusion",
        "badge": "killer",
        "description": (
            "Режим из Mini App: Пользовательский / Продвинутый / Набор. "
            "Модель в клиенте: zeuscode. "
            "(legacy alias: zeus/fusion)"
        ),
        "input_usd": 0.4,
        "output_usd": 2.5,
        "cache_input_usd": None,
        "ready": True,
        "unit": "₽ / 1M токенов",
        "source": "zeus",
    },
    {
        "id": "ultra-mode",
        "title": "ZeusCode Ultra",
        "provider": "ZeusCode",
        "family": "ultra",
        "modality": "chat",
        "adapter": "ultra",
        "badge": "killer",
        "description": "Команда агентов (фронт/бэк/дизайн/тесты) + скиллы + сборка. В студии = режим Ultra",
        "input_usd": 0.09,
        "output_usd": 0.75,
        "cache_input_usd": None,
        "ready": True,
        "unit": "₽ / 1M токенов",
        "source": "zeus",
    },
    {
        "id": "studio-light",
        "title": "ZeusCode Studio Лайт",
        "provider": "ZeusCode",
        "family": "studio",
        "modality": "chat",
        "adapter": "ultra",
        "badge": "cheap",
        "description": "1 быстрый агент · дешёвый черновик",
        "input_usd": 0.09,
        "output_usd": 0.75,
        "cache_input_usd": None,
        "ready": True,
        "unit": "₽ / 1M токенов",
        "source": "zeus",
    },
    {
        "id": "studio-standard",
        "title": "ZeusCode Studio Стандарт",
        "provider": "ZeusCode",
        "family": "studio",
        "modality": "chat",
        "adapter": "ultra",
        "description": "1 сильный агент + скилл под интент",
        "input_usd": 0.38,
        "output_usd": 3.0,
        "cache_input_usd": None,
        "ready": True,
        "unit": "₽ / 1M токенов",
        "source": "zeus",
    },
    {
        "id": "studio-ultra",
        "title": "ZeusCode Studio Ultra",
        "provider": "ZeusCode",
        "family": "studio",
        "modality": "chat",
        "adapter": "ultra",
        "badge": "killer",
        "description": "Команда агентов параллельно + синтез",
        "input_usd": 0.5,
        "output_usd": 3.5,
        "cache_input_usd": None,
        "ready": True,
        "unit": "₽ / 1M токенов",
        "source": "zeus",
    },
    {
        "id": "studio-premium",
        "title": "ZeusCode Studio Premium",
        "provider": "ZeusCode",
        "family": "studio",
        "modality": "chat",
        "adapter": "ultra",
        "badge": "benchmark",
        "description": "Лучшие модели на роль + полный синтез",
        "input_usd": 0.85,
        "output_usd": 4.275,
        "cache_input_usd": None,
        "ready": True,
        "unit": "₽ / 1M токенов",
        "source": "zeus",
    },
]


def _merge_catalog() -> list[dict[str, Any]]:
    from app.kie_sync import load_kie_models
    from app.polza_sync import POLZA_PASS_THROUGH

    by_id: dict[str, dict[str, Any]] = {}
    for m in STUDIO_MODELS:
        row = dict(m)
        # Studio billed like Polza pass-through on its USD basis
        row["input_rub"] = round(float(row.get("input_usd") or 0) * POLZA_PASS_THROUGH, 4)
        row["output_rub"] = round(float(row.get("output_usd") or 0) * POLZA_PASS_THROUGH, 4)
        row["pricing_source"] = "polza-rate"
        by_id[row["id"]] = row
    for m in load_kie_models():
        mid = m["id"]
        if mid in by_id and by_id[mid].get("source") == "zeus":
            continue
        by_id[mid] = dict(m)
    rows = list(by_id.values())
    mod_rank = {"chat": 0, "image": 1, "video": 2, "music": 3}

    def sk(m: dict[str, Any]) -> tuple:
        return (
            0 if m.get("source") == "zeus" else 1,
            mod_rank.get(m.get("modality") or "chat", 9),
            0 if m.get("ready") else 1,
            m.get("provider") or "",
            m.get("title") or "",
        )

    rows.sort(key=sk)
    return rows


MODELS: list[dict[str, Any]] = _merge_catalog()
BY_ID: dict[str, dict[str, Any]] = {m["id"]: m for m in MODELS}
BY_ID_LOWER: dict[str, dict[str, Any]] = {m["id"].lower(): m for m in MODELS}


def reload_catalog() -> list[dict[str, Any]]:
    """Reload after kie sync."""
    global MODELS, BY_ID, BY_ID_LOWER
    MODELS = _merge_catalog()
    BY_ID = {m["id"]: m for m in MODELS}
    BY_ID_LOWER = {m["id"].lower(): m for m in MODELS}
    return MODELS


# Public compound-brain id is ``zeuscode``; old fusion ids still resolve.
_FUSION_ALIASES: dict[str, str] = {
    "zeus/fusion": "zeuscode",
    "zeus-fusion": "zeuscode",
    "fusion": "zeuscode",
    "zeuscode": "zeuscode",
}


def canonical_model_id(model_id: str | None) -> str:
    """Resolve aliases + case to catalog id (never invent a new spelling)."""
    mid = (model_id or "").strip()
    if not mid:
        return ""
    alias = _FUSION_ALIASES.get(mid.lower())
    if alias:
        row = BY_ID.get(alias) or BY_ID_LOWER.get(alias.lower())
        return str(row["id"]) if row else alias
    row = BY_ID.get(mid) or BY_ID_LOWER.get(mid.lower())
    return str(row["id"]) if row else mid


def get_model(model_id: str) -> dict | None:
    mid = (model_id or "").strip()
    if not mid:
        return None
    row = BY_ID.get(mid)
    if row is not None:
        return row
    canon = _FUSION_ALIASES.get(mid.lower())
    if canon:
        return BY_ID.get(canon) or BY_ID_LOWER.get(canon.lower())
    # Clients often send Claude-fable-5 / Gemini-3.1-Pro — match case-insensitively.
    return BY_ID_LOWER.get(mid.lower())


def public_catalog(markup: float | None = None) -> list[dict]:
    settings = get_settings()
    m = markup if markup is not None else settings.MARKUP
    rate = settings.USD_RUB
    out = []
    for row in MODELS:
        mul = m * rate
        unit = row.get("unit") or "₽ / 1M токенов"
        modality = row.get("modality") or "chat"
        # Prefer Polza-aligned RUB prices when present
        if row.get("input_rub") is not None:
            pin = float(row["input_rub"])
            pout = float(row.get("output_rub") or 0)
            cache = (
                round(float(row["cache_input_rub"]), 4)
                if row.get("cache_input_rub") is not None
                else None
            )
        else:
            pin = round(float(row.get("input_usd") or 0) * mul, 4)
            pout = round(float(row.get("output_usd") or 0) * mul, 4)
            cache = (
                round(float(row["cache_input_usd"]) * mul, 4)
                if row.get("cache_input_usd") is not None
                else None
            )
        item = {
            "id": row["id"],
            "title": row["title"],
            "provider": row["provider"],
            "family": row.get("family") or "",
            "modality": modality,
            "badge": row.get("badge"),
            "description": row.get("description") or "",
            "ready": bool(row.get("ready")),
            "adapter": row.get("adapter") or "pending",
            "source": row.get("source") or "kie",
            "pricing_source": row.get("pricing_source") or "markup",
            "pricing": {
                "input_per_1m": round(pin, 4),
                "output_per_1m": round(pout, 4),
                "cache_input_per_1m": cache,
                "markup": m,
                "unit": unit,
                "unit_raw": row.get("unit_raw") or "",
                "from_rub": round(pin, 4),
            },
        }
        out.append(item)
    return out


def upstream_prices() -> dict[str, tuple[float, float]]:
    return {
        m["id"]: (float(m.get("input_usd") or 0), float(m.get("output_usd") or 0))
        for m in MODELS
        if (m.get("modality") or "chat") == "chat"
    }
