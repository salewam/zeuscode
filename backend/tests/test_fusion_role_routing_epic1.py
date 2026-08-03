"""Role Routing Epic 1 — contracts, classify, roles, pipeline=small, Onestack."""

from __future__ import annotations

import ast
from pathlib import Path

from app.fusion.model_power import TEST_AUTHOR_MIN, power_score
from app.fusion.pipeline import apply_small_path_clamps, pick_pipeline
from app.fusion.policy import classify_local, detect_second_signal
from app.fusion.roles import (
    assign_role_model,
    cap_doers,
    pick_curator,
    resolve_roles,
    resolve_stack,
    role_execute_panel,
)
from app.fusion.types import FusionResult
from app.fusion import prepare_messages_for_policy

_FUSION_ROOT = Path(__file__).resolve().parents[1] / "app" / "fusion"


def test_test_author_min_default():
    assert TEST_AUTHOR_MIN == 950


def test_power_stack_tz_crew():
    """TZ §1: меню бригады (панель на turn ≤3)."""
    stack = resolve_stack("power")
    assert stack[0] == "claude-opus-4-6"
    assert "gpt-5.4-mini" in stack
    assert "gpt-5.3-codex-spark" in stack
    assert "deepseek-v4-pro" in stack
    assert "grok-4.3" in stack
    assert "claude-haiku-4-5" in stack
    assert "gpt-5.5" not in stack
    assert "deepseek-v4-flash" not in stack


def test_architect_power_opus_then_gpt():
    stack = resolve_stack("power")
    a = assign_role_model("architect", "power", stack)
    assert a.model_id == "claude-opus-4-6"
    a2 = assign_role_model(
        "architect", "power", stack, unhealthy={"claude-opus-4-6"}
    )
    assert a2.model_id in (None, "gpt-5.4-mini") or (
        a2.model_id and power_score(a2.model_id) >= 900
    )
    ta = assign_role_model("test_author", "power", stack)
    assert ta.model_id == "grok-4.5"
    mini = assign_role_model("mini_verifier", "power", stack)
    assert mini.model_id == "claude-haiku-4-5"
    doer = assign_role_model("doer_logic", "power", stack)
    assert doer.model_id == "gpt-5.4"
    ui = assign_role_model("doer_ui", "power", stack)
    assert ui.model_id == "gpt-5.4"
    critic = assign_role_model("design_critic", "power", stack)
    assert critic.model_id == "grok-4.5"


def test_omp_style_model_aliases_on_power():
    from app.fusion.roles import resolve_model_aliases

    rr = resolve_roles(product_mode="power", task_kind="code")
    aliases = rr.model_aliases
    assert aliases["default"] == "gpt-5.4"
    assert aliases["smol"] == "claude-haiku-4-5"
    assert aliases["slow"] == "claude-opus-4-6"
    assert aliases["plan"] == "claude-opus-4-6"
    assert aliases["designer"] == "gpt-5.4"
    assert aliases["advisor"] == "claude-opus-4-6"
    assert resolve_model_aliases("power", rr.stack)["smol"] == aliases["smol"]


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
        leader="deepseek-v4-flash",
        branches=[],
        answer="ok",
        trace_id="t1",
        pipeline="small",
        curator_model="claude-opus-4-8",
        role_table="v2",
        roles=["doer_logic", "mini_verifier"],
        models_by_role={"doer_logic": "deepseek-v4-flash"},
        size="small",
        task_kind="light",
    )
    assert fr.pipeline == "small"
    # AD-32 refined: on small, execute leader (doer) may differ from curator
    assert fr.leader == "deepseek-v4-flash"
    assert fr.curator_model == "claude-opus-4-8"
    assert fr.role_table == "v2"


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


def test_pipeline_always_crew_on_light():
    rr = resolve_roles(product_mode="power", task_kind="light")
    d = pick_pipeline(
        size="small",
        second_signal=False,
        product_mode="power",
        kill_switch=False,
        roles=rr,
    )
    assert d.pipeline == "v1"
    assert d.reason == "always_crew"
    assert rr.curator_model == "claude-opus-4-6"
    assert d.serving_path_clamp is None
    path, panel, leader = apply_small_path_clamps(
        serving_path="FULL",
        panel=list(rr.stack),
        leader=rr.curator_model,
        decision=d,
    )
    assert path == "FULL"
    assert leader == "claude-opus-4-6"


def test_code_crew_v1_curator_opus_with_gpt_doer():
    rr = resolve_roles(product_mode="power", task_kind="code")
    d = pick_pipeline(
        size="small",
        second_signal=False,
        product_mode="power",
        kill_switch=False,
        roles=rr,
    )
    assert d.pipeline == "v1"
    assert d.curator_model == "claude-opus-4-6"
    assert "gpt-5.4" in d.doer_panel
    assert "claude-opus-4-6" in d.doer_panel
    _path, panel, leader = apply_small_path_clamps(
        serving_path="CASCADE",
        panel=list(rr.stack),
        leader=rr.curator_model,
        decision=d,
    )
    assert _path == "CASCADE"
    assert leader == "claude-opus-4-6"
    assert panel[0] == "claude-opus-4-6"


def test_power_single_crew_uses_event_driven_roles():
    """One roster is resolved once; crew_watch no longer repeats oversight."""
    rr = resolve_roles(product_mode="power", task_kind="code")
    assert rr.meta.get("crew_linked") is True
    assert rr.meta.get("crew_watch") is False
    assert rr.models_by_role["architect"] == "claude-opus-4-6"
    assert rr.models_by_role["test_author"] == "grok-4.5"
    assert rr.models_by_role["log_analyst"] == "deepseek-v4-pro"
    assert rr.models_by_role["doer_logic"] == "gpt-5.4"
    assert rr.curator_model == "claude-opus-4-6"
    rr_arch = resolve_roles(product_mode="power", task_kind="architecture")
    assert rr_arch.meta.get("crew_watch") is False
    rr_rev = resolve_roles(product_mode="power", task_kind="review")
    assert rr_rev.meta.get("crew_watch") is False


def test_task_label_cannot_change_single_crew_topology():
    rr = resolve_roles(product_mode="power", task_kind="light")
    assert rr.meta.get("crew_watch") is False
    assert rr.meta.get("crew_linked") is True
    assert rr.models_by_role["doer_logic"] == "gpt-5.4"
    assert rr.models_by_role["log_analyst"] == "deepseek-v4-pro"
    assert rr.models_by_role["architect"] == "claude-opus-4-6"
    assert rr.models_by_role["test_author"] == "grok-4.5"
    assert rr.curator_model == "claude-opus-4-6"
    d = pick_pipeline(
        size="small",
        second_signal=False,
        product_mode="power",
        kill_switch=False,
        roles=rr,
    )
    # Always-crew: light also enters v1 (no solo demotion)
    assert d.pipeline == "v1"
    assert d.reason == "always_crew"
    assert d.serving_path_clamp is None
    path, panel, leader = apply_small_path_clamps(
        serving_path="CASCADE",
        panel=list(rr.stack),
        leader=rr.curator_model,
        decision=d,
    )
    assert path == "CASCADE"
    assert leader == "claude-opus-4-6"


def test_architecture_always_crew_v1():
    """Coding/architecture always fixed crew (Brief→tests→doers)."""
    rr = resolve_roles(product_mode="power", task_kind="architecture")
    d = pick_pipeline(
        size="large",
        second_signal=True,
        product_mode="power",
        kill_switch=False,
        roles=rr,
    )
    assert d.pipeline == "v1"
    assert d.curator_model == "claude-opus-4-6"
    assert d.reason == "always_crew"
    assert d.serving_path_clamp is None
    assert len(d.doer_panel) >= 2


def test_review_and_landing_always_crew_v1():
    from app.fusion.policy import classify_local

    for prompt in (
        "Сделай code review: гонка в обновлении баланса без лока.",
        "Сделай минимальный HTML+CSS hero для лендинга автосервиса (один файл).",
        "Спроектируй архитектуру prepaid API биллинга: модули, миграции, тесты.",
    ):
        clf = classify_local(prompt, messages=[{"role": "user", "content": prompt}])
        rr = resolve_roles(product_mode="power", task_kind=str(clf.task_kind))
        d = pick_pipeline(
            size=str(clf.size),
            second_signal=bool(clf.second_signal),
            product_mode="power",
            kill_switch=False,
            roles=rr,
        )
        assert d.pipeline == "v1", (prompt, clf.task_kind, d.pipeline)
        assert len(d.doer_panel) >= 1


def test_pipeline_v1_does_not_mutate_compatibility_path_label():
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
    path, _panel, _leader = apply_small_path_clamps(
        serving_path="RACE",
        panel=list(rr.stack),
        leader=rr.curator_model,
        decision=d,
    )
    assert path == "RACE"


def test_pipeline_weak_stack_still_crew_v1():
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
    assert d.pipeline == "v1"
    assert d.reason == "always_crew"


def test_simple_also_crew_v1():
    rr = resolve_roles(product_mode="simple", task_kind="architecture")
    d = pick_pipeline(
        size="large",
        second_signal=True,
        product_mode="simple",
        kill_switch=False,
        roles=rr,
    )
    assert d.pipeline == "v1"
    assert d.reason == "always_crew"


def test_kill_switch_uses_emergency_single_pipeline():
    rr = resolve_roles(product_mode="power", task_kind="code")
    d = pick_pipeline(
        size="large",
        second_signal=True,
        product_mode="power",
        kill_switch=True,
        roles=rr,
    )
    assert d.pipeline == "fallback_single"
    assert d.reason == "kill_switch"


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
    assert path == "FULL"  # always-crew clamp; empty custom still no exclusive fill
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
