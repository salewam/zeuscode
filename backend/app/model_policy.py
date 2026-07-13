"""Per-account model allowlists (e.g. Gemini-only seats)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

# Studio product ids that still run on Gemini workers under the hood
_STUDIO_IDS = frozenset(
    {
        "ultra-mode",
        "ultra",
        "onestack-ultra",
        "studio-light",
        "studio-standard",
        "studio-ultra",
        "studio-premium",
    }
)


def user_model_family(user: Any) -> str:
    return (getattr(user, "model_family", None) or "").strip().lower()


def is_gemini_model(model_id: str | None) -> bool:
    mid = (model_id or "").strip().lower()
    if not mid:
        return True  # empty = auto → Flash/Pro Gemini
    if mid in _STUDIO_IDS:
        return True
    # Strict Gemini family only (not all Google image/video products)
    if mid.startswith("gemini"):
        return True
    return False


def model_allowed_for_user(user: Any, model_id: str | None) -> bool:
    family = user_model_family(user)
    if not family or family == "all":
        return True
    if family == "gemini":
        return is_gemini_model(model_id)
    return True


def assert_model_allowed(user: Any, model_id: str | None) -> None:
    if model_allowed_for_user(user, model_id):
        return
    raise HTTPException(
        403,
        f"На этом аккаунте доступны только модели Gemini (отклонено: {model_id})",
    )


def filter_catalog_for_user(user: Any | None, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not user or user_model_family(user) != "gemini":
        return rows
    return [r for r in rows if is_gemini_model(r.get("id"))]


def gemini_fallback_for_role(role: str) -> str:
    if role in ("synth", "reviewer", "judge"):
        return "gemini-2.5-pro"
    return "gemini-2.5-flash"
