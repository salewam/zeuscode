"""Fetch Kie.ai model pricing and normalize into ZeusCode catalog rows."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

PRICING_URL = "https://api.kie.ai/client/v1/model-pricing/page"
DATA_DIR = Path(__file__).resolve().parent / "data"
KIE_MODELS_PATH = DATA_DIR / "kie_models.json"
RAW_CATALOG_PATH = Path(__file__).resolve().parents[2] / "stage0" / "upstream_catalog.json"

# Display names from Kie → our API ids (keep stable for billing/routing)
ID_ALIASES: dict[str, str] = {
    "gemini 2.5 flash": "gemini-2.5-flash",
    "gemini 2.5 pro": "gemini-2.5-pro",
    "gemini 3 flash": "gemini-3-flash",
    "gemini 3 pro": "gemini-3-pro",
    "gemini 3.5 flash": "gemini-3.5-flash",
    "gemini 3.1 pro- openai": "gemini-3.1-pro",
    "gemini 3.1 pro-openai": "gemini-3.1-pro",
    "claude-haiku-4-5": "claude-haiku-4-5",
    "claude-sonnet-4-5": "claude-sonnet-4-5",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-sonnet-5": "claude-sonnet-5",
    "claude-opus-4-5": "claude-opus-4-5",
    "claude-opus-4-6": "claude-opus-4-6",
    "claude-opus-4-7": "claude-opus-4-7",
    "claude-opus-4-8": "claude-opus-4-8",
    "claude-fable-5": "claude-fable-5",
}

# Path overrides for Gemini OpenAI-compatible routes
PATH_OVERRIDES: dict[str, str] = {
    "gemini-3.5-flash": "gemini-3-5-flash-openai",
    # Kie rejects gemini-3.1-pro-openai; plain id works
    "gemini-3.1-pro": "gemini-3.1-pro",
}


def _slug(name: str) -> str:
    s = name.strip().lower()
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"[^\w./+-]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "model"


def normalize_model_id(name: str) -> str:
    key = re.sub(r"\s+", " ", name.strip().lower())
    if key in ID_ALIASES:
        return ID_ALIASES[key]
    # Claude-Haiku-4-5 → claude-haiku-4-5
    if key.startswith("claude"):
        return key.replace(" ", "-")
    return _slug(name)


def _parse_desc(desc: str) -> tuple[str, str]:
    parts = [p.strip() for p in (desc or "").split(",")]
    name = parts[0] if parts else "unknown"
    kind = parts[2].strip() if len(parts) > 2 else (parts[1].strip() if len(parts) > 1 else "")
    return name, kind


def _f(x: Any) -> float | None:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _kind_bucket(kind: str) -> str:
    k = (kind or "").strip().lower()
    if "cached input" in k or k == "cached input":
        return "cache_input"
    if "cache write" in k:
        return "cache_write"
    if k == "input" or k.endswith(" input"):
        return "input"
    if k == "output" or k.endswith(" output"):
        return "output"
    return "other"


# Kie returns 500 for these ids (live ping 2026-07-21) — drop from catalog
_UPSTREAM_DOWN = frozenset(
    {
        "gpt-5-codex",
        "gpt-5.1-codex",
        "gpt-5.2-codex",
        "gpt-5.3-codex",
    }
)


def infer_adapter(model_id: str, provider: str, modality: str) -> tuple[str, bool]:
    """Return (adapter, ready). Chat: gemini/claude/gpt/grok wired via Kie."""
    if modality != "chat":
        return "pending", False
    pid = model_id.lower()
    if pid in _UPSTREAM_DOWN:
        return "responses", False
    prov = (provider or "").lower()
    if pid.startswith("gemini") or "google" in prov:
        return "gemini", True
    if pid.startswith("claude") or "anthropic" in prov:
        return "claude", True
    # GPT-5.2 uses OpenAI-style chat completions on Kie
    if pid in {"gpt-5-2", "gpt-5.2"} or pid.startswith("gpt-5-2"):
        return "openai_chat", True
    if pid.startswith("gpt") or "openai" in prov:
        return "responses", True
    if pid.startswith("grok") or prov in {"grok", "xai"}:
        return "responses", True
    return "pending", False


def route_for(model_id: str, adapter: str) -> dict[str, str]:
    """Extra routing fields stored on catalog rows."""
    pid = (model_id or "").lower()
    if adapter == "openai_chat":
        return {"path": pid if pid.startswith("gpt") else model_id}
    if adapter != "responses":
        return {}
    if "codex" in pid:
        return {"path": "api/v1/responses", "upstream_model": model_id}
    if pid.startswith("grok"):
        return {"path": "grok/v1/responses", "upstream_model": model_id}
    if pid.startswith("gpt"):
        return {
            "path": "codex/v1/responses",
            "upstream_model": pid.replace(".", "-"),
        }
    return {"path": "codex/v1/responses", "upstream_model": model_id}

def provider_label(raw: str, modality: str) -> str:
    p = (raw or "Other").strip()
    if p.lower() == "grok":
        return "xAI"
    if p.lower() == "openai 4o":
        return "OpenAI"
    return p or "Other"


def family_for(model_id: str, provider: str, modality: str) -> str:
    if modality != "chat":
        return modality
    pid = model_id.lower()
    if pid.startswith("gemini"):
        return "gemini"
    if pid.startswith("claude"):
        return "claude"
    if pid.startswith("gpt"):
        return "gpt"
    if pid.startswith("grok"):
        return "grok"
    return (provider or "other").lower()


async def fetch_kie_pricing_rows() -> list[dict[str, Any]]:
    settings = get_settings()
    key = settings.upstream_api_key or ""
    headers = {
        "Authorization": f"Bearer {key}" if key else "",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for page in range(1, 50):
            r = await client.post(
                PRICING_URL,
                headers=headers,
                json={"pageNum": page, "pageSize": 100},
            )
            data = r.json()
            payload = data.get("data") or {}
            records = payload.get("records") or payload.get("list") or payload.get("rows") or []
            if not records:
                break
            rows.extend(records)
            total = int(payload.get("total") or 0)
            if total and len(rows) >= total:
                break
    return rows


def rows_to_models(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        name, kind = _parse_desc(r.get("modelDescription") or "")
        modality = (r.get("interfaceType") or "other").strip().lower()
        mid = normalize_model_id(name)
        key = (modality, mid)
        grouped.setdefault(key, []).append({**r, "_name": name, "_kind": kind})

    models: list[dict[str, Any]] = []
    for (modality, mid), items in grouped.items():
        if (mid or "").lower() in _UPSTREAM_DOWN:
            continue  # known dead on Kie — do not resurface
        provider = provider_label(items[0].get("provider") or "", modality)
        title = items[0].get("_name") or mid
        buckets: dict[str, list[float]] = {
            "input": [],
            "output": [],
            "cache_input": [],
            "cache_write": [],
            "other": [],
        }
        price_rows = []
        units: set[str] = set()
        for it in items:
            usd = _f(it.get("usdPrice"))
            unit = (it.get("creditUnit") or "").strip()
            if unit:
                units.add(unit)
            bucket = _kind_bucket(it.get("_kind") or "")
            if usd is not None and usd >= 0:
                buckets[bucket].append(usd)
            price_rows.append(
                {
                    "kind": it.get("_kind") or "",
                    "usd": usd,
                    "unit": unit,
                    "credits": it.get("creditPrice"),
                }
            )

        if modality == "chat":
            input_usd = min(buckets["input"]) if buckets["input"] else 0.0
            output_usd = min(buckets["output"]) if buckets["output"] else 0.0
            cache_input = min(buckets["cache_input"]) if buckets["cache_input"] else None
            unit = "₽ / 1M токенов"
            unit_raw = "per million tokens"
        else:
            # media: show cheapest positive price as "from"
            positives = [u for u in buckets["other"] + buckets["input"] + buckets["output"] if u > 0]
            input_usd = min(positives) if positives else 0.0
            output_usd = input_usd
            cache_input = None
            unit_raw = next(iter(units), "per request")
            unit = {
                "per image": "₽ / изображение",
                "per second": "₽ / секунда",
                "per request": "₽ / запрос",
                "per million tokens": "₽ / 1M токенов",
            }.get(unit_raw, f"₽ · {unit_raw}")

        adapter, ready = infer_adapter(mid, provider, modality)
        row: dict[str, Any] = {
            "id": mid,
            "title": title,
            "provider": provider,
            "family": family_for(mid, provider, modality),
            "modality": modality,
            "adapter": adapter,
            "description": "",
            "input_usd": float(input_usd),
            "output_usd": float(output_usd),
            "cache_input_usd": float(cache_input) if cache_input is not None else None,
            "ready": ready,
            "unit": unit,
            "unit_raw": unit_raw,
            "source": "kie",
            "price_rows": price_rows,
        }
        row.update(route_for(mid, adapter))
        if mid in PATH_OVERRIDES:
            row["path"] = PATH_OVERRIDES[mid]
        if cache_input is not None:
            row["badge"] = "cache"
        models.append(row)

    # stable sort: chat ready first, then by provider/title
    order_mod = {"chat": 0, "image": 1, "video": 2, "music": 3}

    def sort_key(m: dict[str, Any]) -> tuple:
        return (
            order_mod.get(m.get("modality") or "", 9),
            0 if m.get("ready") else 1,
            m.get("provider") or "",
            m.get("title") or "",
        )

    models.sort(key=sort_key)
    return models


async def sync_kie_catalog(*, save_raw: bool = True) -> dict[str, Any]:
    rows = await fetch_kie_pricing_rows()
    if not rows and RAW_CATALOG_PATH.exists():
        raw = json.loads(RAW_CATALOG_PATH.read_text(encoding="utf-8"))
        rows = raw.get("rows") or []
    models = rows_to_models(rows)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": PRICING_URL,
        "raw_rows": len(rows),
        "models_n": len(models),
        "models": models,
    }
    KIE_MODELS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if save_raw:
        RAW_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        RAW_CATALOG_PATH.write_text(
            json.dumps(
                {
                    "total": len(rows),
                    "fetched_at": payload["fetched_at"],
                    "rows": rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return payload


def load_kie_models() -> list[dict[str, Any]]:
    if KIE_MODELS_PATH.exists():
        data = json.loads(KIE_MODELS_PATH.read_text(encoding="utf-8"))
        return list(data.get("models") or [])
    if RAW_CATALOG_PATH.exists():
        raw = json.loads(RAW_CATALOG_PATH.read_text(encoding="utf-8"))
        return rows_to_models(raw.get("rows") or [])
    return []
