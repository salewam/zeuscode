"""ZeusCode «client hands» policy — brain must not refuse local IDE/CLI execution.

External agents (Aider, Cursor, OpenCode, …) run files/shell on the user's machine.
Models must not meta-refuse with «I cannot access your terminal» when wired through Zeus.
"""

from __future__ import annotations

import re
from typing import Any

# OpenAI SDK / CLI User-Agent substrings (lowercase match)
_UA_CLIENTS: tuple[tuple[str, str], ...] = (
    ("aider", "aider"),
    ("opencode", "opencode"),
    ("cursor", "cursor"),
    ("continue", "continue"),
    ("codex", "codex"),
    ("claude-cli", "claude"),
    ("claude code", "claude"),
    ("goose", "goose"),
    ("crush", "crush"),
    ("openhands", "openhands"),
    ("roo", "roo"),
    ("kilo", "kilo"),
    ("cline", "cline"),
    ("windsurf", "windsurf"),
    ("librechat", "librechat"),
    ("open-webui", "openwebui"),
)

# System-prompt fingerprints when UA is generic (httpx, python-openai, litellm)
_SYSTEM_MARKERS: tuple[tuple[str, str], ...] = (
    ("aider is an ai programming tool", "aider"),
    ("aider is ai pair programming", "aider"),
    ("act as an expert software developer", "aider"),
    ("you are opencode", "opencode"),
    ("you are cline", "cline"),
    ("you are an expert coding assistant in cursor", "cursor"),
)

HANDS_SYSTEM_APPEND = """[ZeusCode · client hands]
The user's app (IDE/CLI agent on their computer) executes files, terminal, and git locally. You are the remote model only.
NEVER refuse with disclaimers like: cannot access/run terminal or files, cannot execute commands on the user's system, please run X yourself and paste output — when the task is coding, shell, or repo work.
Instead: produce the change or command output this client expects (edits, patches, tool calls, fenced shell blocks). If live stdout is unavailable, infer from repo context or apply the file edit directly. Match the user's language."""


_REFUSAL_RE = re.compile(
    r"(?i)(cannot|can't|unable to|do not)\s+(run|execute|access).{0,40}"
    r"(terminal|shell|command|your computer|your system|filesystem)|"
    r"please run .{0,80}(yourself|in your terminal)|"
    r"i cannot run terminal"
)


def detect_external_coding_client(
    *,
    user_agent: str | None = None,
    client_header: str | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> str | None:
    """Return client id (aider, cursor, …) or None if not an external agent chat."""
    hdr = (client_header or "").strip().lower()
    if hdr and hdr not in ("", "web", "unknown", "browser"):
        return hdr.split("/")[0].strip() or None

    ua = (user_agent or "").lower()
    for needle, cid in _UA_CLIENTS:
        if needle in ua:
            return cid

    blob = ""
    for m in (messages or [])[:6]:
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "").lower() == "system":
            blob += " " + _flatten(m.get("content")).lower()
    for needle, cid in _SYSTEM_MARKERS:
        if needle in blob:
            return cid
    if "aider" in blob and ("pair programming" in blob or "search/replace" in blob):
        return "aider"
    return None


def apply_client_hands_policy(
    messages: list[dict[str, Any]],
    *,
    client: str | None,
) -> list[dict[str, Any]]:
    if not client:
        return messages
    for m in messages[:3]:
        if str(m.get("role") or "").lower() == "system":
            if "ZeusCode · client hands" in _flatten(m.get("content")):
                return messages
            break
    out = [dict(m) for m in messages if isinstance(m, dict)]
    if not out:
        return [{"role": "system", "content": HANDS_SYSTEM_APPEND}]
    if out[0].get("role") == "system":
        prev = _flatten(out[0].get("content")).strip()
        out[0] = {
            **out[0],
            "content": f"{prev}\n\n{HANDS_SYSTEM_APPEND}".strip(),
        }
    else:
        out.insert(0, {"role": "system", "content": HANDS_SYSTEM_APPEND})
    return out


def looks_like_hands_refusal(text: str) -> bool:
    """Heuristic for post-checks / tests — assistant meta-refusal about local execution."""
    if not (text or "").strip():
        return False
    return bool(_REFUSAL_RE.search(text))


def _flatten(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                if p.get("type") in ("text", "input_text", "output_text"):
                    parts.append(str(p.get("text") or ""))
                elif "text" in p:
                    parts.append(str(p.get("text") or ""))
        return "".join(parts)
    return str(content)
