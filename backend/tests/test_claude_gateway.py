from app.claude_gateway import (
    ZEUS_ANTHROPIC_PREFIX,
    gateway_picker_models,
    resolve_model_id,
)


def test_resolve_strips_gateway_prefix():
    assert resolve_model_id(f"{ZEUS_ANTHROPIC_PREFIX}gemini-3.1-pro") == "gemini-3.1-pro"
    assert resolve_model_id(f"{ZEUS_ANTHROPIC_PREFIX}zeuscode") == "zeuscode"
    assert resolve_model_id("zeuscode") == "zeuscode"
    assert resolve_model_id("zeus/fusion") == "zeuscode"
    assert resolve_model_id("fusion") == "zeuscode"


def test_gateway_picker_aliases_non_claude():
    rows = [
        {
            "id": "claude-sonnet-4-6",
            "title": "Claude Sonnet 4.6",
            "ready": True,
            "modality": "chat",
        },
        {
            "id": "gemini-3.1-pro",
            "title": "Gemini 3.1 Pro",
            "ready": True,
            "modality": "chat",
        },
        {
            "id": "zeuscode",
            "title": "ZeusCode",
            "ready": True,
            "modality": "chat",
        },
        {"id": "skip-me", "title": "x", "ready": False, "modality": "chat"},
    ]
    out = gateway_picker_models(rows)
    ids = {m["id"] for m in out}
    assert "claude-sonnet-4-6" in ids
    assert f"{ZEUS_ANTHROPIC_PREFIX}gemini-3.1-pro" in ids
    assert f"{ZEUS_ANTHROPIC_PREFIX}zeuscode" in ids
    assert "skip-me" not in ids
    gem = next(m for m in out if m["id"].endswith("gemini-3.1-pro"))
    assert gem["display_name"].startswith("ZeusCode")
