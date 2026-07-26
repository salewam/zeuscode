"""Product usage analytics — every user request → SQLite + daily JSONL files.

Cursor/VS Code has no Zeus UI buttons: we log API chat completions and
explicit product events (prefs/feedback). Never raises to callers.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("zeus.usage")
_file_lock = threading.Lock()


def _root_data() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def usage_dir() -> Path:
    try:
        from app.config import get_settings

        raw = (get_settings().USAGE_LOG_DIR or "").strip()
        if raw:
            return Path(raw).expanduser()
    except Exception:  # noqa: BLE001
        pass
    return _root_data() / "usage"


def analytics_enabled() -> bool:
    try:
        from app.config import get_settings

        return bool(get_settings().USAGE_ANALYTICS_ENABLED)
    except Exception:  # noqa: BLE001
        return True


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def prompt_preview_from_messages(messages: list[dict[str, Any]] | None, *, limit: int = 280) -> str:
    if not messages:
        return ""
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        c = m.get("content")
        if isinstance(c, str):
            text = c
        elif isinstance(c, list):
            parts: list[str] = []
            for p in c:
                if isinstance(p, str):
                    parts.append(p)
                elif isinstance(p, dict):
                    parts.append(str(p.get("text") or p.get("content") or ""))
            text = "\n".join(x for x in parts if x)
        else:
            text = str(c or "")
        text = " ".join(text.split())
        return text[:limit]
    return ""


def _append_jsonl(row: dict[str, Any]) -> Path | None:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    folder = usage_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{day}.jsonl"
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with _file_lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    return path


def user_identity_meta(user: Any | None) -> dict[str, Any]:
    """Stable identity fields for analytics joins."""
    if user is None:
        return {}
    out: dict[str, Any] = {}
    try:
        tid = getattr(user, "telegram_id", None)
        if tid:
            out["telegram_id"] = int(tid)
        uname = (getattr(user, "telegram_username", None) or "").strip()
        if uname:
            out["telegram_username"] = uname
        fname = (getattr(user, "telegram_first_name", None) or "").strip()
        if fname:
            out["telegram_first_name"] = fname
        bal = getattr(user, "balance_usd", None)
        if bal is not None:
            out["balance_rub"] = round(float(bal or 0), 2)
        pref = (getattr(user, "fusion_pref", None) or "").strip()
        if pref:
            out["fusion_pref"] = pref
    except Exception:  # noqa: BLE001
        pass
    return out


async def log_user_action(
    db: "AsyncSession | None",
    *,
    event: str,
    user: Any | None = None,
    user_id: int | None = None,
    source: str = "tg",
    prompt_preview: str = "",
    status_code: int = 200,
    latency_ms: int = 0,
    error: str = "",
    meta: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    """Convenience wrapper: TG/bot/UI actions with identity in meta."""
    uid = user_id
    if uid is None and user is not None:
        try:
            uid = int(getattr(user, "id"))
        except Exception:  # noqa: BLE001
            uid = None
    merged = user_identity_meta(user)
    if meta:
        merged.update(meta)
    await log_product_event(
        db,
        event=event,
        user_id=uid,
        source=source,
        prompt_preview=prompt_preview,
        status_code=status_code,
        latency_ms=latency_ms,
        error=error,
        meta=merged,
        **kwargs,
    )


async def log_product_event(
    db: "AsyncSession | None",
    *,
    event: str,
    user_id: int | None = None,
    api_key_id: int | None = None,
    key_prefix: str = "",
    source: str = "api",
    model: str = "",
    stream: bool = False,
    session_id: str = "",
    prompt_preview: str = "",
    path: str = "",
    policy_path: str = "",
    leader: str = "",
    routed_by: str = "",
    trace_id: str = "",
    status_code: int = 0,
    latency_ms: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_rub: float = 0.0,
    error: str = "",
    meta: dict[str, Any] | None = None,
) -> None:
    """Best-effort write to DB + JSONL. Never raises."""
    if not analytics_enabled():
        return
    meta = meta or {}
    now = datetime.now(timezone.utc)
    row = {
        "ts": now.isoformat(),
        "event": (event or "event")[:40],
        "source": (source or "api")[:40],
        "user_id": user_id,
        "api_key_id": api_key_id,
        "key_prefix": (key_prefix or "")[:24],
        "model": (model or "")[:120],
        "stream": bool(stream),
        "session_id": (session_id or "")[:128],
        "prompt_preview": (prompt_preview or "")[:500],
        "path": (path or "")[:20],
        "policy_path": (policy_path or "")[:20],
        "leader": (leader or "")[:120],
        "routed_by": (routed_by or "")[:80],
        "trace_id": (trace_id or "")[:64],
        "status_code": int(status_code or 0),
        "latency_ms": int(latency_ms or 0),
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "cost_rub": float(cost_rub or 0.0),
        "error": (error or "")[:800],
        "meta": meta,
    }
    try:
        _append_jsonl(row)
    except Exception as e:  # noqa: BLE001
        log.warning("usage jsonl write failed: %s", e)

    if db is None:
        return
    try:
        from app.models import ProductUsageEvent

        db.add(
            ProductUsageEvent(
                created_at=now,
                user_id=user_id,
                api_key_id=api_key_id,
                key_prefix=row["key_prefix"],
                event=row["event"],
                source=row["source"],
                model=row["model"],
                stream=1 if stream else 0,
                session_id=row["session_id"],
                prompt_preview=row["prompt_preview"],
                path=row["path"],
                policy_path=row["policy_path"],
                leader=row["leader"],
                routed_by=row["routed_by"],
                trace_id=row["trace_id"],
                status_code=row["status_code"],
                latency_ms=row["latency_ms"],
                prompt_tokens=row["prompt_tokens"],
                completion_tokens=row["completion_tokens"],
                cost_rub=row["cost_rub"],
                error=row["error"],
                meta_json=json.dumps(meta, ensure_ascii=False),
            )
        )
        await db.commit()
    except Exception as e:  # noqa: BLE001
        log.warning("usage db write failed: %s", e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


def extract_result_fields(data: dict[str, Any] | None) -> dict[str, Any]:
    """Pull path/leader/usage from chat completion payload."""
    data = data or {}
    onestack = data.get("onestack") if isinstance(data.get("onestack"), dict) else {}
    fr = data.get("_fusion_result") or data.get("fusion_result")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    path = onestack.get("path") or getattr(fr, "path", None) or ""
    if isinstance(fr, dict):
        path = path or fr.get("path") or ""
        leader = onestack.get("leader") or fr.get("leader") or ""
        routed_by = onestack.get("routed_by") or fr.get("routed_by") or ""
        trace_id = onestack.get("trace_id") or fr.get("trace_id") or ""
        policy_path = onestack.get("policy_path") or fr.get("policy_path") or ""
    else:
        leader = onestack.get("leader") or getattr(fr, "leader", None) or ""
        routed_by = onestack.get("routed_by") or getattr(fr, "routed_by", None) or ""
        trace_id = onestack.get("trace_id") or getattr(fr, "trace_id", None) or ""
        policy_path = onestack.get("policy_path") or getattr(fr, "policy_path", None) or ""
    cost = 0.0
    bill = data.get("onestack_billing") if isinstance(data.get("onestack_billing"), dict) else {}
    if bill.get("charged_rub") is not None:
        try:
            cost = float(bill.get("charged_rub") or 0)
        except (TypeError, ValueError):
            cost = 0.0
    elif data.get("credits_consumed") is not None:
        try:
            cost = float(data.get("credits_consumed") or 0)
        except (TypeError, ValueError):
            cost = 0.0
    return {
        "path": str(path or ""),
        "policy_path": str(policy_path or ""),
        "leader": str(leader or ""),
        "routed_by": str(routed_by or ""),
        "trace_id": str(trace_id or ""),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "cost_rub": cost,
    }


class RequestTimer:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()

    def ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)
