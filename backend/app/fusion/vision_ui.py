"""Vision UI check (TZ §3.3): screenshot → what is broken / what to click."""

from __future__ import annotations

from typing import Any


_VISION_SYSTEM = (
    "Ты Vision-роль ZeusCode. Смотри скриншот интерфейса. "
    "Ответь JSON: {\"broken\": bool, \"what\": \"...\", \"click\": \"css-selector или пусто\", "
    "\"works\": bool}. Проверяй работает ли (кнопка, форма, ошибка), не «красиво ли»."
)


async def vision_check_screenshot(
    *,
    image_b64: str | None,
    user_goal: str = "",
    model: str | None = None,
    upstream_call: Any | None = None,
) -> dict[str, Any]:
    """Ask vision-capable model about a page screenshot."""
    if not image_b64:
        return {
            "ok": False,
            "degraded": True,
            "broken": None,
            "error": "no_image",
            "ui_report": None,
        }
    mid = (model or "").strip() or "grok-4.3"
    # Multimodal content block (OpenAI-style); upstream adapters may remap
    user_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"Goal: {(user_goal or 'проверить UI')[:500]}\nСкажи что сломано и что нажать.",
        },
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
        },
    ]
    messages = [
        {"role": "system", "content": _VISION_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    try:
        if upstream_call is not None:
            data = await upstream_call(model=mid, messages=messages, stream=False, max_tokens=512)
        else:
            from app import upstream

            data = await upstream.chat_completions(
                model=mid, messages=messages, stream=False, max_tokens=512, temperature=0.1
            )
        from app import upstream as _up

        text = _up.extract_text(data) if isinstance(data, dict) else str(data or "")
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "degraded": True,
            "broken": None,
            "error": str(e)[:200],
            "ui_report": None,
        }

    import json
    import re

    report: dict[str, Any] = {"raw": (text or "")[:800]}
    try:
        m = re.search(r"\{[\s\S]*\}", text or "")
        if m:
            report = {**report, **json.loads(m.group(0))}
    except (json.JSONDecodeError, TypeError, ValueError):
        report["broken"] = None
        report["parse_degraded"] = True

    broken = report.get("broken")
    if not isinstance(broken, bool):
        broken = None
    return {
        "ok": broken is not None,
        "degraded": broken is None,
        "broken": broken,
        "error": None,
        "model": mid,
        "ui_report": report,
    }
