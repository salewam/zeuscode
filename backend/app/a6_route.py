"""A6 (a6api.com) OpenAI-compatible routing — catalog id → upstream model id.

A6 is New-API style: POST {base}/chat/completions with Bearer sk-… and model name
in the body. Supplier/merchant choice is A6-side (key / dashboard), not Zeus.

This map is spelling/normalization only — never swap to a different model.
"""

from __future__ import annotations

# Catalog / client id → A6 model id when punctuation/casing differs.
# Do NOT remap dead SKUs onto siblings (e.g. gpt-5.4 → mini). That is forbidden.
A6_MODEL_MAP: dict[str, str] = {
    "gpt-5-2": "gpt-5.2",
    "gpt-5.2": "gpt-5.2",
    "gpt-5-4": "gpt-5.4",
    "gpt-5.4": "gpt-5.4",
    "gpt-5-4-mini": "gpt-5.4-mini",
    "gpt-5.4-mini": "gpt-5.4-mini",
    "gpt-5-5": "gpt-5.5",
    "gpt-5.5": "gpt-5.5",
    "gpt-5-6": "gpt-5.6",
    "gpt-5.6": "gpt-5.6",
    "gpt-5-6-luna": "gpt-5.6-luna",
    "gpt-5.6-luna": "gpt-5.6-luna",
    "gpt-5-6-terra": "gpt-5.6-terra",
    "gpt-5.6-terra": "gpt-5.6-terra",
    "gpt-5-6-sol": "gpt-5.6-sol",
    "gpt-5.6-sol": "gpt-5.6-sol",
    "gpt-5-4-codex": "gpt-5.4-codex",
    "gpt-5.4-codex": "gpt-5.4-codex",
    "gpt-5-3-codex": "gpt-5.3-codex",
    "gpt-5.3-codex": "gpt-5.3-codex",
    "gpt-5.3-codex-spark": "gpt-5.3-codex-spark",
    "grok-4-3": "grok-4.3",
    "grok-4.3": "grok-4.3",
    "grok-4-5": "grok-4.5",
    "grok-4.5": "grok-4.5",
    "deepseek-chat": "deepseek-chat",
    "deepseek-v4-flash": "deepseek-v4-flash",
    "deepseek-v4-pro": "deepseek-v4-pro",
    # Client short id → A6 listing id (same Gemini 3.1 Pro SKU).
    "gemini-3.1-pro": "gemini-3.1-pro-preview",
    "gemini-3-pro": "gemini-3-pro-preview",
}

# Adapters that are product-local (not a raw upstream LLM call).
_SKIP_ADAPTERS = frozenset({"ultra", "fusion", "pending", None})


def resolve_a6_model(model_id: str | None) -> str | None:
    """Return A6 model name for a catalog/client id, or None if not routable."""
    mid = (model_id or "").strip()
    if not mid:
        return None
    key = mid.lower()
    if key in A6_MODEL_MAP:
        return A6_MODEL_MAP[key]
    # identity for ids that already match A6 (claude-*, gemini-*, …)
    return mid


def a6_should_route(meta: dict | None) -> bool:
    if not meta:
        return False
    if meta.get("adapter") in _SKIP_ADAPTERS:
        return False
    if (meta.get("modality") or "chat") != "chat":
        return False
    if meta.get("ready") is False:
        return False
    return True
