"""Claude Code gateway helpers.

Claude Code's /model picker (gateway discovery) only accepts model ids that
start with ``claude`` or ``anthropic``. Non-Claude ZeusCode models are therefore
exposed as ``anthropic.zeuscode/<real-id>`` and stripped back on inference.
"""

from __future__ import annotations

from typing import Any

ZEUS_ANTHROPIC_PREFIX = "anthropic.zeuscode/"


def resolve_model_id(model: str | None) -> str:
    """Strip ZeusCode Anthropic gateway prefix; normalize to catalog id."""
    m = (model or "").strip()
    if m.startswith(ZEUS_ANTHROPIC_PREFIX):
        m = m[len(ZEUS_ANTHROPIC_PREFIX) :]
    key = m.lower()
    aliases = {
        # OpenAI aliases → ZeusCode (для Orca совместимости)
        "gpt-4": "zeuscode",
        "gpt-4-turbo": "zeuscode",
        "gpt-4o": "zeuscode",
        "gpt-3.5-turbo": "studio-light",
        # Gemini aliases
        "gemini 2.5 flash": "gemini-2.5-flash",
        "gemini-flash": "gemini-2.5-flash",
        "flash": "gemini-2.5-flash",
        # ZeusCode aliases
        "zeus fusion": "zeuscode",
        "zeuscode fusion": "zeuscode",
        "zeuscode": "zeuscode",
        "fusion": "zeuscode",
        "zeus/fusion": "zeuscode",
        # Claude aliases
        "claude-opus-4": "claude-opus-4-8",
        "claude-sonnet-4": "claude-sonnet-4-6",
        "claude-sonnet-4-5": "claude-sonnet-4-6",
        "claude-3-5-sonnet-latest": "claude-sonnet-4-6",
        "claude-3-5-haiku-latest": "gemini-3.5-flash",
    }
    m = aliases.get(key, m)
    try:
        from app.catalog import canonical_model_id

        return canonical_model_id(m) or m
    except Exception:  # noqa: BLE001
        return m


def gateway_picker_models(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shape catalog rows for Claude Code GET /v1/models discovery."""
    out: list[dict[str, Any]] = []
    for r in rows:
        if not r.get("ready"):
            continue
        if (r.get("modality") or "chat") != "chat":
            continue
        mid = str(r.get("id") or "").strip()
        if not mid:
            continue
        title = str(r.get("title") or mid)
        display = title if title.startswith("ZeusCode") else f"ZeusCode · {title}"
        if mid.startswith("claude") or mid.startswith("anthropic"):
            pick_id = mid
        else:
            pick_id = f"{ZEUS_ANTHROPIC_PREFIX}{mid}"
        out.append(
            {
                "id": pick_id,
                "display_name": display,
                "type": "model",
                "object": "model",
                "owned_by": "zeuscode",
                "created_at": "2026-01-01T00:00:00Z",
            }
        )
    return out
