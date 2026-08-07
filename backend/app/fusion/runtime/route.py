"""DEPRECATED: роутинг удалён. Leader=opus-4.6, doer=gpt-5.4 фиксированы.

Старый код перенесён в git history. Используется упрощённая схема без Path/pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.fusion.combo import (
    ALL_PERSISTED_MODES,
    DEFAULT_PRODUCT_MODE,
    normalize_product_mode as normalize_stack_mode,
)

# Backward compatibility exports
PRODUCT_MODES = frozenset(ALL_PERSISTED_MODES)
PUBLIC_FUSION_MODEL_ID = "zeuscode"


def normalize_product_mode(raw: str | None) -> str | None:
    """Map public aliases (оставлено для совместимости)."""
    mode = (raw or "").strip().lower()
    mapped = normalize_stack_mode(mode)
    if mapped:
        return mapped
    if mode in ALL_PERSISTED_MODES:
        return mode
    return None


def stack_to_path(stack: str | None) -> str:
    """Backward compatibility stub."""
    return "SIMPLE"


@dataclass(frozen=True, slots=True)
class RuntimeRoute:
    """Backward compatibility stub."""
    product_mode: str = "power"
    serving_path: str = "SIMPLE"
    classifier: dict[str, Any] | None = None
    resolved: str = "power"
    policy_path: str | None = None
    routed_by: str = "fixed"
    kill_switch: bool = False


def build_runtime_route(zeus: dict[str, Any] | None = None) -> RuntimeRoute:
    """DEPRECATED: возвращает маршрут из zeus или fallback power/SIMPLE."""
    product_mode = "power"
    if zeus and isinstance(zeus.get("product_mode"), str):
        product_mode = zeus["product_mode"].strip() or "power"
    elif zeus and isinstance(zeus.get("mode"), str):
        # legacy: zeus.mode → product_mode mapping
        mode = zeus["mode"].strip().lower()
        if mode in ("standard", "manual", "combo3"):
            product_mode = mode
    return RuntimeRoute(
        product_mode=product_mode,
        serving_path="SIMPLE",
        classifier={"source": "fixed", "task": "code", "path": "SIMPLE"},
    )


def resolve_show_thinking(show_thinking: bool | None = None, zeus: dict[str, Any] | None = None) -> bool:
    """Backward compatibility stub."""
    if show_thinking is not None:
        return show_thinking
    return bool(zeus and zeus.get("thinking"))
