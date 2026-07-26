"""Role Routing Epic 1 — contracts, classify, roles, pipeline=small, Onestack."""

from __future__ import annotations

import ast
from pathlib import Path

from app.fusion.model_power import TEST_AUTHOR_MIN, power_score
from app.fusion.pipeline import apply_small_path_clamps, pick_pipeline
from app.fusion.policy import classify_local, detect_second_signal
from app.fusion.roles import cap_doers, pick_curator, resolve_roles
from app.fusion.types import FusionResult
from app.fusion import prepare_messages_for_policy

_FUSION_ROOT = Path(__file__).resolve().parents[1] / "app" / "fusion"


def test_test_author_min_default():
    assert TEST_AUTHOR_MIN == 950


def test_role_routing_modules_exist_no_routers_import():
    for name in ("roles.py", "pipeline.py", "merge.py", "log_analyst.py"):
        assert (_FUSION_ROOT / name).is_file(), name
    bad: list[str] = []
    for path in _FUSION_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.startswith("app.routers") or mod == "routers":
                    bad.append(f"{path.name}: from {mod}")
    assert not bad, bad


def test_fusion_result_has_role_routing_fields():
    fr = FusionResult(
        path="CASCADE",
        policy_path="CASCADE",
        routed_by="policy_light_cascade",
        phase="implement",
        complexity="light",
        leader="claude-opus-4-8",
        branches=[],
        answer="ok",
        trace_id="t1",
        pipeline="small",
        curator_model="claude-opus-4-8",
        role_table="v1",
        roles=["doer_logic", "mini_verifier"],
        models_by_role={"doer_logic": "claude-opus-4-8"},
        size="small",
        task_kind="light",
    )
    assert fr.pipeline == "small"
    assert fr.curator_model == fr.leader
    assert fr.role_table == "v1"


def test_classify_chitchat_small_no_second_signal():
    r = classify_local("привет")
    assert r.size == "small"
    assert r.second_signal is False
    assert r.task_kind == "light"


def test_classify_color_change_small():
    r = classify_local("поменяй цвет кнопки на синий")
    assert r.size == "small"
    assert r.second_signal is False


def test_classify_landing_second_signal_large():
    r = classify_local("Сделай лендинг для СТО с нуля")
    assert r.second_signal is True
    assert r.size == "large"


def test_confidence_low_not_second_signal():
    # detect_second_signal independent; low conf alone must not invent second_signal
    assert detect_second_signal("напиши функцию sum") is False


def test_context_chars_large_without_forcing_v1_intent_alone():
    big = "x" * 4500
    r = classify_local(big, messages=[{"role": "user", "content": big}])
    assert r.size == "large"
    # second_signal still false without lexicon/landing/etc.
    assert r.second_signal is False


def test_curator_is_max_power_score():
    stack = ["deepseek-v4-flash", "claude-opus-4-8", "gemini-3.1-pro"]
    cur = pick_curator(stack)
    assert cur == "claude-opus-4-8" or power_score(cur) >= power_score("claude-opus-4-8") - 5
    # opus should win among these
    assert cur == max(stack, key=power_score)


def test_custom_never_adds_models():
    rr = resolve_roles(
        product_mode="custom",
        task_kind="code",
        custom_models=["deepseek-v4-flash", "gemini-3-pro"],
    )
    assert set(rr.stack) <= {"deepseek-v4-flash", "gemini-3-pro"}
    assert rr.curator_model in rr.stack
    assert rr.has_strong is False  # neither ≥950 typically for these mid


def test_unhealthy_fallback_stays_in_stack():
    rr = resolve_roles(
        product_mode="power",
        task_kind="code",
        unhealthy={"claude-opus-4-8"},
    )
    assert rr.curator_model != "claude-opus-4-8"
    assert rr.curator_model in rr.stack


def test_pipeline_small_caps_doers_and_clamps_full():
    rr = resolve_roles(product_mode="power", task_kind="light")
    d = pick_pipeline(
        size="small",
        second_signal=False,
        product_mode="power",
        kill_switch=False,
        roles=rr,
    )
    assert d.pipeline == "small"
    assert len(d.doer_panel) <= 2
    path, panel, leader = apply_small_path_clamps(
        serving_path="FULL",
        panel=list(rr.stack),
        leader=rr.curator_model,
        decision=d,
    )
    assert path in ("FAST", "CASCADE")
    assert len(panel) <= 2
    assert leader == d.curator_model


def test_pipeline_v1_intent_when_large_2nd_strong():
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
    assert d.serving_path_clamp == "FULL"
    # AD-20: RACE must not remain serving Path for RR large
    path, _panel, _leader = apply_small_path_clamps(
        serving_path="RACE",
        panel=list(rr.stack),
        leader=rr.curator_model,
        decision=d,
    )
    assert path != "RACE"
    assert path == "FULL"


def test_pipeline_fallback_when_no_strong():
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
    assert d.pipeline == "fallback_single"
    assert len(d.doer_panel) <= 1


def test_simple_never_v1():
    rr = resolve_roles(product_mode="simple", task_kind="architecture")
    d = pick_pipeline(
        size="large",
        second_signal=True,
        product_mode="simple",
        kill_switch=False,
        roles=rr,
    )
    assert d.pipeline == "small"


def test_scrub_once_still_masks_api_key():
    msgs = prepare_messages_for_policy(
        [{"role": "user", "content": "key sk-abcdefghijklmnopqrstuvwxyz123456"}]
    )
    text = str(msgs[0].get("content") or "")
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in text
    assert "REDACTED" in text.upper() or "***" in text or "[REDACTED]" in text


def test_cap_doers():
    stack = ["a", "b", "c"]
    # synthetic — just length
    out = cap_doers(
        ["deepseek-v4-flash", "gemini-3.1-pro", "claude-opus-4-8"],
        "claude-opus-4-8",
        max_doers=2,
    )
    assert len(out) == 2
    assert out[0] == "claude-opus-4-8"


def test_empty_custom_stack_does_not_reinflate_panel():
    rr = resolve_roles(
        product_mode="custom",
        task_kind="light",
        custom_models=[],
    )
    assert rr.stack == []
    assert rr.curator_model is None
    d = pick_pipeline(
        size="small",
        second_signal=False,
        product_mode="custom",
        kill_switch=False,
        roles=rr,
    )
    path, panel, leader = apply_small_path_clamps(
        serving_path="FULL",
        panel=["claude-opus-4-8", "gemini-3.1-pro"],  # exclusive leak must not stick
        leader="claude-opus-4-8",
        decision=d,
    )
    assert path in ("FAST", "CASCADE")
    assert panel == []
    assert leader is None


def test_monolith_demotes_full_after_path_override_for_small():
    """Regression: zeus.path=FULL must not beat pipeline=small clamps (AD-20)."""
    src = (_FUSION_ROOT / "_monolith.py").read_text(encoding="utf-8")
    assert 'elif _pipe in ("small", "fallback_single")' in src
    assert '"FULL"' in src
    assert "kill wins over zeus.path" in src or "kill_switch" in src


def test_resolve_panel_custom_empty_rejects():
    from fastapi import HTTPException

    from app.fusion._monolith import resolve_panel

    try:
        resolve_panel(user=None, models=[], mode="full", product_mode="custom")
        raise AssertionError("expected HTTPException")
    except HTTPException as e:
        assert e.status_code == 400
        assert "custom" in str(e.detail).lower()
