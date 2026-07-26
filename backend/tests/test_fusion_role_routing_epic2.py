"""Role Routing Epic 2 — Log Analyst, Unified Gate, Escalate≤2, Soft-Stop, kill≠v1."""

from __future__ import annotations

import asyncio
import os

from app.fusion.log_analyst import (
    brief_log_input,
    has_error_trigger,
    parse_log_analyst_json,
    pick_log_model,
    run_log_analyst,
    should_run_log_analyst,
)
from app.fusion.panel import pick_mini_model_from_panel, soft_stop_pick_by_power
from app.fusion.pipeline import pick_pipeline
from app.fusion.roles import resolve_roles
from app.fusion.verify import (
    SOFT_STOP_RED_LINE,
    GateSignals,
    append_soft_stop_red_line,
    compute_unified_gate,
    run_trusted_verify_loop,
)


def test_parse_log_analyst_json_ok():
    r = parse_log_analyst_json(
        '{"critical": true, "summary": "boom", "fix_hint": "fix x", "confidence": 0.9}'
    )
    assert r is not None
    assert r["critical"] is True
    assert r["fix_hint"] == "fix x"


def test_parse_log_analyst_missing_critical():
    assert parse_log_analyst_json('{"summary": "x", "fix_hint": "", "confidence": 0.5}') is None


def test_should_run_requires_model_and_trigger():
    assert should_run_log_analyst(stack_has_log_model=True, has_error_trigger=True)
    assert not should_run_log_analyst(stack_has_log_model=False, has_error_trigger=True)
    assert not should_run_log_analyst(stack_has_log_model=True, has_error_trigger=False)


def test_custom_without_deepseek_skips_log_model():
    assert pick_log_model(["claude-opus-4-8", "gemini-3.1-pro"]) is None
    assert pick_log_model(["deepseek-v4-flash", "gemini-3-pro"]) == "deepseek-v4-flash"


def test_has_error_trigger_traceback():
    assert has_error_trigger(user_q="Traceback (most recent call last):\nValueError")
    assert not has_error_trigger(user_q="поменяй цвет кнопки")


def test_log_analyst_heuristic_critical():
    os.environ["ZEUS_FUSION_LOG_HEURISTIC"] = "1"
    try:
        r = asyncio.run(
            run_log_analyst(
                goal="fix crash",
                log_tail="Traceback (most recent call last):\nException: x",
                model_id="deepseek-v4-flash",
            )
        )
        assert not r.skipped
        assert r.report is not None
        assert r.report["critical"] is True
    finally:
        os.environ.pop("ZEUS_FUSION_LOG_HEURISTIC", None)


def test_log_analyst_skip_no_model():
    r = asyncio.run(
        run_log_analyst(
            goal="Traceback",
            log_tail="Exception: x",
            model_id=None,
        )
    )
    assert r.skipped
    assert r.reason == "no_log_model"


def test_gate_mini_fail_red():
    g, reasons = compute_unified_gate(GateSignals(mini_passed=False, log_report="N/A"))
    assert g == "RED"
    assert "mini_fail" in reasons


def test_gate_log_critical_red():
    g, reasons = compute_unified_gate(
        GateSignals(
            mini_passed=True,
            log_report={
                "critical": True,
                "summary": "x",
                "fix_hint": "y",
                "confidence": 0.9,
            },
        )
    )
    assert g == "RED"
    assert "log_critical" in reasons


def test_gate_log_na_not_red():
    g, reasons = compute_unified_gate(
        GateSignals(mini_passed=True, log_report="N/A")
    )
    assert g == "GREEN"
    assert reasons == ["mini_pass"]


def test_gate_log_called_but_bad_red():
    g, reasons = compute_unified_gate(
        GateSignals(mini_passed=True, log_report=None)
    )
    assert g == "RED"
    assert "log_parse_degraded" in reasons


def test_gate_lint_alone_not_critical():
    g, reasons = compute_unified_gate(
        GateSignals(mini_passed=True, log_report="N/A", lint_failed=True)
    )
    assert g == "GREEN"


def test_gate_tests_na_ignored():
    g, reasons = compute_unified_gate(
        GateSignals(
            mini_passed=True,
            log_report="N/A",
            tests_failed=None,
            build_failed=None,
        )
    )
    assert g == "GREEN"


def test_gate_doer_self_score_cannot_force_green():
    g, reasons = compute_unified_gate(
        GateSignals(
            mini_passed=False,
            log_report="N/A",
            doer_self_score=0.99,
        )
    )
    assert g == "RED"


def test_soft_stop_red_line():
    out = append_soft_stop_red_line("тело ответа")
    assert SOFT_STOP_RED_LINE in out
    assert "тело ответа" in out


def test_trusted_verify_soft_stop_after_escalate_cap():
    os.environ["ZEUS_FUSION_LOG_HEURISTIC"] = "1"
    os.environ["ZEUS_FUSION_MINI_HEURISTIC"] = "1"
    os.environ["ZEUS_FUSION_JUDGE_FIX_HEURISTIC"] = "1"
    try:
        # Answer contains traceback → mini heuristic fails; log critical
        r = asyncio.run(
            run_trusted_verify_loop(
                answer="Traceback (most recent call last):\nError",
                user_q="fix this Traceback Exception please",
                panel=["deepseek-v4-flash", "claude-opus-4-8"],
                models_by_role={
                    "log_analyst": "deepseek-v4-flash",
                    "judge_fix": "claude-opus-4-8",
                    "mini_verifier": "deepseek-v4-flash",
                },
                curator_model="claude-opus-4-8",
                early_exit=None,
                routed_by="policy_cascade",
                branches=[],
                allow_green_without_mini=False,
                max_escalate=2,
                candidate_answers=[
                    ("deepseek-v4-flash", "weak answer traceback"),
                    ("claude-opus-4-8", "stronger post-merge body"),
                ],
            )
        )
        assert r.gate == "RED"
        assert r.soft_stop is True
        assert r.escalate_count <= 2
        assert r.escalate_count == 2
        assert SOFT_STOP_RED_LINE in r.answer
        assert "stronger post-merge body" in r.answer or "claude" in (r.soft_stop_model or "")
        assert r.soft_stop_model == "claude-opus-4-8"
        roles = {getattr(b, "role", None) for b in r.branches}
        assert "log_analyst" in roles
        assert "judge_fix" in roles
    finally:
        for k in (
            "ZEUS_FUSION_LOG_HEURISTIC",
            "ZEUS_FUSION_MINI_HEURISTIC",
            "ZEUS_FUSION_JUDGE_FIX_HEURISTIC",
        ):
            os.environ.pop(k, None)


def test_trusted_verify_custom_no_deepseek_log_na():
    os.environ["ZEUS_FUSION_MINI_HEURISTIC"] = "1"
    try:
        r = asyncio.run(
            run_trusted_verify_loop(
                answer="кнопка теперь синяя, всё ок",
                user_q="поменяй цвет кнопки на синий",
                panel=["claude-haiku-4-5", "gemini-3-pro"],
                models_by_role={"doer_logic": "claude-haiku-4-5"},
                curator_model="gemini-3-pro",
                early_exit="mini_pass",
                routed_by="policy_cascade_mini_pass",
                allow_green_without_mini=False,
                max_escalate=2,
            )
        )
        assert r.log_report == "N/A"
        assert r.gate == "GREEN"
        assert r.soft_stop is False
        assert r.escalate_count == 0
    finally:
        os.environ.pop("ZEUS_FUSION_MINI_HEURISTIC", None)


def test_kill_switch_never_pipeline_v1():
    rr = resolve_roles(product_mode="power", task_kind="architecture")
    assert rr.has_strong
    d = pick_pipeline(
        size="large",
        second_signal=True,
        product_mode="power",
        kill_switch=True,
        roles=rr,
    )
    assert d.pipeline != "v1"
    assert d.pipeline == "small"


def test_kill_switch_blocks_v1_even_with_forced_false():
    rr = resolve_roles(product_mode="custom", task_kind="architecture", custom_models=[
        "claude-opus-4-8",
        "deepseek-v4-pro",
        "gemini-3.1-pro",
    ])
    d = pick_pipeline(
        size="large",
        second_signal=True,
        product_mode="custom",
        kill_switch=True,
        roles=rr,
        forced_path=False,
    )
    assert d.pipeline == "small"
    assert d.serving_path_clamp in ("FAST", "CASCADE", None) or d.pipeline == "small"


def test_soft_stop_prefers_post_merge_over_raw_live_power():
    """AD-25: when outcome answer exists, do not pick raw pre-merge doer text."""
    os.environ["ZEUS_FUSION_MINI_HEURISTIC"] = "1"
    os.environ["ZEUS_FUSION_JUDGE_FIX_HEURISTIC"] = "1"
    try:
        r = asyncio.run(
            run_trusted_verify_loop(
                answer="merged curator answer body that is solid enough",
                user_q="поменяй цвет",  # no error trigger
                panel=["deepseek-v4-flash", "claude-opus-4-8"],
                models_by_role={"mini_verifier": "deepseek-v4-flash"},
                curator_model="deepseek-v4-flash",
                early_exit=None,
                routed_by="policy_cascade",
                # Force RED via soft_stop_already then pick among candidates
                soft_stop_already=True,
                allow_green_without_mini=False,
                max_escalate=0,
                candidate_answers=[
                    ("claude-opus-4-8", "RAW PREMERGE DOER CHUNK"),
                    ("deepseek-v4-flash", "merged curator answer body that is solid enough"),
                ],
            )
        )
        assert r.soft_stop is True
        assert "RAW PREMERGE" not in r.answer
        assert "merged curator answer" in r.answer
    finally:
        os.environ.pop("ZEUS_FUSION_MINI_HEURISTIC", None)
        os.environ.pop("ZEUS_FUSION_JUDGE_FIX_HEURISTIC", None)


def test_brief_log_input_caps_nfr2():
    g, tail, files = brief_log_input(
        goal="x" * 5000,
        log_tail="y" * 10000,
        files=[f"f{i}.py" for i in range(20)],
    )
    assert len(g) <= 800
    assert len(tail) <= 3500
    assert len(files) <= 8


def test_pick_mini_model_stays_in_custom_stack():
    mid = pick_mini_model_from_panel(["claude-haiku-4-5", "gemini-3-pro"])
    assert mid in {"claude-haiku-4-5", "gemini-3-pro"}
    assert "deepseek" not in (mid or "")


def test_soft_stop_pick_by_power_prefers_stronger_model():
    from app.fusion.panel import LiveBranch

    weak = LiveBranch(
        model_id="deepseek-v4-flash",
        role="cheap",
        text="weak body",
        ok=True,
        billable_state="completed",
        verifier_confidence=0.99,
    )
    strong = LiveBranch(
        model_id="claude-opus-4-8",
        role="strong",
        text="strong body",
        ok=True,
        billable_state="completed",
        verifier_confidence=0.1,
    )
    pick = soft_stop_pick_by_power([weak, strong], leader_id="deepseek-v4-flash")
    assert pick is not None
    assert pick.model_id == "claude-opus-4-8"


def test_log_rearm_from_na_when_answer_gains_error():
    """If first log was N/A but judge_fix leaves error text — re-arm Log (AD-27)."""
    os.environ["ZEUS_FUSION_LOG_HEURISTIC"] = "1"
    os.environ["ZEUS_FUSION_MINI_HEURISTIC"] = "1"
    os.environ["ZEUS_FUSION_JUDGE_FIX_HEURISTIC"] = "1"

    async def _mini_always_fail(*, answer: str = "", user_q: str = "", **_k):
        from app.fusion.verify import MiniVerifyResult

        return MiniVerifyResult(
            good_enough=False, confidence=0.1, reason="fail", passed=False
        )

    try:
        r = asyncio.run(
            run_trusted_verify_loop(
                answer="ok short",  # no error → log N/A initially if no trigger in q
                user_q="сделай фикс",  # no traceback
                panel=["deepseek-v4-flash", "claude-opus-4-8"],
                models_by_role={
                    "log_analyst": "deepseek-v4-flash",
                    "judge_fix": "claude-opus-4-8",
                    "mini_verifier": "deepseek-v4-flash",
                },
                curator_model="claude-opus-4-8",
                allow_green_without_mini=False,
                max_escalate=1,
                mini_verify_fn=_mini_always_fail,
            )
        )
        # mini fail → escalate; judge_fix heuristic keeps/adds text; escalate≤1
        assert r.escalate_count <= 1
        assert r.gate == "RED"
    finally:
        for k in (
            "ZEUS_FUSION_LOG_HEURISTIC",
            "ZEUS_FUSION_MINI_HEURISTIC",
            "ZEUS_FUSION_JUDGE_FIX_HEURISTIC",
        ):
            os.environ.pop(k, None)


def test_escalate_can_clear_log_critical_when_answer_fixed():
    os.environ["ZEUS_FUSION_LOG_HEURISTIC"] = "1"
    os.environ["ZEUS_FUSION_MINI_HEURISTIC"] = "1"
    os.environ["ZEUS_FUSION_JUDGE_FIX_HEURISTIC"] = "1"

    async def _mini_pass(*, answer: str = "", user_q: str = "", model: str | None = None, **_k):
        from app.fusion.verify import MiniVerifyResult

        ok = "traceback" not in (answer or "").lower() and len(answer or "") > 20
        return MiniVerifyResult(
            good_enough=ok, confidence=0.9 if ok else 0.2, reason="t", passed=ok
        )

    try:
        r = asyncio.run(
            run_trusted_verify_loop(
                answer="Traceback (most recent call last):\nError",
                user_q="please fix",
                panel=["deepseek-v4-flash", "claude-opus-4-8"],
                models_by_role={
                    "log_analyst": "deepseek-v4-flash",
                    "judge_fix": "claude-opus-4-8",
                    "mini_verifier": "deepseek-v4-flash",
                },
                curator_model="claude-opus-4-8",
                allow_green_without_mini=False,
                max_escalate=2,
                mini_verify_fn=_mini_pass,
            )
        )
        # judge_fix heuristic appends text without traceback → re-log + mini can GREEN
        # or Soft-Stop; must not be stuck with escalate_count>2
        assert r.escalate_count <= 2
        if r.gate == "GREEN":
            assert r.soft_stop is False
            assert not (isinstance(r.log_report, dict) and r.log_report.get("critical"))
    finally:
        for k in (
            "ZEUS_FUSION_LOG_HEURISTIC",
            "ZEUS_FUSION_MINI_HEURISTIC",
            "ZEUS_FUSION_JUDGE_FIX_HEURISTIC",
        ):
            os.environ.pop(k, None)
