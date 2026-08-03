"""Curated design taste / насмотренность (TZ §3.4).

User-named competitors + shared category catalog. Never invent «top» from SEO search.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("zeus.fusion.taste")

_LOCK = threading.Lock()
_CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "taste_catalog.json"

# Seed categories — shared across users when they name nothing
_DEFAULT: dict[str, list[dict[str, str]]] = {
    "landing": [
        {"url": "https://linear.app", "note": "product landing clarity"},
        {"url": "https://stripe.com", "note": "enterprise trust + motion"},
    ],
    "dashboard": [
        {"url": "https://vercel.com/dashboard", "note": "dense ops UI"},
    ],
    "form": [
        {"url": "https://www.notion.so/signup", "note": "onboarding form"},
    ],
    "onboarding": [],
}

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)

ASK_COMPETITORS_ONCE = (
    "Есть продукты/сайты, на которые ориентируетесь? "
    "Киньте 1–2 ссылки — так я попаду в ваш вкус, а не в SEO-выдачу."
)


def _load_catalog() -> dict[str, list[dict[str, str]]]:
    if _CATALOG_PATH.exists():
        try:
            raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                out: dict[str, list[dict[str, str]]] = {}
                for k, v in raw.items():
                    if isinstance(v, list):
                        out[str(k)] = [x for x in v if isinstance(x, dict)]
                return out or dict(_DEFAULT)
        except (OSError, json.JSONDecodeError) as e:
            log.warning("taste catalog load fail: %s", e)
    return {k: list(v) for k, v in _DEFAULT.items()}


def _save_catalog(cat: dict[str, list[dict[str, str]]]) -> None:
    try:
        _CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CATALOG_PATH.write_text(json.dumps(cat, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        log.warning("taste catalog save fail: %s", e)


def detect_category(user_q: str) -> str:
    q = (user_q or "").lower()
    if any(x in q for x in ("дашборд", "dashboard", "admin", "crm")):
        return "dashboard"
    if any(x in q for x in ("онборд", "onboard", "signup", "регистрац")):
        return "onboarding"
    if any(x in q for x in ("форм", "form", "checkout", "оплат")):
        return "form"
    return "landing"


def extract_urls(text: str) -> list[str]:
    return list(dict.fromkeys(_URL_RE.findall(text or "")))[:8]


def add_refs(category: str, urls: list[str], *, note: str = "user") -> None:
    cat = _load_catalog()
    key = category if category in cat else "landing"
    bucket = list(cat.get(key) or [])
    existing = {str(x.get("url") or "") for x in bucket}
    for u in urls:
        if u.startswith("http") and u not in existing:
            bucket.append({"url": u, "note": note})
            existing.add(u)
    cat[key] = bucket[-40:]
    with _LOCK:
        _save_catalog(cat)


def refs_for(
    user_q: str,
    *,
    user_urls: list[str] | None = None,
    max_n: int = 3,
) -> list[dict[str, str]]:
    """Prefer user-named refs; else shared catalog for category."""
    if user_urls:
        return [{"url": u, "note": "user"} for u in user_urls[:max_n] if u.startswith("http")]
    cat = _load_catalog()
    bucket = list(cat.get(detect_category(user_q)) or [])
    return bucket[:max_n]


def format_taste_block(
    user_q: str,
    *,
    user_urls: list[str] | None = None,
    max_chars: int = 1200,
) -> str:
    refs = refs_for(user_q, user_urls=user_urls)
    if not refs:
        return ""
    lines = [f"- {r.get('url')} ({r.get('note') or 'ref'})" for r in refs]
    return ("Эталоны (насмотренность, не SEO):\n" + "\n".join(lines))[:max_chars]


def should_ask_competitors(*, memory: dict[str, Any] | None, user_q: str) -> bool:
    """Ask once per project when design task and no taste yet."""
    mem = memory or {}
    if mem.get("taste_asked"):
        return False
    if mem.get("taste_urls"):
        return False
    q = (user_q or "").lower()
    design = any(
        x in q
        for x in (
            "лендинг",
            "landing",
            "дизайн",
            "ui",
            "ux",
            "сайт",
            "hero",
            "вёрстк",
            "верстк",
        )
    )
    return design


def mark_asked(memory_key: str | None) -> None:
    if not memory_key:
        return
    from app.fusion.project_memory import load_memory, save_memory

    mem = load_memory(memory_key)
    mem["taste_asked"] = True
    save_memory(memory_key, mem)
