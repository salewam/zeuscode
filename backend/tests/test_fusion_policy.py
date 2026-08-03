"""Epic 2 policy unit tests: classify, Effort, Path table, MoR, clamps, custom, Mini."""

from __future__ import annotations

from app.fusion.policy import (
    ClassifyResult,
    bump_complexity,
    cascade_escalate_action,
    classify_local,
    compute_interactive,
    detect_design_lexicon,
    leader_failover_chain,
    mor_scores,
    mor_tip_escalate,
    next_leader_failover,
    path_to_legacy_stack,
    resolve_custom_panel,
    resolve_request_policy,
    resolve_zeus_mode_fields,
    select_path_policy,
    thinking_passthrough,
)
from app.fusion.verify import mini_verifier_passed, parse_mini_verifier_json


def test_classify_phase_complexity_confidence():
    chat = classify_local("привет")
    assert chat.classify_phase == "chat"
    assert chat.complexity_band == "light"
    assert chat.confidence >= 0.7

    ui = classify_local("поменяй цвет кнопки на красный")
    assert ui.classify_phase == "ui"
    assert ui.complexity_band == "light"

    tb = classify_local("Traceback (most recent call last):\nTypeError: x")
    assert tb.classify_phase == "debug"
    assert tb.complexity_band in ("med", "heavy")

    # P06: "code review" must be review, not architecture/plan
    rev = classify_local(
        "Сделай code review: гонка в обновлении баланса "
        "user.balance_usd -= charge без лока. Найди баг и предложи фикс."
    )
    assert rev.classify_phase == "review"
    assert rev.task_kind == "review"
    assert rev.complexity_band == "med"
    assert not rev.design_lexicon


def test_effort_high_bump_cap_heavy():
    assert bump_complexity("light", "high") == "med"
    assert bump_complexity("med", "high") == "heavy"
    assert bump_complexity("heavy", "high") == "heavy"
    assert bump_complexity("light", "med") == "light"
    assert bump_complexity("light", "low") == "light"


def test_classify_fail_cascade():
    d = select_path_policy(
        classify=ClassifyResult(
            classify_phase="implement",
            complexity_band="med",
            confidence=0.0,
            failed=True,
        ),
        product_mode="power",
    )
    assert d.path == "CASCADE"
    assert d.routed_by == "classify_fallback_cascade"


def test_design_lexicon_forces_full_power():
    assert detect_design_lexicon("спроектируй модуль auth")
    d = select_path_policy(
        classify=ClassifyResult(
            classify_phase="implement",
            complexity_band="med",
            confidence=0.7,
            design_lexicon=True,
        ),
        product_mode="power",
        user_q="спроектируй модуль auth",
    )
    assert d.path == "FULL"
    assert d.routed_by == "policy_design_lexicon_full"
    assert d.policy_phase == "plan"
    assert d.phase == "implement"  # classify phase preserved


def test_simple_clamp_never_full_from_lexicon():
    d = select_path_policy(
        classify=ClassifyResult(
            classify_phase="implement",
            complexity_band="med",
            confidence=0.7,
            design_lexicon=True,
        ),
        product_mode="simple",
        user_q="спроектируй модуль auth",
    )
    assert d.path == "CASCADE"
    assert d.routed_by == "mode_simple_clamp"


def test_kill_switch_fast():
    d = select_path_policy(
        classify=ClassifyResult(
            classify_phase="review",
            complexity_band="heavy",
            confidence=0.9,
        ),
        kill_switch=True,
        product_mode="power",
    )
    assert d.path == "FAST"
    assert d.routed_by == "kill_switch"


def test_forced_vs_legacy_routed_by():
    prod, forced, legacy, ignored = resolve_zeus_mode_fields(
        model_id="zeus/fusion", zeus={"mode": "full"}
    )
    assert forced == "forced_full" and legacy is None and not ignored

    prod, forced, legacy, ignored = resolve_zeus_mode_fields(
        model_id="zeus/fusion-full", zeus=None
    )
    assert legacy == "legacy_full_alias" and forced is None

    d_f = select_path_policy(
        classify=ClassifyResult("chat", "light", 0.9),
        forced_code="forced_full",
        product_mode="power",
    )
    assert d_f.routed_by == "forced_full" and d_f.path == "FULL"

    d_l = select_path_policy(
        classify=ClassifyResult("chat", "light", 0.9),
        legacy_code="legacy_full_alias",
        product_mode="power",
    )
    assert d_l.routed_by == "legacy_full_alias" and d_l.path == "FULL"


def test_unknown_mode_ignored():
    prod, forced, legacy, ignored = resolve_zeus_mode_fields(
        model_id="zeus/fusion",
        zeus={"mode": "turbo-blaster"},
        prefs_product_mode="power",
    )
    assert ignored is True
    assert prod == "power"
    assert forced is None and legacy is None

    d = resolve_request_policy(
        user_q="привет",
        model_id="zeus/fusion",
        zeus={"mode": "turbo-blaster"},
        prefs_product_mode="power",
    )
    assert d.mode_ignored is True
    assert d.path == "FAST"
    assert d.routed_by == "mode_ignored"


def test_thinking_passthrough_no_path_effect():
    assert thinking_passthrough({"thinking": True}) is True
    assert thinking_passthrough({"thinking": False}) is False
    assert thinking_passthrough({}) is None


def test_mor_tip_only_escalates_fast():
    scores = mor_scores(
        complexity="med", effort="med", confidence=0.4, interactive=False
    )
    # s_quality = 0.55 + 0.20*(1-0.4) = 0.67
    assert scores["s_quality"] >= 0.60
    tip = mor_tip_escalate(
        scores, policy_path="FAST", kill_switch=False, forced_or_legacy=False
    )
    assert tip == 1
    tip_c = mor_tip_escalate(
        scores, policy_path="CASCADE", kill_switch=False, forced_or_legacy=False
    )
    assert tip_c == 0  # never demotes; no CASCADE→RACE tip in MVP harness


def test_f14_effort_high_not_fast():
    d = select_path_policy(
        classify=ClassifyResult(
            classify_phase="chat",
            complexity_band="light",
            confidence=0.75,
        ),
        effort="high",
        product_mode="power",
    )
    assert d.complexity == "med"
    assert d.path == "CASCADE"
    assert d.path != "FAST"


def test_interactive_gates():
    assert compute_interactive(
        policy_phase="ui",
        complexity="light",
        design_lexicon=False,
        kill_switch=False,
        user_q="поправь отступы у кнопки пожалуйста",
        has_last_assistant=True,
        has_new_traceback=False,
        stream=False,
    )
    assert not compute_interactive(
        policy_phase="plan",
        complexity="med",
        design_lexicon=True,
        kill_switch=False,
        user_q="спроектируй модуль",
        has_last_assistant=True,
        has_new_traceback=False,
        stream=True,
    )
    long_q = "x" * 900
    assert not compute_interactive(
        policy_phase="implement",
        complexity="med",
        design_lexicon=False,
        kill_switch=False,
        user_q=long_q,
        has_last_assistant=False,
        has_new_traceback=False,
        stream=True,
    )


def test_custom_panel_rules():
    ready = ["a", "b", "c", "d"]
    one = resolve_custom_panel(["a", "dead"], ready=ready)
    assert one.path_hint == "FAST" and one.models == ["a"] and one.roles == ["A"]

    two = resolve_custom_panel(["a", "b"], ready=ready)
    assert two.models == ["a", "b"] and two.roles == ["A", "B"]
    assert "C" not in two.roles

    # Потолок панели — 3 доера: четвёртый отбрасывается, а не расширяет панель
    three = resolve_custom_panel(["a", "b", "c", "d"], ready=ready)
    assert three.models == ["a", "b", "c"] and three.roles == ["A", "B", "C"]
    assert three.path_hint == "FULL"


def test_cascade_escalate_map():
    ks = cascade_escalate_action(
        kill_switch=True, product_mode="power", complexity="heavy", phase="plan"
    )
    assert ks.action == "stronger_leader" and not ks.allow_full

    simple = cascade_escalate_action(
        kill_switch=False, product_mode="simple", complexity="heavy", phase="debug"
    )
    assert simple.action == "stronger_leader" and not simple.allow_full

    # Power fixed crew: Mini fail → keep (no ladder / no FULL handoff)
    heavy = cascade_escalate_action(
        kill_switch=False, product_mode="power", complexity="heavy", phase="implement"
    )
    assert heavy.action == "keep" and heavy.routed_by == "cascade_fixed_no_escalate"

    med1 = cascade_escalate_action(
        kill_switch=False,
        product_mode="power",
        complexity="med",
        phase="implement",
        stronger_already_tried=False,
    )
    assert med1.action == "keep"
    med2 = cascade_escalate_action(
        kill_switch=False,
        product_mode="custom",
        complexity="med",
        phase="implement",
        stronger_already_tried=True,
    )
    assert med2.action == "full"


def test_leader_failover_ordered():
    chain = leader_failover_chain(product_mode="power")
    assert chain[0] == "claude-opus-4-6"
    nxt = next_leader_failover(chain[0], product_mode="power")
    assert nxt == "gpt-5.4-mini"
    assert next_leader_failover(chain[-1], product_mode="power") is None

    # empty ready → disaster (None)
    assert next_leader_failover("x", product_mode="power", ready=[]) is None


def test_mini_verifier_json_threshold():
    ok = mini_verifier_passed(
        {"good_enough": True, "confidence": 0.9, "reason": "solid"}
    )
    assert ok.passed and not ok.degraded

    low = mini_verifier_passed(
        {"good_enough": True, "confidence": 0.5, "reason": "weak"}
    )
    assert not low.passed

    bad = mini_verifier_passed("not json at all")
    assert bad.degraded and not bad.passed

    fenced = parse_mini_verifier_json(
        '```json\n{"good_enough": true, "confidence": 0.85, "reason": "ok"}\n```'
    )
    assert fenced and fenced["good_enough"] is True


def test_path_to_legacy_stack():
    assert path_to_legacy_stack("FAST") == "fast"
    assert path_to_legacy_stack("CASCADE") == "fast"
    assert path_to_legacy_stack("RACE") == "full"
    assert path_to_legacy_stack("FULL") == "full"


def test_fusion_modules_do_not_import_routers():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app" / "fusion"
    for py in root.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.routers"), py.name
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app.routers"), py.name
