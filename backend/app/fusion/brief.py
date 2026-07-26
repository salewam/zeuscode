"""Anti-bloat Brief for Panel satellites (AD-4, FR-22).

Satellites must never receive the full Cursor/skills dump. Brief is derived from
already-scrubbed Leader context (AD-17) and contains only:
  • last_assistant
  • errors
  • goal
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_ERROR_RE = re.compile(
    r"(?im)^(?:"
    r"Traceback \(most recent call last\):|"
    r"\w*(?:Error|Exception):\s+.+"
    r").*(?:\n(?:\s+.+)*)*"
)
_ERROR_LINE_RE = re.compile(
    r"(?i)\b(?:error|exception|traceback|failed|failure|panic)\b.{0,200}"
)


def _plain(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                parts.append(str(p.get("text") or p.get("content") or ""))
        return "\n".join(x for x in parts if x)
    if content is None:
        return ""
    return str(content)


def _clip(text: str, n: int) -> str:
    t = (text or "").strip()
    if len(t) <= n:
        return t
    if n < 80:
        return t[:n]
    head = max(40, (n * 2) // 3)
    tail = max(20, n - head - 5)
    return t[:head] + "\n…\n" + t[-tail:]


def extract_errors(text: str, *, max_len: int = 1200) -> str:
    """Pull traceback / error blocks from assistant or user text."""
    raw = text or ""
    blocks = [m.group(0).strip() for m in _ERROR_RE.finditer(raw)]
    if not blocks:
        blocks = [m.group(0).strip() for m in _ERROR_LINE_RE.finditer(raw)]
    if not blocks:
        return ""
    joined = "\n---\n".join(blocks)
    return _clip(joined, max_len)


@dataclass(frozen=True)
class SatelliteBrief:
    """Contract shape for satellite context (even before FULL panel is live)."""

    last_assistant: str
    errors: str
    goal: str

    def as_prompt_block(self) -> str:
        parts: list[str] = []
        if self.goal:
            parts.append(f"Goal:\n{self.goal}")
        if self.errors:
            parts.append(f"Errors:\n{self.errors}")
        if self.last_assistant:
            parts.append(f"Last assistant:\n{self.last_assistant}")
        return "\n\n".join(parts) if parts else "(empty brief)"

    def as_dict(self) -> dict[str, str]:
        return {
            "last_assistant": self.last_assistant,
            "errors": self.errors,
            "goal": self.goal,
        }


def build_satellite_brief(
    messages: list[dict[str, Any]],
    *,
    user_q: str | None = None,
    goal_max: int = 2800,
    assistant_max: int = 1600,
    errors_max: int = 1200,
) -> SatelliteBrief:
    """Build Brief from scrubbed messages — last_assistant + errors + goal only."""
    goal = (user_q or "").strip()
    last_assistant = ""
    for m in reversed(messages or []):
        role = (m.get("role") or "").strip().lower()
        text = _plain(m.get("content")).strip()
        if not goal and role == "user" and text:
            goal = text
        if not last_assistant and role == "assistant" and text:
            last_assistant = text
        if goal and last_assistant:
            break

    err_src = "\n".join(x for x in (last_assistant, goal) if x)
    errors = extract_errors(err_src, max_len=errors_max)
    return SatelliteBrief(
        last_assistant=_clip(last_assistant, assistant_max),
        errors=errors,
        goal=_clip(goal, goal_max),
    )


def satellite_messages_from_brief(
    brief: SatelliteBrief,
    *,
    system_prefix: str | None = None,
) -> list[dict[str, Any]]:
    """Turn Brief into the messages list sent to a satellite model."""
    out: list[dict[str, Any]] = []
    sys = (system_prefix or "").strip()
    if sys:
        out.append({"role": "system", "content": sys[:1000]})
    out.append(
        {
            "role": "user",
            "content": (
                "Ты ветка панели Zeus Fusion. Полный контекст IDE уже у лидера — "
                "дай сильную альтернативу: подход, код или правку по брифу. "
                "Без мета-воды, сразу полезный ответ.\n\n"
                f"Бриф:\n{brief.as_prompt_block()}"
            ),
        }
    )
    return out
