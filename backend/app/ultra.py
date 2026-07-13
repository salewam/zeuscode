"""Ultra Mode — thin wrapper around Studio orchestration (backward compatible)."""

from __future__ import annotations

from typing import Any

from app.orchestrate import run_studio


async def run_ultra(user_messages: list[dict[str, Any]]) -> dict[str, Any]:
    user_text = ""
    history: list[dict[str, Any]] = []
    for m in user_messages:
        role = m.get("role")
        content = m.get("content", "")
        if isinstance(content, list):
            content = str(content)
        if role in ("user", "assistant") and content:
            history.append({"role": role, "content": content})
        if role == "user":
            user_text = content if isinstance(content, str) else str(content)
    if not user_text:
        user_text = "Сделай минимальный рабочий пример по запросу пользователя."
    # history without duplicating trailing user in agent call — run_studio adds if needed
    hist = history[:-1] if history and history[-1]["role"] == "user" else history
    data = await run_studio(
        user_text=user_text,
        intent="feature",
        mode="ultra",
        history=hist,
        brief=None,
    )
    # Keep legacy field name for API consumers
    os_meta = data.setdefault("onestack", {})
    os_meta["upstream_model"] = os_meta.get("bill_model")
    data["model"] = "ultra-mode"
    return data
