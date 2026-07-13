"""Align ZeusCode user-facing RUB prices with Polza.ai catalog."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.kie_sync import KIE_MODELS_PATH, load_kie_models

POLZA_MODELS_URL = "https://polza.ai/api/v1/models"
# Pass-through rate Polza uses for Gemini 2.5 Flash vs our Kie USD basis
POLZA_PASS_THROUGH = 138.024  # 12.42216 / 0.09

# Our id → Polza id (when names differ)
POLZA_ID_ALIASES: dict[str, str] = {
    "claude-haiku-4-5": "anthropic/claude-haiku-4.5",
    "claude-sonnet-4-5": "anthropic/claude-sonnet-4.5",
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4.6",
    "claude-sonnet-5": "anthropic/claude-sonnet-5",
    "claude-opus-4-5": "anthropic/claude-opus-4.5",
    "claude-opus-4-6": "anthropic/claude-opus-4.6",
    "claude-opus-4-7": "anthropic/claude-opus-4.7",
    "claude-opus-4-8": "anthropic/claude-opus-4.8",
    "claude-fable-5": "anthropic/claude-fable-5",
    "gemini-2.5-flash": "google/gemini-2.5-flash",
    "gemini-2.5-pro": "google/gemini-2.5-pro",
    "gemini-3-flash": "google/gemini-3-flash-preview",
    "gemini-3-pro": "google/gemini-3-pro-preview",
    "gemini-3.1-pro": "google/gemini-3.1-pro-preview",
    "gemini-3.5-flash": "google/gemini-3.5-flash",
    "gpt-5-2": "openai/gpt-5.2",
    "gpt-5-codex": "openai/gpt-5-codex",
    "gpt-5.1-codex": "openai/gpt-5.1-codex",
    "gpt-5.2-codex": "openai/gpt-5.2-codex",
    "gpt-5.3-codex": "openai/gpt-5.3-codex",
    "gpt-5.4": "openai/gpt-5.4",
    "gpt-5.4-codex": "openai/gpt-5.4",
    "gpt-5.5": "openai/gpt-5.5",
    "gpt-5.6-luna": "openai/gpt-5.6-luna",
    "gpt-5.6-sol": "openai/gpt-5.6-sol",
    "gpt-5.6-terra": "openai/gpt-5.6-terra",
    "grok-4-3": "x-ai/grok-4.3",
    "grok-4-5": "x-ai/grok-4.5",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _pricing(row: dict[str, Any]) -> dict[str, Any]:
    return ((row.get("top_provider") or {}).get("pricing") or {}) if isinstance(row, dict) else {}


async def fetch_polza_models() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(POLZA_MODELS_URL, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
    return list(data.get("data") or [])


def _index_polza(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for row in rows:
        rid = row.get("id") or ""
        idx[rid.lower()] = row
        short = rid.split("/")[-1].lower()
        idx[short] = row
        idx[_norm(short)] = row
        # dash/dot variants: claude-haiku-4.5 ↔ claude-haiku-4-5
        idx[_norm(short.replace(".", "-"))] = row
        idx[_norm(short.replace("-", "."))] = row
    return idx


def resolve_polza_row(our_id: str, idx: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    oid = (our_id or "").lower()
    if oid in POLZA_ID_ALIASES:
        alias = POLZA_ID_ALIASES[oid].lower()
        if alias in idx:
            return idx[alias]
        short = alias.split("/")[-1]
        if short in idx:
            return idx[short]
    if oid in idx:
        return idx[oid]
    n = _norm(oid)
    if n in idx:
        return idx[n]
    # soft: endswith
    for k, row in idx.items():
        if k.endswith(n) or n.endswith(_norm(k.split("/")[-1])):
            return row
    return None


def apply_polza_to_models(
    models: list[dict[str, Any]],
    polza_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    idx = _index_polza(polza_rows)
    matched = 0
    fallback = 0
    out: list[dict[str, Any]] = []
    for m in models:
        row = dict(m)
        modality = (row.get("modality") or "chat").lower()
        mid = row.get("id") or ""
        if modality == "chat":
            prow = resolve_polza_row(mid, idx)
            pricing = _pricing(prow) if prow else {}
            pin = pricing.get("prompt_per_million")
            pout = pricing.get("completion_per_million")
            cache = pricing.get("input_cache_read_per_million")
            if pin is not None:
                row["input_rub"] = round(float(pin), 4)
                row["output_rub"] = round(float(pout or 0), 4)
                if cache is not None:
                    row["cache_input_rub"] = round(float(cache), 4)
                row["pricing_source"] = "polza.ai"
                row["polza_id"] = prow.get("id")
                matched += 1
            else:
                # same effective rate as Polza Gemini pass-through
                row["input_rub"] = round(float(row.get("input_usd") or 0) * POLZA_PASS_THROUGH, 4)
                row["output_rub"] = round(float(row.get("output_usd") or 0) * POLZA_PASS_THROUGH, 4)
                if row.get("cache_input_usd") is not None:
                    row["cache_input_rub"] = round(float(row["cache_input_usd"]) * POLZA_PASS_THROUGH, 4)
                row["pricing_source"] = "polza-rate"
                fallback += 1
        else:
            # media: keep Kie USD × Polza pass-through so markup matches
            row["input_rub"] = round(float(row.get("input_usd") or 0) * POLZA_PASS_THROUGH, 4)
            row["output_rub"] = round(float(row.get("output_usd") or 0) * POLZA_PASS_THROUGH, 4)
            row["pricing_source"] = "polza-rate"
            fallback += 1
        out.append(row)
    stats = {
        "matched_polza": matched,
        "fallback_rate": fallback,
        "pass_through": POLZA_PASS_THROUGH,
        "polza_models": len(polza_rows),
    }
    return out, stats


async def sync_polza_prices() -> dict[str, Any]:
    """Write Polza RUB prices into kie_models.json and return stats."""
    models = load_kie_models()
    if not models:
        return {"ok": False, "error": "kie catalog empty — sync Kie first"}
    polza_rows = await fetch_polza_models()
    priced, stats = apply_polza_to_models(models, polza_rows)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "kie+polza",
        "polza_synced_at": datetime.now(timezone.utc).isoformat(),
        "models_n": len(priced),
        "models": priced,
        "polza_stats": stats,
    }
    # preserve raw_rows count if file exists
    if KIE_MODELS_PATH.exists():
        try:
            old = json.loads(KIE_MODELS_PATH.read_text(encoding="utf-8"))
            payload["raw_rows"] = old.get("raw_rows")
            payload["kie_fetched_at"] = old.get("fetched_at")
        except Exception:
            pass
    KIE_MODELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    KIE_MODELS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, **stats, "models_n": len(priced)}
