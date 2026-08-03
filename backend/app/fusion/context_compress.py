"""Cheap context compressor (TZ §5.1): shrink history before expensive roles."""

from __future__ import annotations

from typing import Any


def compress_tool_log(
    text: Any,
    *,
    max_chars: int = 3500,
    error_tail_chars: int = 1800,
) -> str:
    """Bound a tool log while preserving its error-rich tail verbatim."""
    raw = str(text or "").replace("\x00", "")
    if len(raw) <= max_chars:
        return raw
    tail_size = max(400, min(error_tail_chars, max_chars - 300))
    head_size = max_chars - tail_size - len("\n…[tool log compressed]…\n")
    return (
        raw[: max(0, head_size)]
        + "\n…[tool log compressed]…\n"
        + raw[-tail_size:]
    )


def compress_history(
    messages: list[dict[str, Any]] | None,
    *,
    keep_last: int = 6,
    max_chars_per_msg: int = 1200,
    max_total_chars: int = 8000,
) -> list[dict[str, Any]]:
    """Keep recent turns; truncate older bodies. No LLM call (deterministic)."""
    if not messages:
        return []
    cleaned: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip()
        if role not in ("user", "assistant", "tool"):
            continue
        content = m.get("content")
        if content is None:
            continue
        if not isinstance(content, str):
            content = str(content)
        cleaned.append({"role": role, "content": content})

    if len(cleaned) <= keep_last:
        out = cleaned
    else:
        head = cleaned[: -keep_last]
        tail = cleaned[-keep_last:]
        # One-line stubs for older turns
        stubs: list[dict[str, Any]] = []
        for m in head[-4:]:
            stub = (m["content"] or "").replace("\n", " ").strip()[:160]
            stubs.append({"role": m["role"], "content": f"[earlier] {stub}"})
        out = stubs + tail

    total = 0
    final: list[dict[str, Any]] = []
    for m in reversed(out):
        text = m["content"]
        if len(text) > max_chars_per_msg:
            if m["role"] == "tool":
                text = compress_tool_log(
                    text,
                    max_chars=max_chars_per_msg,
                    error_tail_chars=max_chars_per_msg * 2 // 3,
                )
            else:
                text = text[: max_chars_per_msg - 20] + "\n…[truncated]"
        if total + len(text) > max_total_chars and final:
            break
        final.append({"role": m["role"], "content": text})
        total += len(text)
    final.reverse()
    return final
