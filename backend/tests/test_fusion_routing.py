"""Fusion auto-route: classify_query + product modes + leader pick + classifier."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.fusion import (
    _parse_classifier_json,
    apply_classifier_guardrails,
    apply_user_fusion_pref,
    classify_query,
    classify_smart,
    classify_task,
    classifier_features,
    order_panel_leader_first,
    pick_leader,
    regex_classify,
    resolve_mode,
    resolve_routing,
    resolve_routing_ex,
)

_SIMPLE = ["deepseek-v4-flash", "gemini-3-pro", "claude-haiku-4-5"]
_POWER = [
    "claude-opus-4-6",
    "gpt-5.4",
    "deepseek-v4-pro",
    "gemini-3.1-pro",
]


def test_chitchat_fast():
    assert classify_query("привет") == "fast"
    assert classify_query("hello") == "fast"


def test_trivial_ui_fast():
    assert classify_query("поменяй цвет кнопки на красный") == "fast"


def test_serious_full():
    assert classify_query("отрефакторь архитектуру API") == "full"
    assert classify_query("сделай лендинг для автосервиса") == "full"


def test_product_simple_auto_within_cheap_stack():
    # simple uses classify — short chitchat → fast (1 of cheap panel)
    # FR-37: historic auto 1↔3 uses compat_1to3_* (not bare "auto")
    assert resolve_routing_ex("zeus/fusion", {"mode": "simple"}, "привет") == (
        "fast",
        "compat_1to3_auto",
        "simple",
    )
    assert resolve_routing_ex("zeus/fusion", {"mode": "simple"}, "отрефакторь архитектуру API") == (
        "full",
        "compat_1to3_auto",
        "simple",
    )


def test_product_power_auto():
    assert resolve_routing_ex("zeus/fusion", {"mode": "power"}, "привет") == (
        "fast",
        "compat_1to3_auto",
        "power",
    )
    assert resolve_routing_ex("zeus/fusion", {"mode": "power"}, "отрефакторь архитектуру API") == (
        "full",
        "compat_1to3_auto",
        "power",
    )


def test_product_custom():
    assert resolve_routing_ex("zeus/fusion", {"mode": "custom"}, "привет")[2] == "custom"


def test_default_fusion_power_auto():
    mode, by = resolve_routing("zeus/fusion", None, "привет")
    assert mode == "fast" and by == "compat_1to3_auto"


def test_force_overrides():
    # FR-37: forced_* ≠ legacy_*
    assert resolve_routing("zeus/fusion", {"mode": "full"}, "привет") == ("full", "forced_full")
    assert resolve_routing("zeus/fusion", {"mode": "fast"}, "напиши код") == ("fast", "forced_fast")
    assert resolve_routing("zeus/fusion-fast", None, "отрефакторь всё") == (
        "fast",
        "legacy_fast_alias",
    )
    assert resolve_mode("zeus/fusion", {"mode": "auto"}, "привет") == "fast"


def test_apply_user_pref():
    class U:
        fusion_pref = "simple"
        fusion_models = ""

    z, p = apply_user_fusion_pref(U(), zeus={}, models=None)
    assert z["mode"] == "simple"


def test_classify_task_kinds():
    assert classify_task("привет") == "light"
    assert classify_task("поменяй цвет кнопки") == "light"
    assert classify_task("отрефакторь архитектуру API") == "architecture"
    assert classify_task("сделай лендинг для сто") == "ui"
    assert classify_task("найди баг в коде, security review") == "review"


def test_pick_leader_simple():
    # light → flash; architecture/code → gemini-3-pro (strongest cheap)
    assert pick_leader(_SIMPLE, "light") == "deepseek-v4-flash"
    assert pick_leader(_SIMPLE, "architecture") == "gemini-3-pro"
    assert pick_leader(_SIMPLE, "code") == "gemini-3-pro"
    assert pick_leader(_SIMPLE, "ui") in ("claude-haiku-4-5", "gemini-3-pro", "deepseek-v4-flash")


def test_pick_leader_power():
    assert pick_leader(_POWER, "architecture") == "claude-opus-4-6"
    assert pick_leader(_POWER, "code") == "claude-opus-4-6"
    assert pick_leader(_POWER, "light") == "deepseek-v4-pro"
    assert pick_leader(_POWER, "review") in ("gpt-5.4", "claude-opus-4-6", "gemini-3.1-pro")


def test_order_leader_first():
    ordered = order_panel_leader_first(_POWER, "gpt-5.4")
    assert ordered[0] == "gpt-5.4"
    assert set(ordered) == set(_POWER)


def test_parse_classifier_json_ok():
    raw = '{"stack":"full","task":"architecture","confidence":0.91}'
    p = _parse_classifier_json(raw)
    assert p == {"stack": "full", "task": "architecture", "confidence": 0.91}


def test_parse_classifier_json_fence_and_alias():
    raw = '```json\n{"stack":"fast","task":"chitchat","confidence":0.8}\n```'
    p = _parse_classifier_json(raw)
    assert p["stack"] == "fast" and p["task"] == "light"


def test_parse_classifier_json_bad():
    assert _parse_classifier_json("not json") is None
    assert _parse_classifier_json('{"stack":"maybe","task":"code","confidence":1}') is None


def test_classifier_features_code_and_users():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "сначала сделай auth"},
        {"role": "assistant", "content": "ok\n```py\nx=1\n```"},
        {"role": "user", "content": "поправь это"},
    ]
    feat = classifier_features(msgs)
    assert feat["has_code_blocks"] is True
    assert feat["short_followup"] is True
    assert feat["last_user"] == "поправь это"
    assert feat["prev_user"] == "сначала сделай auth"
    assert "```py" in feat["last_assistant"]
    assert feat["n_user"] == 2
    assert feat["context_chars"] > 20


def test_guardrails_followup_forces_full():
    feat = {
        "short_followup": True,
        "has_code_blocks": True,
        "has_error_trace": False,
        "context_chars": 500,
        "last_user": "поправь это",
    }
    out = apply_classifier_guardrails(
        {"stack": "fast", "task": "light", "confidence": 0.9, "source": "llm"},
        feat,
    )
    assert out["stack"] == "full"
    assert out["task"] == "code"
    assert "followup+context→full" in out.get("guardrails", [])


def test_regex_classify_fallback():
    r = regex_classify("привет")
    assert r["stack"] == "fast" and r["task"] == "light" and r["source"] == "regex"


def test_classify_smart_chitchat_skips_llm():
    out = asyncio.run(classify_smart([{"role": "user", "content": "привет"}]))
    assert out["source"] == "regex-chitchat"
    assert out["stack"] == "fast"


def test_classify_smart_force_regex_skips_llm():
    """Hot path: force_regex=True must never call upstream."""

    async def _run():
        with patch(
            "app.fusion._monolith.upstream.chat_completions",
            new_callable=AsyncMock,
        ) as m:
            out = await classify_smart(
                [{"role": "user", "content": "поправь auth middleware"}],
                force_regex=True,
            )
            m.assert_not_called()
            return out

    out = asyncio.run(_run())
    assert out["source"] == "regex"
    assert out["stack"] in ("fast", "full")


def test_classify_smart_llm_accepted():
    fake = {
        "choices": [{"message": {"content": '{"stack":"full","task":"code","confidence":0.88}'}}],
        "usage": {"prompt_tokens": 40, "completion_tokens": 12},
    }

    async def _run():
        with patch("app.fusion._monolith.upstream.chat_completions", new_callable=AsyncMock) as m:
            m.return_value = fake
            return await classify_smart(
                [
                    {"role": "user", "content": "сначала auth"},
                    {"role": "assistant", "content": "```js\n1\n```"},
                    {"role": "user", "content": "поправь это для auth"},
                ]
            )

    out = asyncio.run(_run())
    assert out["source"] == "llm"
    assert out["stack"] == "full"
    assert out["task"] == "code"
    assert out["confidence"] == 0.88


def test_classify_smart_low_confidence_hybrid():
    fake = {
        "choices": [{"message": {"content": '{"stack":"full","task":"code","confidence":0.4}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }

    async def _run():
        with patch("app.fusion._monolith.upstream.chat_completions", new_callable=AsyncMock) as m:
            m.return_value = fake
            return await classify_smart(
                [
                    {"role": "assistant", "content": "```py\nprint(1)\n```"},
                    {"role": "user", "content": "поправь это"},
                ]
            )

    out = asyncio.run(_run())
    assert out["source"] == "hybrid-lowconf"
    assert out["stack"] == "full"  # signals + llm stack=full


def test_classify_smart_timeout_falls_back():
    async def _slow(*_a, **_k):
        await asyncio.sleep(5)
        return {}

    async def _run():
        with patch("app.fusion._monolith.upstream.chat_completions", side_effect=_slow):
            with patch("app.fusion._monolith._CLASSIFIER_TIMEOUT_S", 0.05):
                return await classify_smart([{"role": "user", "content": "поправь auth"}])

    out = asyncio.run(_run())
    assert out["source"].startswith("regex-")
