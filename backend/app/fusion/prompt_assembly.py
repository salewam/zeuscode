"""Stable prompt prefix assembly (TZ §2) — required for prompt caching.

Order is architectural, not a flag: fresh data above slot 7 kills the cache.
Zeus appends to the client system prompt — never replaces it.
"""

from __future__ import annotations

from typing import Any

from app.client_hands import HANDS_SYSTEM_APPEND


def assemble_messages(
    *,
    role_system: str,
    client_system: str = "",
    project_memory: str = "",
    taste_refs: str = "",
    artifacts: str = "",
    compressed_history: list[dict[str, Any]] | None = None,
    fresh_user: str,
    hands_append: bool = True,
) -> list[dict[str, Any]]:
    """Build chat messages with cache-stable prefix → volatile suffix.

    1 role system · 2 client system (+ hands append) · 3 project memory ·
    4 taste · 5 artifacts · 6 compressed history · 7 fresh user (+ fresh arts).
    """
    blocks: list[str] = []
    role = (role_system or "").strip()
    if role:
        blocks.append(role)

    client = (client_system or "").strip()
    if client:
        blocks.append(client)
    if hands_append and HANDS_SYSTEM_APPEND.strip():
        # Append only — never overwrite client skills / Cursor rules
        if HANDS_SYSTEM_APPEND.strip() not in client:
            blocks.append(HANDS_SYSTEM_APPEND.strip())

    mem = (project_memory or "").strip()
    if mem:
        blocks.append(f"[ZeusCode · project memory]\n{mem}")

    taste = (taste_refs or "").strip()
    if taste:
        blocks.append(f"[ZeusCode · taste / refs]\n{taste}")

    arts = (artifacts or "").strip()
    if arts:
        blocks.append(f"[ZeusCode · artifacts]\n{arts}")

    out: list[dict[str, Any]] = []
    if blocks:
        out.append({"role": "system", "content": "\n\n".join(blocks)})

    for m in compressed_history or []:
        if not isinstance(m, dict):
            continue
        role_m = str(m.get("role") or "").strip()
        content = m.get("content")
        if role_m not in ("user", "assistant", "system", "tool") or content is None:
            continue
        if role_m == "system":
            # History system lines stay below the stable prefix block
            out.append({"role": "system", "content": str(content)})
        else:
            out.append({"role": role_m, "content": content})

    fresh = (fresh_user or "").strip()
    if fresh:
        out.append({"role": "user", "content": fresh})
    return out


def extract_client_system(messages: list[dict[str, Any]] | None) -> str:
    """Pull client-provided system prompt(s) to preserve on reassemble."""
    parts: list[str] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").lower() != "system":
            continue
        text = m.get("content")
        if isinstance(text, list):
            chunks = []
            for p in text:
                if isinstance(p, dict) and p.get("text"):
                    chunks.append(str(p["text"]))
                elif isinstance(p, str):
                    chunks.append(p)
            text = "".join(chunks)
        if text and str(text).strip():
            parts.append(str(text).strip())
    return "\n\n".join(parts)


def strip_system_messages(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Non-system turns for history compression input."""
    out: list[dict[str, Any]] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").lower() == "system":
            continue
        out.append(m)
    return out
