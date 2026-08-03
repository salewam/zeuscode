"""Error piggy bank (TZ §5.5): repeating log_digest → brief rule."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("zeus.fusion.error_bank")

_LOCK = threading.Lock()
_PATH = Path(__file__).resolve().parents[1] / "data" / "error_bank.json"
_HITS: dict[str, dict[str, Any]] = {}
_PROMOTE_AFTER = 3


def _fingerprint(text: str) -> str:
    norm = " ".join((text or "").lower().split())[:400]
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _load() -> None:
    global _HITS
    if _HITS:
        return
    if _PATH.exists():
        try:
            raw = json.loads(_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                _HITS = {str(k): v for k, v in raw.items() if isinstance(v, dict)}
        except (OSError, json.JSONDecodeError) as e:
            log.warning("error_bank load fail: %s", e)


def _save() -> None:
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(_HITS, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        log.warning("error_bank save fail: %s", e)


def note_log_digest(digest: str | dict[str, Any] | None) -> str | None:
    """Record digest; return promoted rule text when threshold hit."""
    if digest is None or digest == "N/A":
        return None
    if isinstance(digest, dict):
        text = str(digest.get("summary") or digest.get("digest") or digest)[:600]
    else:
        text = str(digest).strip()[:600]
    if len(text) < 12:
        return None
    fp = _fingerprint(text)
    with _LOCK:
        _load()
        row = _HITS.get(fp) or {"count": 0, "sample": text, "rule": None}
        row["count"] = int(row.get("count") or 0) + 1
        row["sample"] = text
        promoted = None
        if row["count"] >= _PROMOTE_AFTER and not row.get("rule"):
            rule = f"Повторяющаяся ошибка: {text[:200]}"
            row["rule"] = rule
            promoted = rule
        _HITS[fp] = row
        # Cap store
        if len(_HITS) > 500:
            for k in list(_HITS.keys())[:50]:
                _HITS.pop(k, None)
        _save()
        return promoted


def active_rules(*, max_n: int = 8) -> list[str]:
    with _LOCK:
        _load()
        rules = [str(v["rule"]) for v in _HITS.values() if v.get("rule")]
    return rules[-max_n:]


def format_rules_block(*, max_chars: int = 800) -> str:
    rules = active_rules()
    if not rules:
        return ""
    return ("Копилка ошибок (не повторять):\n- " + "\n- ".join(rules))[:max_chars]


def reset_error_bank_for_tests() -> None:
    global _HITS
    with _LOCK:
        _HITS = {}
        try:
            if _PATH.exists():
                _PATH.unlink()
        except OSError:
            pass
