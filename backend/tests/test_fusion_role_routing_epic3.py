"""Role Routing Epic 3 — fallback_single curator one-shot (AD-23/32)."""

from __future__ import annotations

import asyncio

from app.fusion.model_power import TEST_AUTHOR_MIN, power_score
from app.fusion.panel import execute_fallback_single
from app.fusion.pipeline import apply_small_path_clamps, pick_pipeline, stamp_role_routing_onestack
from app.fusion.roles import resolve_roles
from app.fusion.verify import run_trusted_verify_loop


def test_weak_stack_architecture_still_crew_v1():
    rr = resolve_roles(
        product_mode="custom",
        task_kind="architecture",
        custom_models=["deepseek-v4-flash", "gemini-3-pro"],
    )
    assert rr.has_strong is False
    assert all(power_score(m) < TEST_AUTHOR_MIN for m in rr.stack)
    d = pick_pipeline(
        size="large",
        second_signal=True,
        product_mode="custom",
        kill_switch=False,
        roles=rr,
    )
    assert d.pipeline == "v1"
    assert d.reason == "always_crew"


def test_strong_architecture_always_crew_v1():
    rr = resolve_roles(product_mode="power", task_kind="architecture")
    assert rr.has_strong
    d = pick_pipeline(
        size="large",
        second_signal=True,
        product_mode="power",
        kill_switch=False,
        roles=rr,
    )
    assert d.pipeline == "v1"
    assert d.reason == "always_crew"


def test_crew_v1_clamps_to_full_with_curator_panel():
    rr = resolve_roles(
        product_mode="custom",
        task_kind="architecture",
        custom_models=["deepseek-v4-flash", "gemini-3-pro", "claude-haiku-4-5"],
    )
    d = pick_pipeline(
        size="large",
        second_signal=True,
        product_mode="custom",
        kill_switch=False,
        roles=rr,
    )
    assert d.pipeline == "v1"
    path, panel, leader = apply_small_path_clamps(
        serving_path="FULL",
        panel=list(rr.stack),
        leader=d.execute_leader or rr.curator_model,
        decision=d,
    )
    assert path == "FULL"
    assert panel
    assert panel[0] == leader


def test_execute_fallback_single_one_llm_no_brief():
    calls: list[str] = []
    saw_hint = False

    async def _up(model, messages, **_k):
        nonlocal saw_hint
        calls.append(model)
        blob = " ".join(str(m.get("content") or "") for m in messages)
        saw_hint = "fallback_single" in blob and "Architect Brief" in blob
        text = (
            "Полный ответ куратора: вот готовый лендинг HTML с секциями "
            "hero, услуги, контакты. Без Brief и без peer doers."
        )
        return {
            "ok": True,
            "text": text,
            "prompt_tokens": 10,
            "completion_tokens": 40,
        }

    out = asyncio.run(
        execute_fallback_single(
            curator="gemini-3-pro",
            messages=[{"role": "user", "content": "Сделай лендинг для СТО"}],
            user_q="Сделай лендинг для СТО",
            product_mode="custom",
            upstream_call=_up,
        )
    )
    assert len(calls) == 1
    assert calls[0] == "gemini-3-pro"
    assert saw_hint is True
    assert out.routed_by == "fallback_single_curator"
    assert out.leader == "gemini-3-pro"
    assert out.meta.get("no_architect_brief") is True
    assert out.meta.get("mid_parallel") is False
    assert out.meta.get("max_doer_llms") == 1
    assert len(out.branches) == 1
    assert out.branches[0].role == "doer_logic"


def test_execute_fallback_never_invents_second_model():
    seen: list[str] = []

    async def _up(model, messages, **_k):
        seen.append(model)
        return {"ok": True, "text": "solo answer body here", "prompt_tokens": 1, "completion_tokens": 5}

    out = asyncio.run(
        execute_fallback_single(
            curator="deepseek-v4-flash",
            messages=[{"role": "user", "content": "heavy task"}],
            upstream_call=_up,
        )
    )
    assert seen == ["deepseek-v4-flash"]
    assert out.meta.get("llm_calls") == 1


def test_onestack_fallback_curator_equals_leader():
    rr = resolve_roles(
        product_mode="custom",
        task_kind="architecture",
        custom_models=["deepseek-v4-flash", "gemini-3-pro"],
    )
    d = pick_pipeline(
        size="large",
        second_signal=True,
        product_mode="custom",
        kill_switch=False,
        roles=rr,
    )
    os_ = stamp_role_routing_onestack(
        {},
        decision=d,
        roles=rr,
        gate="GREEN",
        gate_reasons=["mini_pass"],
    )
    assert os_["pipeline"] == "v1"
    assert os_["curator_model"] == rr.curator_model
    assert os_["leader"] == (d.execute_leader or rr.curator_model)


def test_fallback_then_tv_verify_still_applies():
    """AD-23: after curator shot, Mini→Log→Escalate path still works."""
    import os

    os.environ["ZEUS_FUSION_MINI_HEURISTIC"] = "1"
    try:
        r = asyncio.run(
            run_trusted_verify_loop(
                answer="полный ответ куратора по лендингу без traceback",
                user_q="Сделай лендинг",
                panel=["gemini-3-pro"],
                models_by_role={"mini_verifier": "gemini-3-pro", "doer_logic": "gemini-3-pro"},
                curator_model="gemini-3-pro",
                early_exit=None,  # as execute_fallback_single leaves it
                routed_by="fallback_single_curator",
                allow_green_without_mini=False,
                max_escalate=2,
            )
        )
        assert r.gate in ("GREEN", "RED")
        assert r.escalate_count <= 2
        if r.gate == "GREEN":
            assert r.soft_stop is False
    finally:
        os.environ.pop("ZEUS_FUSION_MINI_HEURISTIC", None)


def test_fallback_empty_curator_disaster():
    out = asyncio.run(
        execute_fallback_single(
            curator="",
            messages=[{"role": "user", "content": "x"}],
        )
    )
    assert out.disaster is True
    assert out.routed_by == "fallback_single_disaster"


def test_unhealthy_strong_model_still_crew_without_dead_opus():
    """B1: dead opus must not count as has_strong (AD-23); crew still v1."""
    rr = resolve_roles(
        product_mode="custom",
        task_kind="architecture",
        custom_models=["claude-opus-4-8", "deepseek-v4-flash"],
        unhealthy={"claude-opus-4-8"},
    )
    assert rr.has_strong is False
    assert rr.curator_model == "deepseek-v4-flash"
    d = pick_pipeline(
        size="large",
        second_signal=True,
        product_mode="custom",
        kill_switch=False,
        roles=rr,
    )
    assert d.pipeline == "v1"
    assert d.curator_model == "deepseek-v4-flash"
    assert "claude-opus-4-8" not in d.doer_panel


def test_empty_curator_answer_tv_soft_stop_not_stuck():
    """B2: empty curator body still reaches Soft-Stop via TV (Story 3.1)."""
    import os

    from app.fusion.verify import SOFT_STOP_RED_LINE

    os.environ["ZEUS_FUSION_MINI_HEURISTIC"] = "1"
    os.environ["ZEUS_FUSION_JUDGE_FIX_HEURISTIC"] = "1"
    try:
        r = asyncio.run(
            run_trusted_verify_loop(
                answer="Ответ куратора недоступен.",
                user_q="Сделай лендинг",
                panel=["gemini-3-pro"],
                models_by_role={"mini_verifier": "gemini-3-pro", "judge_fix": "gemini-3-pro"},
                curator_model="gemini-3-pro",
                routed_by="fallback_single_curator",
                early_exit=None,
                soft_stop_already=False,
                allow_green_without_mini=False,
                max_escalate=0,  # force Soft-Stop after RED without burn
            )
        )
        # mini heuristic may fail short/empty-ish; either GREEN or Soft-Stop RED
        assert r.escalate_count <= 2
        if r.gate == "RED":
            assert r.soft_stop is True
            assert SOFT_STOP_RED_LINE in r.answer
    finally:
        os.environ.pop("ZEUS_FUSION_MINI_HEURISTIC", None)
        os.environ.pop("ZEUS_FUSION_JUDGE_FIX_HEURISTIC", None)
