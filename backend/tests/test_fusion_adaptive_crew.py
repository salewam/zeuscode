from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from app.fusion import panel
from app.fusion.crew import CrewSession, TurnKind, merge_machine_evidence, select_crew
from app.fusion.pipeline import apply_small_path_clamps, pick_pipeline
from app.fusion.research_crew import should_run_research_crew
from app.fusion.roles import resolve_roles
from app.fusion._monolith import iter_fusion
from app.fusion.verify import (
    GateSignals,
    collect_tool_evidence,
    compute_unified_gate,
    derive_test_command,
    conventional_test_commands,
    is_submit_tool_call,
    pre_submit_gate,
    machine_signals_from_client,
    plan_test_command,
    run_trusted_verify_loop,
    validate_test_command,
)
from app.fusion.policy import detect_adaptive_signals
from app.routers.chat import (
    _automatic_tool_session_id,
    _namespace_session_id,
    _tool_call_alias_session_id,
)
from app.fusion.pipeline_v1 import execute_pipeline_v1
from app.fusion import log_analyst
from app.fusion.log_analyst import LogAnalystResult
from app.fusion.session import merge_sticky_phase_meta


MODELS = {
    "architect": "claude-opus-4-6",
    "doer_logic": "gpt-5.4",
    "log_analyst": "deepseek-v4-pro",
    "test_author": "grok-4.5",
}


def test_approved_role_topology_uses_distinct_specialists():
    resolved = resolve_roles(product_mode="power", task_kind="code")
    assert resolved.models_by_role["architect"] == "claude-opus-4-6"
    assert resolved.models_by_role["doer_logic"] == "gpt-5.4"
    assert resolved.models_by_role["test_author"] == "grok-4.5"
    assert resolved.models_by_role["log_analyst"] == "deepseek-v4-pro"


def test_unhealthy_grok_45_uses_test_role_fallback():
    resolved = resolve_roles(
        product_mode="power",
        task_kind="code",
        unhealthy={"grok-4.5"},
    )
    assert resolved.models_by_role["test_author"] == "grok-4.3"


def test_mini_swe_bash_completion_marker_is_a_submit_call():
    assert is_submit_tool_call(
        {
            "id": "submit-via-bash",
            "type": "function",
            "function": {
                "name": "bash",
                "arguments": (
                    '{"command":"echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT '
                    '&& cat patch.txt"}'
                ),
            },
        }
    )


def test_malformed_bash_arguments_cannot_hide_submit_marker():
    assert is_submit_tool_call(
        {
            "type": "function",
            "function": {
                "name": "bash",
                "arguments": (
                    '{"command":"echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT'
                ),
            },
        }
    )


def test_wrapped_empty_diff_is_not_nonempty_evidence():
    evidence = collect_tool_evidence(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "empty-diff",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command":"git diff"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "empty-diff",
                "content": (
                    "<returncode>0</returncode><output></output>"
                ),
            },
        ]
    )
    assert evidence["diff_nonempty"] is False


def test_echo_or_masked_pytest_cannot_create_green_evidence():
    prior = {
        "diff_nonempty": True,
        "diff_seq": 1,
        "test_plan_command": "pytest -q tests/test_target.py",
    }
    echoed = collect_tool_evidence(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "echo-test",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": (
                                '{"command":"echo pytest -q tests/test_target.py"}'
                            ),
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "echo-test",
                "content": "<returncode>0</returncode><output></output>",
            },
        ],
        prior,
    )
    assert echoed.get("test_green") is not True

    masked = collect_tool_evidence(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "masked-test",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": (
                                '{"command":"pytest -q tests/test_target.py '
                                '>/dev/null || true"}'
                            ),
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "masked-test",
                "content": "<returncode>0</returncode><output></output>",
            },
        ],
        prior,
    )
    assert masked["test_green"] is False
    assert pre_submit_gate(masked)[0] == "RED"


def test_grok_test_command_must_be_a_single_direct_test():
    assert (
        validate_test_command("pytest -q tests/test_target.py")
        == "pytest -q tests/test_target.py"
    )
    assert validate_test_command(
        "pytest -q tests/test_target.py; rm -rf /"
    ) == ""
    assert validate_test_command(
        "pytest -q tests/test_target.py >/dev/null || true"
    ) == ""
    assert validate_test_command("sudo pytest -q tests/test_target.py") == ""
    assert validate_test_command(
        "pytest -q tests/test_target.py --basetemp=/tmp/zeus"
    ) == ""
    assert validate_test_command(
        "pytest -q tests/test_target.py --baset=/tmp/zeus"
    ) == ""


def test_unknown_successful_shell_command_invalidates_green_freshness():
    prior = {
        "diff_nonempty": True,
        "diff_seq": 1,
        "diff_fingerprint": "before",
        "test_plan_command": "pytest -q tests/test_target.py",
        "test_green": True,
        "test_relevant": True,
        "test_seq": 2,
        "fresh_green_test": True,
        "tool_event_seq": 2,
    }
    evidence = collect_tool_evidence(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "scripted-write",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": (
                                '{"command":"python -c '
                                '\\"open(\\\\\\"module.py\\\\\\",\\\\\\"w\\\\\\").write(\\\\\\"x=1\\\\\\")\\""}'
                            ),
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "scripted-write",
                "content": "<returncode>0</returncode><output></output>",
            },
        ],
        prior,
    )
    assert evidence["diff_seq"] > prior["test_seq"]
    assert evidence["fresh_green_test"] is False


def test_malformed_persisted_event_sequences_are_sanitized():
    evidence = collect_tool_evidence(
        [], {"tool_event_seq": "not-a-number", "diff_seq": {"bad": True}}
    )
    assert evidence["tool_event_seq"] == 0
    assert evidence["fresh_green_test"] is False


def test_astropy_11693_replay_requires_test_after_latest_diff():
    prior = collect_tool_evidence(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "diff-astropy",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command":"git diff"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "diff-astropy",
                "content": (
                    "<returncode>0</returncode>\n"
                    "diff --git a/astropy/wcs/wcsapi/fitswcs.py "
                    "b/astropy/wcs/wcsapi/fitswcs.py\n"
                    "--- a/astropy/wcs/wcsapi/fitswcs.py\n"
                    "+++ b/astropy/wcs/wcsapi/fitswcs.py"
                ),
            },
        ]
    )
    assert pre_submit_gate(prior) == (
        "RED",
        ["relevant_test_not_green"],
    )
    prior["test_plan_command"] = (
        "pytest -q astropy/wcs/wcsapi/tests/test_fitswcs.py"
    )
    tested = collect_tool_evidence(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "test-astropy",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": (
                                '{"command":"pytest -q '
                                'astropy/wcs/wcsapi/tests/test_fitswcs.py"}'
                            ),
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "test-astropy",
                "content": "<returncode>0</returncode>\n1 passed",
            },
        ],
        prior,
    )
    assert tested["fresh_green_test"] is True
    assert pre_submit_gate(tested) == ("GREEN", ["fresh_green_test"])
    edited_again = collect_tool_evidence(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "edit-after-test",
                        "type": "function",
                        "function": {
                            "name": "edit",
                            "arguments": '{"path":"astropy/wcs/wcsapi/fitswcs.py"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "edit-after-test",
                "content": "<returncode>0</returncode>\nDone",
            },
        ],
        tested,
    )
    assert pre_submit_gate(edited_again) == (
        "RED",
        ["diff_empty", "green_test_stale_after_diff"],
    )


def test_single_crew_topology_does_not_change_with_regex_labels():
    simple, _ = select_crew(
        user_q="Rename the label",
        models_by_role=MODELS,
    )
    normal, _ = select_crew(
        user_q="Fix this Python traceback and update the handler",
        models_by_role=MODELS,
    )
    risky, _ = select_crew(
        user_q="Migrate the auth database schema and public API",
        models_by_role=MODELS,
    )
    assert all(x.crew_size == 4 for x in (simple, normal, risky))
    assert all(x.active_roles == ["leader", "doer"] for x in (simple, normal, risky))
    assert all(x.tier == "compact" for x in (simple, normal, risky))
    assert all(x.reason for x in (simple, normal, risky))


def test_bootstrap_budgets_match_selected_topology():
    standard, _ = select_crew(
        user_q="Fix this Python traceback and update the handler",
        models_by_role=MODELS,
    )
    specialist, _ = select_crew(
        user_q="Migrate the auth database schema and public API",
        zeus={"serious": True},
        models_by_role=MODELS,
    )
    compact_tool, _ = select_crew(
        user_q="Rename label",
        models_by_role=MODELS,
        tool_enabled=True,
    )
    specialist_tool, _ = select_crew(
        user_q="Migrate the auth database schema and public API",
        zeus={"serious": True},
        models_by_role=MODELS,
        tool_enabled=True,
    )
    assert standard.max_internal_branches == 2
    assert specialist.max_internal_branches == 4
    assert compact_tool.max_internal_branches == 2
    assert specialist_tool.max_internal_branches == 4


def test_crew_state_roundtrip_and_machine_evidence_merge():
    _, state = select_crew(
        user_q="Fix this traceback",
        models_by_role=MODELS,
    )
    state.machine_evidence = merge_machine_evidence(
        state.machine_evidence,
        {"exec": {"tests_ok": False, "compile_ok": True}},
    )
    restored = CrewSession.from_dict(state.to_dict())
    assert restored.crew_size == 4
    assert restored.machine_evidence["tests_failed"] is True
    assert restored.machine_evidence["compile_failed"] is False
    string_evidence = merge_machine_evidence(
        {},
        {"exec": {"tests_ok": "false", "build_ok": "true"}},
    )
    assert string_evidence["tests_failed"] is True
    assert string_evidence["build_failed"] is False


def test_exit_code_machine_signal_and_red_gate():
    assert machine_signals_from_client({"exec": {"exit_code": 0}})[
        "command_exit_nonzero"
    ] is False
    assert machine_signals_from_client({"exec": {"exit_code": "0"}})[
        "command_exit_nonzero"
    ] is False
    failed = machine_signals_from_client({"exec": {"exit_code": "2"}})
    assert failed["command_exit_nonzero"] is True
    assert machine_signals_from_client({"exec": {"exit_code": "bad"}})[
        "command_exit_nonzero"
    ] is None
    gate, reasons = compute_unified_gate(
        GateSignals(mini_passed=True, **failed)
    )
    assert gate == "RED"
    assert "command_exit_nonzero" in reasons


def test_sticky_tool_turn_keeps_crew_and_uses_incremental_pipeline():
    prior = CrewSession(
        crew_size=3,
        tier="standard",
        roles=["leader", "doer", "analyst"],
        role_assignments={
            "leader": MODELS["architect"],
            "doer": MODELS["doer_logic"],
            "analyst": MODELS["log_analyst"],
        },
    )
    decision, _ = select_crew(
        user_q="tool output",
        messages=[
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        ],
        prior=prior,
        models_by_role=MODELS,
    )
    roles = resolve_roles(product_mode="power", task_kind="code")
    pipeline = pick_pipeline(
        size="small",
        second_signal=False,
        product_mode="power",
        kill_switch=False,
        roles=roles,
        crew=decision,
    )
    assert decision.turn_kind is TurnKind.TOOL_LOOP
    assert decision.crew_size == 4
    assert decision.active_roles == ["doer"]
    assert pipeline.pipeline == "incremental"
    assert pipeline.meta["max_internal_branches"] <= 3


def test_new_user_task_after_old_tool_history_bootstraps_again():
    signals = detect_adaptive_signals(
        user_q="Now explain the architecture",
        messages=[
            {"role": "user", "content": "Read it"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "body"},
            {"role": "user", "content": "Now explain the architecture"},
        ],
    )
    assert signals["turn_kind"] == "bootstrap"
    stale_exec = detect_adaptive_signals(
        user_q="Build a new export screen",
        messages=[{"role": "user", "content": "Build a new export screen"}],
        zeus={"exec": {"tests_ok": "true"}},
    )
    assert stale_exec["turn_kind"] == "bootstrap"
    failed_exec = detect_adaptive_signals(
        user_q="The test failed with assertion error",
        messages=[{"role": "user", "content": "The test failed with assertion error"}],
        zeus={"exec": {"tests_ok": "false"}},
    )
    assert failed_exec["turn_kind"] == "exec_feedback"


def test_swe_test_author_boilerplate_does_not_trigger_security_tier():
    decision, _ = select_crew(
        user_q=(
            "You are a test author fixing astropy__astropy-11693. "
            "Inspect the implementation and add a regression test."
        ),
        models_by_role=MODELS,
        available_models=list(MODELS.values()),
    )
    assert decision.tier != "specialist_security"
    assert decision.crew_size == 4


def test_per_turn_budget_resets_across_49_turns():
    state = CrewSession(
        crew_size=3,
        tier="standard",
        roles=["leader", "doer", "analyst"],
        role_assignments={
            "leader": MODELS["architect"],
            "doer": MODELS["doer_logic"],
            "analyst": MODELS["log_analyst"],
        },
    )
    for turn in range(49):
        decision, state = select_crew(
            user_q=f"result {turn}",
            messages=[
                {"role": "user", "content": "Run it"},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
                {"role": "tool", "tool_call_id": "c1", "content": "ok"},
            ],
            prior=state,
            models_by_role=MODELS,
        )
        assert decision.max_internal_branches == 3
        assert decision.remaining_internal_branches == 3
        assert state.remaining_internal_branches == 3
        state.llm_calls_session += 1
        state.total_internal_branches += 1
        state = CrewSession.from_dict(state.to_dict())
    assert state.llm_calls_session == 49
    assert state.total_internal_branches == 49


def test_malformed_persisted_state_uses_safe_defaults():
    state = CrewSession.from_dict(
        {
            "crew_size": "not-a-number",
            "max_internal_branches": [],
            "remaining_internal_branches": {},
            "role_assignments": [],
        }
    )
    assert state.crew_size == 4
    assert state.max_internal_branches == 2
    assert state.remaining_internal_branches == 2
    assert state.degraded is True


def test_auto_tool_session_id_is_stable_and_separates_tasks():
    first = _automatic_tool_session_id(
        api_key_identity="hashed-key-1",
        messages=[{"role": "user", "content": "Fix parser bug"}],
    )
    continuation = _automatic_tool_session_id(
        api_key_identity="hashed-key-1",
        messages=[
            {"role": "user", "content": "Fix parser bug"},
            {"role": "assistant", "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "content": "result"},
        ],
    )
    other = _automatic_tool_session_id(
        api_key_identity="hashed-key-1",
        messages=[{"role": "user", "content": "Fix billing bug"}],
    )
    assert continuation == _tool_call_alias_session_id("hashed-key-1", "c1")
    assert first != continuation
    assert first != other
    assert first and len(first) <= 128
    assert "Fix parser bug" not in first


def test_tool_call_aliases_isolate_identical_concurrent_bootstraps():
    first = _tool_call_alias_session_id("42", "call-a")
    second = _tool_call_alias_session_id("42", "call-b")
    assert first != second
    assert _automatic_tool_session_id(
        api_key_identity="42",
        messages=[
            {"role": "user", "content": "same task"},
            {"role": "assistant", "tool_calls": [{"id": "call-a"}]},
            {"role": "tool", "tool_call_id": "call-a", "content": "A"},
        ],
    ) == first
    assert _namespace_session_id("42", "shared") != _namespace_session_id("43", "shared")
    fresh_goal = _automatic_tool_session_id(
        api_key_identity="42",
        messages=[
            {"role": "user", "content": "old task"},
            {"role": "assistant", "tool_calls": [{"id": "call-a"}]},
            {"role": "tool", "tool_call_id": "call-a", "content": "done"},
            {"role": "user", "content": "new unrelated goal"},
        ],
    )
    assert fresh_goal not in (first, second)
    parallel = _automatic_tool_session_id(
        api_key_identity="42",
        messages=[
            {"role": "user", "content": "same task"},
            {
                "role": "assistant",
                "tool_calls": [{"id": "call-a"}, {"id": "call-b"}],
            },
            {"role": "tool", "tool_call_id": "call-b", "content": "B"},
        ],
    )
    assert parallel == first


def test_tool_format_retry_keeps_the_existing_crew_session():
    session_id = _automatic_tool_session_id(
        api_key_identity="42",
        messages=[
            {"role": "user", "content": "Fix parser bug"},
            {"role": "assistant", "tool_calls": [{"id": "call-a"}]},
            {"role": "tool", "tool_call_id": "call-a", "content": "result"},
            {"role": "assistant", "content": "I will inspect the next file."},
            {
                "role": "user",
                "content": (
                    "Tool call error:\n\n<error>No tool calls found in the response. "
                    "Every response MUST include at least one tool call.</error>"
                ),
            },
        ],
    )
    assert session_id == _tool_call_alias_session_id("42", "call-a")


def test_compact_red_expands_and_missing_continuation_recovers_bootstrap():
    compact = CrewSession(
        crew_size=2,
        roles=["leader", "doer"],
        role_assignments={
            "leader": MODELS["architect"],
            "doer": MODELS["doer_logic"],
        },
    )
    red, _ = select_crew(
        user_q="failed",
        messages=[{"role": "tool", "content": "1 failed"}],
        zeus={"exec": {"tests_ok": "false"}},
        prior=compact,
        models_by_role=MODELS,
        available_models=list(MODELS.values()),
    )
    recovered, _ = select_crew(
        user_q="result",
        messages=[{"role": "function", "content": "output"}],
        models_by_role=MODELS,
        available_models=list(MODELS.values()),
    )
    assert red.crew_size == 4
    assert red.active_roles == ["analyst", "doer"]
    assert recovered.turn_kind is TurnKind.BOOTSTRAP
    assert recovered.reason == "recovered_tool_bootstrap"
    recovered_pipeline = pick_pipeline(
        size="small",
        second_signal=False,
        product_mode="power",
        kill_switch=False,
        roles=resolve_roles(product_mode="power", task_kind="code"),
        crew=recovered,
        tool_enabled=True,
    )
    assert recovered_pipeline.pipeline == "tool_bootstrap"


def test_fresh_healthy_assignments_replace_stale_and_report_distinctness():
    prior = CrewSession(
        crew_size=3,
        roles=["leader", "doer", "analyst"],
        role_assignments={
            "leader": "dead-opus",
            "doer": "dead-gpt",
            "analyst": "dead-deepseek",
        },
    )
    decision, _ = select_crew(
        user_q="continue",
        messages=[{"role": "tool", "content": "ok"}],
        prior=prior,
        models_by_role=MODELS,
        unhealthy={"dead-opus", "dead-gpt", "dead-deepseek"},
        available_models=list(MODELS.values()),
    )
    assert "dead-opus" not in decision.role_assignments.values()
    assert decision.role_assignments["leader"] == MODELS["architect"]
    assert decision.distinct_model_count == 4
    assert decision.degraded is False


def test_malformed_collections_and_soft_cap_stop_safely():
    malformed = CrewSession.from_dict(
        {"roles": "leader", "machine_evidence": ["bad"], "plan_digest": "x" * 9000}
    )
    assert malformed.roles == ["leader", "doer", "analyst", "verifier"]
    assert malformed.machine_evidence == {}
    assert len(malformed.plan_digest) == 6000
    malformed.total_internal_branches = malformed.session_soft_cap
    decision, _ = select_crew(
        user_q="continue",
        messages=[{"role": "tool", "content": "ok"}],
        prior=malformed,
        models_by_role=MODELS,
        available_models=list(MODELS.values()),
    )
    assert decision.reason == "session_soft_cap"
    assert decision.max_internal_branches == 0


def test_persisted_soft_cap_is_ignored(monkeypatch):
    monkeypatch.setenv("ZEUS_CREW_SESSION_SOFT_CAP", "700")
    restored = CrewSession.from_dict(
        {"session_soft_cap": 64, "llm_calls_session": 12, "total_internal_branches": 13}
    )
    assert restored.session_soft_cap == 700
    assert restored.llm_calls_session == 12
    assert restored.total_internal_branches == 13


def test_new_bootstrap_clears_stale_task_artifacts():
    state = CrewSession(turn_kind=TurnKind.BOOTSTRAP).to_dict()
    merged = merge_sticky_phase_meta(
        {
            "clarify": {"question": "old"},
            "plan_artifact": {"content": "old plan"},
            "project_memory": {"keep": True},
        },
        {"crew": state},
    )
    assert "clarify" not in merged
    assert "plan_artifact" not in merged
    assert merged["project_memory"] == {"keep": True}


def test_atomic_phase_merge_counts_same_prior_responses():
    current = CrewSession(
        turn_kind=TurnKind.TOOL_LOOP,
        llm_calls_session=10,
        total_internal_branches=10,
        turn_count=5,
        plan_digest="existing plan",
        machine_evidence={"tests_failed": True},
    )
    incoming = CrewSession(
        turn_kind=TurnKind.TOOL_LOOP,
        llm_calls_session=11,
        total_internal_branches=11,
        turn_count=6,
        plan_digest="",
        machine_evidence={"compile_failed": False},
    )
    first = merge_sticky_phase_meta(
        {"crew": current.to_dict(), "project_memory": {"keep": True}},
        {"crew": incoming.to_dict()},
        spent_internal_branches=1,
    )
    second = merge_sticky_phase_meta(
        first,
        {"crew": incoming.to_dict()},
        spent_internal_branches=1,
    )
    crew = CrewSession.from_dict(second["crew"])
    assert crew.llm_calls_session == 12
    assert crew.total_internal_branches == 12
    assert crew.turn_count == 7
    assert crew.machine_evidence == {
        "tests_failed": True,
        "compile_failed": False,
    }
    assert crew.plan_digest == "existing plan"
    assert second["project_memory"] == {"keep": True}


def test_apply_clamp_never_inflates_selected_doer_panel():
    roles = resolve_roles(product_mode="power", task_kind="code")
    decision = pick_pipeline(
        size="small",
        second_signal=True,
        product_mode="power",
        kill_switch=False,
        roles=roles,
    )
    decision.doer_panel = ["gpt-5.4-mini"]
    decision.execute_leader = "claude-opus-4-6"
    _, panel_out, leader_out = apply_small_path_clamps(
        serving_path="FULL",
        panel=["gpt-5.4-mini"],
        leader="claude-opus-4-6",
        decision=decision,
    )
    assert panel_out == ["gpt-5.4-mini"]
    assert leader_out == "gpt-5.4-mini"


def test_string_exec_false_selects_analyst_feedback():
    prior = CrewSession(
        crew_size=3,
        tier="standard",
        roles=["leader", "doer", "analyst"],
        role_assignments={
            "leader": MODELS["architect"],
            "doer": MODELS["doer_logic"],
            "analyst": MODELS["log_analyst"],
        },
    )
    decision, state = select_crew(
        user_q="tests failed",
        messages=[
            {"role": "user", "content": "Fix it"},
            {"role": "tool", "content": "1 failed"},
        ],
        zeus={"exec": {"tests_ok": "false"}},
        prior=prior,
        models_by_role=MODELS,
    )
    assert decision.turn_kind is TurnKind.EXEC_FEEDBACK
    assert decision.active_roles == ["analyst", "doer"]
    assert state.machine_evidence["tests_failed"] is True


def test_research_is_off_for_code_without_explicit_network_signal(monkeypatch):
    monkeypatch.setenv("ZEUS_FUSION_RESEARCH", "1")
    assert (
        should_run_research_crew(
            user_q="Fix the failing unit test",
            task_kind="code",
            phase="debug",
            zeus={},
        )
        is False
    )
    assert should_run_research_crew(
        user_q="Check the latest official API docs, then fix this",
        task_kind="code",
        phase="implement",
        zeus={},
    )
    assert not should_run_research_crew(
        user_q="Compare two parser designs using best practices",
        task_kind="code",
        phase="implement",
        zeus={},
    )


def test_tool_bootstrap_leader_plans_once_then_doer_calls_tool(monkeypatch):
    from app.fusion import policy

    leader_calls = 0
    doer_calls = 0

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy path policy/executor must not run")

    async def fake_leader(model, messages, **_kwargs):
        nonlocal leader_calls
        leader_calls += 1
        assert model == MODELS["architect"]
        return {
            "text": json.dumps(
                {
                    "goal": "Fix parser bug",
                    "motivation": "Restore parsing",
                    "scope": ["inspect parser.py", "patch parser"],
                    "test_command": "pytest -q",
                    "done_criteria": ["Focused test is green"],
                    "assignments": {
                        "leader": "Own card",
                        "doer": "Inspect and patch",
                        "analyst": "Fresh errors only",
                        "verifier": "Resolve ambiguous test",
                    },
                }
            ),
            "prompt_tokens": 4,
            "completion_tokens": 5,
            "model_id": model,
        }

    async def fake_hands(**kwargs):
        nonlocal doer_calls
        doer_calls += 1
        assert "inspect parser.py" in kwargs["crew_answer"]
        return {
            "text": "",
            "tool_calls": [
                {
                    "id": "read-1",
                    "type": "function",
                    "function": {"name": "read", "arguments": '{"path":"parser.py"}'},
                }
            ],
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "model_id": MODELS["doer_logic"],
            "ok": True,
        }

    monkeypatch.setattr(panel, "_default_upstream", fake_leader)
    monkeypatch.setattr(panel, "run_hands_doer", fake_hands)
    monkeypatch.setattr(policy, "soft_resolve_for_monolith", forbidden)
    monkeypatch.setattr(panel, "execute_cascade", forbidden)
    monkeypatch.setattr(panel, "execute_race", forbidden)
    monkeypatch.setattr(panel, "execute_full", forbidden)

    async def collect():
        return [
            event
            async for event in iter_fusion(
                messages=[{"role": "user", "content": "Fix the parser bug"}],
                model_id="zeuscode",
                zeus={"path": "RACE", "mode": "fast"},
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "read",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            )
        ]

    events = asyncio.run(collect())
    done = next(event["data"] for event in events if event["kind"] == "done")
    roles = [branch["role"] for branch in done["onestack"]["branches"]]
    assert leader_calls == 1
    assert doer_calls == 1
    assert roles == ["leader", "doer"]
    assert done["onestack"]["active_roles"] == ["leader", "doer"]
    assert done["onestack"]["pipeline"] == "tool_bootstrap"
    assert done["onestack"]["path"] == "CASCADE"
    assert done["choices"][0]["finish_reason"] == "tool_calls"
    state = done["onestack"]["crew_state"]
    assert "inspect parser.py" in state["plan_digest"]
    assert state["llm_calls_session"] == 2
    assert done["onestack"].get("research_ok") is None

    async def continue_task():
        return [
            event
            async for event in iter_fusion(
                messages=[
                    {"role": "user", "content": "Fix the parser bug"},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "read-1",
                                "type": "function",
                                "function": {
                                    "name": "read",
                                    "arguments": '{"path":"parser.py"}',
                                },
                            }
                        ],
                    },
                    {"role": "tool", "tool_call_id": "read-1", "content": "source"},
                ],
                model_id="zeuscode",
                zeus={"crew_state": state},
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "read",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            )
        ]

    continued = asyncio.run(continue_task())
    continued_done = next(
        event["data"] for event in continued if event["kind"] == "done"
    )
    assert leader_calls == 1
    assert doer_calls == 2
    assert [
        branch["role"] for branch in continued_done["onestack"]["branches"]
    ] == ["doer"]
    assert continued_done["onestack"]["crew_state"]["llm_calls_session"] == 3
    assert "inspect parser.py" in continued_done["onestack"]["crew_state"]["plan_digest"]


def test_non_tool_request_uses_task_card_v1_without_legacy_paths(monkeypatch):
    from app.fusion import policy

    calls: list[str] = []

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy path policy/executor must not run")

    async def fake_upstream(model, _messages, **_kwargs):
        calls.append(model)
        if len(calls) == 1:
            return {
                "text": json.dumps(
                    {
                        "goal": "Explain the parser change",
                        "motivation": "Keep the client contract stable",
                        "scope": ["parser.py"],
                        "test_command": "pytest -q tests/test_parser.py",
                        "done_criteria": ["Answer is accurate"],
                        "assignments": {
                            "leader": "Own the card",
                            "doer": "Answer from the card",
                            "analyst": "Fresh failures only",
                            "verifier": "Select tests if ambiguous",
                        },
                    }
                ),
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "model_id": model,
            }
        return {
            "text": "The parser keeps the compatibility contract.",
            "prompt_tokens": 4,
            "completion_tokens": 3,
            "model_id": model,
        }

    monkeypatch.setattr(policy, "soft_resolve_for_monolith", forbidden)
    monkeypatch.setattr(panel, "execute_cascade", forbidden)
    monkeypatch.setattr(panel, "execute_race", forbidden)
    monkeypatch.setattr(panel, "execute_full", forbidden)
    monkeypatch.setattr(panel, "_default_upstream", fake_upstream)

    async def collect():
        return [
            event
            async for event in iter_fusion(
                messages=[{"role": "user", "content": "Explain the parser change"}],
                model_id="zeuscode",
                zeus={"path": "FULL", "policy_path": "RACE", "mode": "fast"},
                show_thinking=False,
            )
        ]

    done = next(
        event["data"] for event in asyncio.run(collect()) if event["kind"] == "done"
    )
    assert len(calls) == 2
    assert done["onestack"]["pipeline"] == "v1"
    assert done["onestack"]["path"] == "CASCADE"
    assert done["onestack"]["internal_llm_branches"] == 2
    assert done["onestack"]["task_card"]["tier"] == "compact"
    assert done["onestack"]["crew_budgets"]["spent_internal_branches"] == 2


def test_kill_switch_is_one_model_emergency_without_legacy_paths(monkeypatch):
    from app.fusion import policy

    calls: list[str] = []

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy path policy/executor must not run")

    async def fake_upstream(model, _messages, **_kwargs):
        calls.append(model)
        return {
            "text": "Emergency response.",
            "prompt_tokens": 2,
            "completion_tokens": 2,
            "model_id": model,
        }

    monkeypatch.setattr(policy, "soft_resolve_for_monolith", forbidden)
    monkeypatch.setattr(panel, "execute_cascade", forbidden)
    monkeypatch.setattr(panel, "execute_race", forbidden)
    monkeypatch.setattr(panel, "execute_full", forbidden)
    monkeypatch.setattr(panel, "_default_upstream", fake_upstream)

    async def collect():
        return [
            event
            async for event in iter_fusion(
                messages=[{"role": "user", "content": "Inspect the failure"}],
                model_id="zeuscode",
                zeus={"kill_switch": True},
                show_thinking=False,
            )
        ]

    done = next(
        event["data"] for event in asyncio.run(collect()) if event["kind"] == "done"
    )
    assert len(calls) == 1
    assert done["onestack"]["pipeline"] == "fallback_single"
    assert done["onestack"]["path"] == "FAST"
    assert done["onestack"]["internal_llm_branches"] == 1


def test_tool_bootstrap_uses_safe_card_fallback_when_opus_fails(monkeypatch):
    leader_attempts = 0

    async def failing_leaders(_model, _messages, **_kwargs):
        nonlocal leader_attempts
        leader_attempts += 1
        raise RuntimeError(f"leader failure {leader_attempts}")

    async def surviving_doer(**kwargs):
        return {
            "text": "Saved plan; retry execution.",
            "tool_calls": [],
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "model_id": kwargs["model_id"],
            "ok": True,
        }

    monkeypatch.setattr(panel, "_default_upstream", failing_leaders)
    monkeypatch.setattr(panel, "run_hands_doer", surviving_doer)

    async def collect():
        return [
            event
            async for event in iter_fusion(
                messages=[
                    {
                        "role": "user",
                        "content": "Migrate auth database schema and public API safely",
                    }
                ],
                model_id="zeuscode",
                zeus={},
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "read",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            )
        ]

    events = asyncio.run(collect())
    done = next(event["data"] for event in events if event["kind"] == "done")
    branches = done["onestack"]["branches"]
    budgets = done["onestack"]["crew_budgets"]
    assert leader_attempts == 1
    assert [branch["role"] for branch in branches] == ["leader", "doer"]
    assert done["onestack"]["task_card_phases"][0]["ok"] is False
    assert done["onestack"]["task_card"]["degraded"] is True
    assert budgets["spent_internal_branches"] == 2
    assert budgets["spent_internal_branches"] <= budgets["per_turn_limit"]


def test_serious_bootstrap_is_opus_gpt_critique_opus_final(monkeypatch):
    calls: list[str] = []

    async def fake_upstream(model, _messages, **_kwargs):
        calls.append(model)
        if model == "gpt-5.4":
            text = '{"omissions":[],"unsafe_assumptions":[],"test_gaps":[],"assignment_gaps":[]}'
        else:
            text = json.dumps(
                {
                    "goal": "Migrate safely",
                    "motivation": "Preserve compatibility",
                    "scope": ["database", "public API"],
                    "test_command": "pytest -q tests/test_migration.py",
                    "done_criteria": ["Migration and rollback tests pass"],
                    "assignments": {
                        "leader": "Own and revise card",
                        "doer": "Implement migration",
                        "analyst": "Diagnose fresh failures",
                        "verifier": "Resolve ambiguous tests",
                    },
                }
            )
        return {
            "text": text,
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "model_id": model,
        }

    async def fake_hands(**kwargs):
        return {
            "text": "",
            "tool_calls": [
                {
                    "id": "read-risk",
                    "type": "function",
                    "function": {"name": "read", "arguments": "{}"},
                }
            ],
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "model_id": kwargs["model_id"],
            "ok": True,
        }

    monkeypatch.setattr(panel, "_default_upstream", fake_upstream)
    monkeypatch.setattr(panel, "run_hands_doer", fake_hands)

    async def collect():
        return [
            event
            async for event in iter_fusion(
                messages=[
                    {
                        "role": "user",
                        "content": "Migrate auth database schema and public API safely",
                    }
                ],
                model_id="zeuscode",
                zeus={"serious": True},
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "read",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            )
        ]

    done = next(
        event["data"]
        for event in asyncio.run(collect())
        if event["kind"] == "done"
    )
    branches = done["onestack"]["branches"]
    budgets = done["onestack"]["crew_budgets"]
    assert calls == ["claude-opus-4-6", "gpt-5.4", "claude-opus-4-6"]
    assert [branch["role"] for branch in branches] == [
        "leader",
        "critic",
        "leader",
        "doer",
    ]
    assert [row["phase"] for row in done["onestack"]["task_card_phases"]] == [
        "draft",
        "critique",
        "final",
    ]
    assert done["onestack"]["task_card"]["critique_applied"] is True
    assert budgets["spent_internal_branches"] == 4
    assert budgets["spent_internal_branches"] <= budgets["per_turn_limit"]


def test_incremental_tool_loop_preserves_openai_tool_calls(monkeypatch):
    calls = 0

    async def fake_hands(**kwargs):
        nonlocal calls
        calls += 1
        assert any(m.get("role") == "tool" for m in kwargs["messages"])
        return {
            "text": "",
            "tool_calls": [
                {
                    "id": "next-1",
                    "type": "function",
                    "function": {"name": "bash", "arguments": '{"cmd":"pytest -q"}'},
                }
            ],
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "model_id": "gpt-5.4",
            "ok": True,
        }

    monkeypatch.setattr(panel, "run_hands_doer", fake_hands)
    prior = CrewSession(
        crew_size=3,
        tier="standard",
        roles=["leader", "doer", "analyst"],
        role_assignments={
            "leader": MODELS["architect"],
            "doer": MODELS["doer_logic"],
            "analyst": MODELS["log_analyst"],
        },
    )

    async def collect():
        return [
            event
            async for event in iter_fusion(
                messages=[
                    {"role": "user", "content": "Fix it"},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "old-1",
                                "type": "function",
                                "function": {"name": "read", "arguments": "{}"},
                            }
                        ],
                    },
                    {"role": "tool", "tool_call_id": "old-1", "content": "file body"},
                ],
                model_id="zeuscode",
                zeus={"crew_state": prior.to_dict()},
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            )
        ]

    events = asyncio.run(collect())
    done = next(e["data"] for e in events if e["kind"] == "done")
    choice = done["choices"][0]
    assert calls == 1
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["tool_calls"][0]["id"] == "next-1"
    assert done["onestack"]["pipeline"] == "incremental"
    assert done["onestack"]["internal_llm_branches"] <= 3
    assert done["onestack"]["turn_kind"] == "tool_loop"
    assert done["onestack"]["crew_size"] == 4
    assert done["onestack"]["active_roles"] == ["doer"]
    assert [branch["role"] for branch in done["onestack"]["branches"]] == ["doer"]
    assert done["onestack"]["crew_budgets"]["spent_internal_branches"] == 1
    assert done["onestack"]["crew_state"]["llm_calls_session"] == 1
    assert done["onestack"].get("research_ok") is None


def test_string_exec_failure_runs_analyst_and_stays_red(monkeypatch):
    async def fake_analyst(**_kwargs):
        return LogAnalystResult(
            skipped=False,
            reason="ok",
            report={"fix_hint": "Fix the failing assertion first."},
            model_id=MODELS["log_analyst"],
            prompt_tokens=2,
            completion_tokens=2,
        )

    async def fake_hands(**kwargs):
        assert "failing assertion" in kwargs["fresh_note"]
        assert "Inspect code" in kwargs["crew_answer"]
        return {
            "text": "The patch is complete.",
            "tool_calls": [],
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "model_id": MODELS["doer_logic"],
            "ok": True,
        }

    monkeypatch.setattr(log_analyst, "run_log_analyst", fake_analyst)
    monkeypatch.setattr(panel, "run_hands_doer", fake_hands)
    prior = CrewSession(
        crew_size=3,
        tier="standard",
        roles=["leader", "doer", "analyst"],
        role_assignments={
            "leader": MODELS["architect"],
            "doer": MODELS["doer_logic"],
            "analyst": MODELS["log_analyst"],
        },
        plan_digest="Inspect code, patch, then rerun tests.",
    )

    async def collect():
        return [
            event
            async for event in iter_fusion(
                messages=[
                    {"role": "user", "content": "Fix it"},
                    {"role": "assistant", "tool_calls": [{"id": "test-1"}]},
                    {"role": "tool", "tool_call_id": "test-1", "content": "1 failed"},
                ],
                model_id="zeuscode",
                zeus={
                    "crew_state": prior.to_dict(),
                    "exec": {"tests_ok": "false"},
                },
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            )
        ]

    events = asyncio.run(collect())
    done = next(event["data"] for event in events if event["kind"] == "done")
    assert [branch["role"] for branch in done["onestack"]["branches"]] == [
        "analyst",
        "doer",
    ]
    assert done["onestack"]["gate"] == "RED"
    assert done["onestack"]["soft_stop"] is True
    assert done["onestack"]["crew_state"]["machine_evidence"]["tests_failed"] is True


def test_incremental_degraded_analyst_uses_one_bounded_failover(monkeypatch):
    analyst_models = []

    async def fake_analyst(*, model_id, **_kwargs):
        analyst_models.append(model_id)
        degraded = len(analyst_models) == 1
        return LogAnalystResult(
            skipped=False,
            reason="parse_failed" if degraded else "ok",
            report={} if degraded else {"fix_hint": "Use the alternate diagnosis."},
            model_id=model_id,
            prompt_tokens=1,
            completion_tokens=1,
            degraded=degraded,
        )

    async def fake_hands(**kwargs):
        assert "alternate diagnosis" in kwargs["fresh_note"]
        return {
            "text": "Applied the alternate diagnosis.",
            "tool_calls": [],
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "model_id": kwargs["model_id"],
            "ok": True,
        }

    monkeypatch.setattr(log_analyst, "run_log_analyst", fake_analyst)
    monkeypatch.setattr(panel, "run_hands_doer", fake_hands)
    prior = CrewSession(
        crew_size=3,
        tier="standard",
        roles=["leader", "doer", "analyst"],
        role_assignments={
            "leader": MODELS["architect"],
            "doer": MODELS["doer_logic"],
            "analyst": MODELS["log_analyst"],
        },
        plan_digest="Original plan",
    )

    async def collect():
        return [
            event
            async for event in iter_fusion(
                messages=[
                    {"role": "user", "content": "Fix it"},
                    {"role": "assistant", "tool_calls": [{"id": "test-2"}]},
                    {"role": "tool", "tool_call_id": "test-2", "content": "failed"},
                ],
                model_id="zeuscode",
                zeus={
                    "crew_state": prior.to_dict(),
                    "exec": {"exit_code": "1"},
                },
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            )
        ]

    done = next(
        event["data"]
        for event in asyncio.run(collect())
        if event["kind"] == "done"
    )
    branches = done["onestack"]["branches"]
    budgets = done["onestack"]["crew_budgets"]
    assert [branch["role"] for branch in branches] == [
        "analyst",
        "analyst",
        "doer",
    ]
    assert len(analyst_models) == 2
    assert branches[0]["meta"]["degraded"] is True
    assert branches[1]["meta"]["failover"] is True
    assert done["onestack"]["crew_state"]["degraded"] is True
    assert budgets["spent_internal_branches"] == 3
    assert budgets["spent_internal_branches"] <= budgets["per_turn_limit"]


def test_v1_does_not_repeat_architect_or_test_author_watch():
    async def mini(**_kwargs):
        class Result:
            passed = True
            degraded = False
            reason = "ok"

        return Result()

    result = asyncio.run(
        run_trusted_verify_loop(
            answer="A complete implementation response with enough detail to pass the gate.",
            user_q="Implement the feature",
            panel=["gpt-5.4", "claude-opus-4-6"],
            models_by_role={
                "mini_verifier": "gpt-5.4",
                "test_author": "gpt-5.4",
                "architect": "claude-opus-4-6",
            },
            curator_model="claude-opus-4-6",
            mini_verify_fn=mini,
            crew_watch=True,
            task_kind="code",
            skip_log=True,
            prior_oversight_complete=True,
        )
    )
    roles = [branch.role for branch in result.branches]
    assert "test_author" not in roles
    assert "architect" not in roles


def test_adaptive_v1_caps_topology_to_three_roles():
    previous = os.environ.get("ZEUS_FUSION_V1_HEURISTIC")
    os.environ["ZEUS_FUSION_V1_HEURISTIC"] = "1"
    try:
        outcome = asyncio.run(
            execute_pipeline_v1(
                stack=[
                    "claude-opus-4-6",
                    "gpt-5.4",
                    "deepseek-v4-pro",
                ],
                curator="claude-opus-4-6",
                messages=[{"role": "user", "content": "Implement parser fix"}],
                user_q="Implement parser fix",
                max_components=1,
                role_overrides={
                    "leader": "claude-opus-4-6",
                    "doer": "gpt-5.4",
                    "analyst": "deepseek-v4-pro",
                },
            )
        )
        roles = {branch.role for branch in outcome.branches}
        assert {"architect", "analyst"}.issubset(roles)
        assert "test_author" not in roles
        assert len([role for role in roles if role.startswith("doer_")]) == 1
        assert len(outcome.branches) == 3
    finally:
        if previous is None:
            os.environ.pop("ZEUS_FUSION_V1_HEURISTIC", None)
        else:
            os.environ["ZEUS_FUSION_V1_HEURISTIC"] = previous


def test_v1_specialist_advice_reaches_analyst_and_doer():
    advice = "Require transaction rollback and verify authorization boundaries."
    seen = {"analyst": False, "doer": False}

    async def fake_upstream(model, messages, **_kwargs):
        prompt = "\n".join(str(message.get("content") or "") for message in messages)
        if model == "claude-opus-4-6":
            text = (
                '{"components":[{"id":"c1","role":"doer_logic","goal":"Implement safe '
                'migration","acceptance_one_liner":"Working migration with rollback",'
                '"files_hint":["migration.py"]}],"api_contract":"migrate()",'
                '"files_contract":"migration.py"}'
            )
        elif model == "grok-4.3":
            text = advice
        elif model == "deepseek-v4-pro":
            seen["analyst"] = advice in prompt
            text = '{"tests":[{"component_id":"c1","checks":["rollback","auth"]}]}'
        else:
            seen["doer"] = advice in prompt
            text = (
                "// file: migration.py\n"
                "def migrate():\n"
                "    return 'working migration with rollback and authorization checks'\n"
            )
        return {
            "ok": True,
            "text": text,
            "prompt_tokens": 2,
            "completion_tokens": 3,
            "model_id": model,
        }

    outcome = asyncio.run(
        execute_pipeline_v1(
            stack=[
                "claude-opus-4-6",
                "gpt-5.4",
                "deepseek-v4-pro",
                "grok-4.3",
            ],
            curator="claude-opus-4-6",
            messages=[{"role": "user", "content": "Implement safe migration"}],
            user_q="Implement safe migration",
            max_components=1,
            role_overrides={
                "leader": "claude-opus-4-6",
                "doer": "gpt-5.4",
                "analyst": "deepseek-v4-pro",
                "specialist": "grok-4.3",
            },
            upstream_call=fake_upstream,
        )
    )
    specialist = next(branch for branch in outcome.branches if branch.role == "specialist")
    assert seen == {"analyst": True, "doer": True}
    assert specialist.meta["checklist_sha256"]


def test_hands_doer_wraps_upstream_in_bounded_timeout(monkeypatch):
    observed: dict[str, float] = {}

    async def fake_upstream(*_args, **_kwargs):
        return {"text": "done", "tool_calls": []}

    async def fake_wait_for(awaitable, *, timeout):
        observed["timeout"] = timeout
        return await awaitable

    monkeypatch.setenv("ZEUS_HANDS_DOER_TIMEOUT_S", "17")
    monkeypatch.setattr(panel.asyncio, "wait_for", fake_wait_for)
    result = asyncio.run(
        panel.run_hands_doer(
            model_id="gpt-5.4-mini",
            messages=[{"role": "user", "content": "Inspect files"}],
            crew_answer="Read the repository, then act.",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            upstream_call=fake_upstream,
        )
    )

    assert observed["timeout"] == 17.0
    assert result["ok"] is True


def test_tool_returncode_failure_activates_analyst_without_zeus_exec(monkeypatch):
    signals = detect_adaptive_signals(
        user_q="Fix it",
        messages=[
            {"role": "user", "content": "Fix it"},
            {"role": "assistant", "tool_calls": [{"id": "cmd-1"}]},
            {
                "role": "tool",
                "tool_call_id": "cmd-1",
                "content": "<returncode>1</returncode>\n<output>Traceback: boom</output>",
            },
        ],
    )
    assert signals["tool_failed"] is True
    assert signals["turn_kind"] == "exec_feedback"

    async def fake_analyst(**_kwargs):
        return LogAnalystResult(
            skipped=False,
            reason="ok",
            report={"fix_hint": "Use the traceback to correct the patch."},
            model_id=MODELS["log_analyst"],
            prompt_tokens=1,
            completion_tokens=1,
        )

    async def fake_hands(**kwargs):
        assert "traceback" in kwargs["fresh_note"].lower()
        assert "Inspect, patch" in kwargs["crew_answer"]
        return {
            "text": "",
            "tool_calls": [
                {
                    "id": "cmd-2",
                    "type": "function",
                    "function": {"name": "bash", "arguments": '{"command":"fix"}'},
                }
            ],
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "model_id": MODELS["doer_logic"],
            "ok": True,
        }

    monkeypatch.setattr(log_analyst, "run_log_analyst", fake_analyst)
    monkeypatch.setattr(panel, "run_hands_doer", fake_hands)
    prior = CrewSession(
        crew_size=3,
        tier="standard",
        roles=["leader", "doer", "analyst"],
        role_assignments={
            "leader": MODELS["architect"],
            "doer": MODELS["doer_logic"],
            "analyst": MODELS["log_analyst"],
        },
        plan_digest="Inspect, patch, and test.",
    )

    async def collect():
        return [
            event
            async for event in iter_fusion(
                messages=[
                    {"role": "user", "content": "Fix it"},
                    {"role": "assistant", "tool_calls": [{"id": "cmd-1"}]},
                    {
                        "role": "tool",
                        "tool_call_id": "cmd-1",
                        "content": "<returncode>1</returncode>\n<output>Traceback: boom</output>",
                    },
                ],
                model_id="zeuscode",
                zeus={"crew_state": prior.to_dict()},
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            )
        ]

    done = next(
        event["data"]
        for event in asyncio.run(collect())
        if event["kind"] == "done"
    )
    assert done["onestack"]["active_roles"] == ["analyst", "doer"]
    assert [branch["role"] for branch in done["onestack"]["branches"]] == [
        "analyst",
        "doer",
    ]


def test_submit_marker_is_replaced_until_grok_test_is_green(monkeypatch):
    async def fake_test_verifier(model, _messages, **_kwargs):
        assert model == "grok-4.5"
        return {
            "text": (
                '{"command":"pytest -q '
                'astropy/wcs/wcsapi/tests/test_fitswcs.py",'
                '"reason":"regression target","covers_diff":true}'
            ),
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "model_id": model,
        }

    async def fake_analyst(**_kwargs):
        return LogAnalystResult(
            skipped=False,
            reason="ok",
            report={
                "critical": False,
                "fix_hint": "Do not submit until the planned pytest is green.",
            },
            model_id="deepseek-v4-pro",
            prompt_tokens=1,
            completion_tokens=1,
        )

    async def fake_hands(**kwargs):
        assert kwargs["model_id"] == "gpt-5.4"
        return {
            "text": "Ready to submit.",
            "tool_calls": [
                {
                    "id": "submit-early",
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "arguments": (
                            '{"command":"echo '
                            'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT '
                            '&& cat patch.txt"}'
                        ),
                    },
                }
            ],
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "model_id": kwargs["model_id"],
            "ok": True,
        }

    monkeypatch.setattr(panel, "_default_upstream", fake_test_verifier)
    monkeypatch.setattr(panel, "run_hands_doer", fake_hands)
    monkeypatch.setattr(log_analyst, "run_log_analyst", fake_analyst)
    prior = CrewSession(
        crew_size=4,
        tier="standard",
        roles=["leader", "doer", "analyst", "specialist"],
        role_assignments={
            "leader": "claude-opus-4-6",
            "doer": "gpt-5.4",
            "analyst": "deepseek-v4-pro",
            "specialist": "grok-4.5",
        },
        plan_digest="Patch astropy and run a focused regression test.",
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                },
            },
        },
    ]

    async def collect():
        return [
            event
            async for event in iter_fusion(
                messages=[
                    {"role": "user", "content": "Fix astropy__astropy-11693"},
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "edit-astropy",
                                "type": "function",
                                "function": {
                                    "name": "edit",
                                    "arguments": (
                                        '{"path":"astropy/wcs/wcsapi/fitswcs.py"}'
                                    ),
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "edit-astropy",
                        "content": "<returncode>0</returncode>\nDone",
                    },
                ],
                model_id="zeuscode",
                zeus={"crew_state": prior.to_dict()},
                tools=tools,
            )
        ]

    done = next(
        event["data"]
        for event in asyncio.run(collect())
        if event["kind"] == "done"
    )
    calls = done["choices"][0]["message"]["tool_calls"]
    assert all(
        "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
        not in call["function"]["arguments"]
        for call in calls
    )
    assert calls[-1]["function"]["name"] == "bash"
    assert "git diff" in calls[-1]["function"]["arguments"]
    assert "test_fitswcs.py" in done["onestack"]["machine_evidence"][
        "test_plan_command"
    ]
    assert done["onestack"]["submit_gate"] == "RED"
    assert done["onestack"]["active_roles"] == ["doer"]
    assert done["onestack"]["internal_llm_branches"] == 1


def test_fresh_green_test_allows_submit_without_opus_or_grok_recall(monkeypatch):
    async def unexpected_upstream(*_args, **_kwargs):
        raise AssertionError("Opus/Grok must not run on a green test continuation")

    async def fake_analyst(**_kwargs):
        return LogAnalystResult(
            skipped=False,
            reason="ok",
            report={
                "critical": False,
                "summary": "Focused pytest is fresh and green.",
            },
            model_id="deepseek-v4-pro",
            prompt_tokens=1,
            completion_tokens=1,
        )

    async def fake_hands(**kwargs):
        return {
            "text": "Verified.",
            "tool_calls": [
                {
                    "id": "submit-green",
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "arguments": (
                            '{"command":"echo '
                            'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT '
                            '&& cat patch.txt"}'
                        ),
                    },
                }
            ],
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "model_id": kwargs["model_id"],
            "ok": True,
        }

    monkeypatch.setattr(panel, "_default_upstream", unexpected_upstream)
    monkeypatch.setattr(panel, "run_hands_doer", fake_hands)
    monkeypatch.setattr(log_analyst, "run_log_analyst", fake_analyst)
    prior = CrewSession(
        crew_size=4,
        tier="standard",
        roles=["leader", "doer", "analyst", "specialist"],
        role_assignments={
            "leader": "claude-opus-4-6",
            "doer": "gpt-5.4",
            "analyst": "deepseek-v4-pro",
            "specialist": "grok-4.5",
            "log_analyst": "deepseek-v4-pro",
            "test_verifier": "grok-4.5",
        },
        machine_evidence={
            "diff_nonempty": True,
            "diff_seq": 1,
            "test_plan_command": (
                "pytest -q astropy/wcs/wcsapi/tests/test_fitswcs.py"
            ),
        },
    )

    async def collect():
        return [
            event
            async for event in iter_fusion(
                messages=[
                    {"role": "user", "content": "Fix astropy__astropy-11693"},
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "test-astropy-green",
                                "type": "function",
                                "function": {
                                    "name": "bash",
                                    "arguments": (
                                        '{"command":"pytest -q '
                                        'astropy/wcs/wcsapi/tests/test_fitswcs.py"}'
                                    ),
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "test-astropy-green",
                        "content": "<returncode>0</returncode>\n1 passed",
                    },
                ],
                model_id="zeuscode",
                zeus={"crew_state": prior.to_dict()},
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "command": {"type": "string"},
                                },
                            },
                        },
                    }
                ],
            )
        ]

    done = next(
        event["data"]
        for event in asyncio.run(collect())
        if event["kind"] == "done"
    )
    call = done["choices"][0]["message"]["tool_calls"][0]
    assert call["function"]["name"] == "bash"
    assert "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" in call["function"]["arguments"]
    assert done["onestack"]["submit_gate"] == "GREEN"
    assert done["onestack"]["active_roles"] == ["doer"]
    assert done["onestack"]["machine_evidence"]["fresh_green_test"] is True


def test_inspection_commands_never_erase_a_real_diff():
    evidence = collect_tool_evidence(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "diff-1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command":"git diff"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "diff-1",
                "content": (
                    "<returncode>0</returncode>\n"
                    "diff --git a/astropy/wcs/wcsapi/fitswcs.py "
                    "b/astropy/wcs/wcsapi/fitswcs.py\n"
                    "--- a/astropy/wcs/wcsapi/fitswcs.py\n"
                    "+++ b/astropy/wcs/wcsapi/fitswcs.py"
                ),
            },
        ]
    )
    assert evidence["diff_nonempty"] is True
    assert evidence["changed_paths"] == ["astropy/wcs/wcsapi/fitswcs.py"]
    for command in (
        "sed -n '320,340p' astropy/wcs/wcsapi/fitswcs.py",
        "find astropy/wcs -name 'test_*.py'",
        "python3 --version",
    ):
        evidence = collect_tool_evidence(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": f"read-{command[:6]}",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps({"command": command}),
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": f"read-{command[:6]}",
                    "content": "<returncode>0</returncode>\n<output>ok</output>",
                },
            ],
            evidence,
        )
        assert evidence["last_tool_event"]["mutates_diff"] is False, command
        assert evidence["diff_nonempty"] is True, command


def test_in_place_edit_still_counts_as_a_mutation():
    evidence = collect_tool_evidence(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "sed-inplace",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": json.dumps(
                                {"command": "sed -i 's/a/b/' module.py"}
                            ),
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "sed-inplace",
                "content": "<returncode>0</returncode>",
            },
        ],
        {"diff_nonempty": True, "diff_seq": 1, "tool_event_seq": 1},
    )
    assert evidence["last_tool_event"]["mutates_diff"] is True
    assert evidence["diff_nonempty"] is False
    assert "module.py" in evidence["changed_paths"]


def test_old_failure_stops_summoning_the_analyst_after_a_good_step():
    history = [
        {"role": "user", "content": "Fix astropy__astropy-11693"},
        {"role": "assistant", "tool_calls": [{"id": "boom"}]},
        {
            "role": "tool",
            "tool_call_id": "boom",
            "content": "<returncode>1</returncode>\nTraceback (most recent call last):",
        },
    ]
    assert detect_adaptive_signals(user_q="Fix it", messages=history)["exec_failed"]
    history += [
        {"role": "assistant", "tool_calls": [{"id": "read"}]},
        {
            "role": "tool",
            "tool_call_id": "read",
            "content": "<returncode>0</returncode>\n<output>class FITSWCS:</output>",
        },
    ]
    healthy = detect_adaptive_signals(user_q="Fix it", messages=history)
    assert healthy["exec_failed"] is False
    assert healthy["significant_tool_output"] is False


def test_source_listing_alone_is_not_an_analyst_trigger():
    signals = detect_adaptive_signals(
        user_q="Fix it",
        messages=[
            {"role": "user", "content": "Fix it"},
            {"role": "assistant", "tool_calls": [{"id": "cat"}]},
            {
                "role": "tool",
                "tool_call_id": "cat",
                "content": (
                    "<returncode>0</returncode>\n<output>\n"
                    "    raise Exception('boom')  # warning: legacy path\n"
                    "</output>"
                ),
            },
        ],
    )
    assert signals["exec_failed"] is False
    assert signals["significant_tool_output"] is False


def test_fresh_diff_without_a_plan_calls_the_test_verifier():
    prior = CrewSession(
        crew_size=4,
        tier="standard",
        roles=["leader", "doer", "analyst", "specialist"],
        role_assignments={
            "leader": MODELS["architect"],
            "doer": MODELS["doer_logic"],
            "analyst": MODELS["log_analyst"],
            "specialist": MODELS["test_author"],
        },
    )
    decision, _ = select_crew(
        user_q="Fix astropy__astropy-11693",
        messages=[
            {"role": "user", "content": "Fix astropy__astropy-11693"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "edit-1",
                        "type": "function",
                        "function": {
                            "name": "edit",
                            "arguments": '{"path":"astropy/wcs/wcsapi/fitswcs.py"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "edit-1",
                "content": "<returncode>0</returncode>\nDone",
            },
        ],
        prior=prior,
        models_by_role=MODELS,
        tool_enabled=True,
    )
    assert decision.active_roles == ["verifier", "doer"]
    assert decision.role_assignments["test_verifier"] == MODELS["test_author"]


def test_fresh_failed_diff_activates_analyst_and_verifier_together():
    prior = CrewSession(
        role_assignments={
            "leader": MODELS["architect"],
            "doer": MODELS["doer_logic"],
            "analyst": MODELS["log_analyst"],
            "verifier": MODELS["test_author"],
        },
        machine_evidence={
            "diff_nonempty": True,
            "diff_seq": 1,
            "changed_paths": ["unknown.extension"],
        },
    )
    decision, _ = select_crew(
        user_q="Continue",
        messages=[
            {"role": "user", "content": "Continue"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "edit-failed",
                        "type": "function",
                        "function": {
                            "name": "edit",
                            "arguments": '{"path":"unknown.extension"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "edit-failed",
                "content": "<returncode>1</returncode>\nFAILED to write",
            },
        ],
        prior=prior,
        models_by_role=MODELS,
        available_models=list(MODELS.values()),
        tool_enabled=True,
    )
    assert decision.active_roles == ["analyst", "verifier", "doer"]


def test_test_command_chain_has_no_empty_link():
    assert plan_test_command(
        "1. Patch the module.\n"
        "2. Run `pytest -q astropy/wcs/wcsapi/tests/test_fitswcs.py`\n"
    ) == "pytest -q astropy/wcs/wcsapi/tests/test_fitswcs.py"
    assert conventional_test_commands(
        ["astropy/wcs/wcsapi/fitswcs.py"]
    ) == [
        "python -m pytest -q astropy/wcs/wcsapi/tests/test_fitswcs.py",
        "python -m pytest -q astropy/wcs/wcsapi/tests",
    ]
    command, source = derive_test_command(
        {"changed_paths": ["astropy/wcs/wcsapi/fitswcs.py"]},
        plan_digest="no command here",
    )
    assert command == "python -m pytest -q astropy/wcs/wcsapi/tests/test_fitswcs.py"
    assert source == "changed_paths"
    already_tried = derive_test_command(
        {
            "changed_paths": ["astropy/wcs/wcsapi/fitswcs.py"],
            "test_commands_tried": [
                "python -m pytest -q astropy/wcs/wcsapi/tests/test_fitswcs.py"
            ],
        },
        plan_digest="",
    )
    assert already_tried == (
        "python -m pytest -q astropy/wcs/wcsapi/tests",
        "changed_paths",
    )


def test_blocked_submit_still_returns_a_tool_call_when_grok_is_silent(monkeypatch):
    async def silent_verifier(model, _messages, **_kwargs):
        return {
            "text": "I cannot pick a test right now.",
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "model_id": model,
        }

    async def fake_hands(**kwargs):
        return {
            "text": "Done, submitting.",
            "tool_calls": [
                {
                    "id": "submit-now",
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "arguments": (
                            '{"command":"echo '
                            'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"}'
                        ),
                    },
                }
            ],
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "model_id": kwargs["model_id"],
            "ok": True,
        }

    monkeypatch.setattr(panel, "_default_upstream", silent_verifier)
    monkeypatch.setattr(panel, "run_hands_doer", fake_hands)
    done = _run_submit_turn(
        prior_evidence={
            "diff_nonempty": True,
            "diff_seq": 4,
            "tool_event_seq": 4,
            "changed_paths": ["astropy/wcs/wcsapi/fitswcs.py"],
        },
        plan_digest="Patch fitswcs and verify.",
    )
    calls = done["choices"][0]["message"]["tool_calls"]
    assert calls, "a tool-driven client must never receive a reply without a call"
    arguments = calls[-1]["function"]["arguments"]
    assert "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" not in arguments
    assert "astropy/wcs/wcsapi/tests/test_fitswcs.py" in arguments
    evidence = done["onestack"]["machine_evidence"]
    assert evidence["test_plan_source"] == "changed_paths"
    assert done["onestack"]["submit_gate"] == "RED"


def test_gate_releases_a_real_patch_after_three_blocks(monkeypatch):
    async def fake_analyst(**_kwargs):
        return LogAnalystResult(
            skipped=False,
            reason="ok",
            report={"critical": False, "summary": "Diff looks consistent."},
            model_id=MODELS["log_analyst"],
            prompt_tokens=1,
            completion_tokens=1,
        )

    async def fake_hands(**kwargs):
        return {
            "text": "Submitting the finished patch.",
            "tool_calls": [
                {
                    "id": "submit-final",
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "arguments": (
                            '{"command":"echo '
                            'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"}'
                        ),
                    },
                }
            ],
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "model_id": kwargs["model_id"],
            "ok": True,
        }

    monkeypatch.setattr(log_analyst, "run_log_analyst", fake_analyst)
    monkeypatch.setattr(panel, "run_hands_doer", fake_hands)
    done = _run_submit_turn(
        prior_evidence={
            "diff_nonempty": True,
            "diff_seq": 4,
            "tool_event_seq": 4,
            "submit_block_count": 3,
            "test_plan_command": "pytest -q astropy/wcs/wcsapi/tests/test_fitswcs.py",
            "changed_paths": ["astropy/wcs/wcsapi/fitswcs.py"],
        },
        plan_digest="Patch fitswcs and verify.",
    )
    call = done["choices"][0]["message"]["tool_calls"][0]
    assert "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" in call["function"]["arguments"]
    assert done["onestack"]["submit_gate"] == "GREEN"
    assert (
        done["onestack"]["machine_evidence"]["submit_gate_failopen"]
        == "retries_exhausted"
    )
    assert done["onestack"]["crew_state"]["degraded"] is True


def test_empty_diff_probe_loop_also_ends(monkeypatch):
    async def fake_analyst(**_kwargs):
        return LogAnalystResult(
            skipped=False,
            reason="ok",
            report={"critical": False, "summary": "Nothing staged."},
            model_id=MODELS["log_analyst"],
            prompt_tokens=1,
            completion_tokens=1,
        )

    async def fake_hands(**kwargs):
        return {
            "text": "Submitting.",
            "tool_calls": [
                {
                    "id": "submit-empty",
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "arguments": (
                            '{"command":"echo '
                            'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"}'
                        ),
                    },
                }
            ],
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "model_id": kwargs["model_id"],
            "ok": True,
        }

    monkeypatch.setattr(log_analyst, "run_log_analyst", fake_analyst)
    monkeypatch.setattr(panel, "run_hands_doer", fake_hands)
    done = _run_submit_turn(
        prior_evidence={
            "diff_nonempty": False,
            "tool_event_seq": 4,
            "submit_block_count": 3,
        },
        plan_digest="Patch fitswcs and verify.",
    )
    call = done["choices"][0]["message"]["tool_calls"][0]
    assert "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" in call["function"]["arguments"]
    assert (
        done["onestack"]["machine_evidence"]["submit_gate_failopen"]
        == "retries_exhausted_without_diff"
    )


def test_disguised_edits_are_still_recognized_as_mutations():
    for command in (
        "sed --in-place 's/a/b/' astropy/wcs/wcsapi/fitswcs.py",
        "awk -i inplace '{print}' astropy/wcs/wcsapi/fitswcs.py",
        "find astropy -name '*.pyc' -delete",
        "cat > astropy/wcs/wcsapi/fitswcs.py <<'EOF'",
    ):
        evidence = collect_tool_evidence(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": f"write-{abs(hash(command))}",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps({"command": command}),
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": f"write-{abs(hash(command))}",
                    "content": "<returncode>0</returncode>",
                },
            ],
            {
                "diff_nonempty": True,
                "diff_seq": 1,
                "test_plan_command": "pytest -q tests/test_target.py",
                "test_green": True,
                "test_relevant": True,
                "test_seq": 2,
                "fresh_green_test": True,
                "tool_event_seq": 2,
            },
        )
        assert evidence["fresh_green_test"] is False, command


def test_escaping_paths_never_reach_a_test_command():
    evidence = collect_tool_evidence(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "hostile-diff",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command":"git diff"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "hostile-diff",
                "content": (
                    "<returncode>0</returncode>\n"
                    "diff --git a/../../etc/passwd.py b/../../etc/passwd.py\n"
                    "diff --git a//etc/shadow.py b//etc/shadow.py\n"
                    "diff --git a/pkg/mod.py b/pkg/mod.py"
                ),
            },
        ]
    )
    assert evidence["changed_paths"] == ["pkg/mod.py"]
    assert derive_test_command(evidence, plan_digest="") == (
        "python -m pytest -q pkg/tests/test_mod.py",
        "changed_paths",
    )


def _run_submit_turn(
    *, prior_evidence: dict, plan_digest: str
) -> dict:
    """Drive one continuation turn that ends in a submit attempt."""
    prior = CrewSession(
        crew_size=4,
        tier="standard",
        roles=["leader", "doer", "analyst", "specialist"],
        role_assignments={
            "leader": MODELS["architect"],
            "doer": MODELS["doer_logic"],
            "analyst": MODELS["log_analyst"],
            "specialist": MODELS["test_author"],
        },
        machine_evidence=dict(prior_evidence),
        plan_digest=plan_digest,
    )

    async def collect():
        return [
            event
            async for event in iter_fusion(
                messages=[
                    {"role": "user", "content": "Fix astropy__astropy-11693"},
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "read-src",
                                "type": "function",
                                "function": {
                                    "name": "bash",
                                    "arguments": json.dumps(
                                        {
                                            "command": (
                                                "sed -n '320,340p' "
                                                "astropy/wcs/wcsapi/fitswcs.py"
                                            )
                                        }
                                    ),
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "read-src",
                        "content": "<returncode>0</returncode>\n<output>ok</output>",
                    },
                ],
                model_id="zeuscode",
                zeus={"crew_state": prior.to_dict()},
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "parameters": {
                                "type": "object",
                                "properties": {"command": {"type": "string"}},
                            },
                        },
                    }
                ],
            )
        ]

    return next(
        event["data"]
        for event in asyncio.run(collect())
        if event["kind"] == "done"
    )


def test_volatile_crew_note_never_sits_above_the_transcript():
    ordered = panel._stable_prefix_messages(
        [
            {"role": "system", "content": "client rules"},
            {"role": "user", "content": "Fix it"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "1 failed"},
        ],
        plan="Patch fitswcs and verify.",
        fresh_note="DeepSeek says the assertion is off by one.",
    )
    # The client prompt stays first, the rarely-changing plan sits right under
    # it, and only the volatile note lands after the append-only transcript.
    assert ordered[0]["content"] == "client rules"
    assert "Patch fitswcs" in ordered[1]["content"]
    assert ordered[1]["role"] == "system"
    assert ordered[-1]["role"] == "system"
    assert "off by one" in ordered[-1]["content"]
    assert [m["role"] for m in ordered[2:-1]] == ["user", "assistant", "tool"]


def test_a_growing_tool_loop_keeps_a_shared_prefix():
    def build(transcript):
        return panel._stable_prefix_messages(
            transcript, plan="Same plan", fresh_note="turn note"
        )

    base = [
        {"role": "system", "content": "client rules"},
        {"role": "user", "content": "Fix it"},
    ]
    turn_one = build(list(base))
    turn_two = build(base + [{"role": "tool", "tool_call_id": "c1", "content": "ok"}])
    shared = turn_one[:-1]
    assert turn_two[: len(shared)] == shared


def test_doer_sends_identical_cache_anchor_bytes_across_tool_turns():
    sent: list[list[dict[str, Any]]] = []
    cache_keys: list[str] = []

    async def capture(_model, messages, **kwargs):
        sent.append(messages)
        cache_keys.append(str(kwargs.get("prompt_cache_key") or ""))
        return {
            "text": "",
            "tool_calls": [
                {
                    "id": f"c{len(sent)}",
                    "type": "function",
                    "function": {"name": "bash", "arguments": '{"command":"true"}'},
                }
            ],
            "prompt_tokens": 10,
            "completion_tokens": 1,
        }

    base = [
        {"role": "system", "content": "client rules"},
        {"role": "user", "content": "Fix it"},
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    first = asyncio.run(
        panel.run_hands_doer(
            model_id="gpt-5.4",
            messages=base,
            crew_answer='{"card_id":"tc_same","goal":"Fix it"}',
            fresh_note="volatile bootstrap memory",
            tools=tools,
            require_tool_call=True,
            upstream_call=capture,
        )
    )
    second = asyncio.run(
        panel.run_hands_doer(
            model_id="gpt-5.4",
            messages=[
                *base,
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": first["tool_calls"],
                },
                {
                    "role": "tool",
                    "tool_call_id": "c1",
                    "content": "<returncode>0</returncode>",
                },
            ],
            crew_answer='{"card_id":"tc_same","goal":"Fix it"}',
            fresh_note="different volatile evidence",
            tools=tools,
            require_tool_call=True,
            upstream_call=capture,
        )
    )
    assert panel._stable_prefix_bytes(sent[0]) == panel._stable_prefix_bytes(sent[1])
    assert first["cache_prefix_sha256"] == second["cache_prefix_sha256"]
    assert first["cache_prefix_bytes"] == second["cache_prefix_bytes"]
    assert cache_keys[0] == cache_keys[1] == (
        f"zeus-task-{first['cache_prefix_sha256'][:48]}"
    )


def test_cached_tokens_survive_the_trip_to_the_bill():
    from app.fusion.types import BranchUsage
    from app.routers.chat import _branch_rows

    row = _branch_rows(
        type("FR", (), {"branches": [
            BranchUsage(
                model_id="gpt-5.4",
                billable_state="completed",
                prompt_tokens=30000,
                completion_tokens=400,
                cached_tokens=28000,
                role="doer",
            )
        ]})()
    )[0]
    assert row["usage"]["cached_tokens"] == 28000
    from app.cost import estimate_upstream_usd

    full = estimate_upstream_usd("gpt-5.4", 30000, 400)
    discounted = estimate_upstream_usd("gpt-5.4", 30000, 400, cached_tokens=28000)
    assert discounted < full


def test_cached_tokens_can_never_exceed_the_prompt():
    from app.fusion.types import BranchUsage

    usage = BranchUsage(
        model_id="gpt-5.4",
        billable_state="completed",
        prompt_tokens=100,
        cached_tokens=999999,
    ).usage
    assert usage["cached_tokens"] == 100


def test_a_green_test_is_remembered_for_the_files_it_covered(tmp_path, monkeypatch):
    from app.fusion import project_memory

    monkeypatch.setattr(project_memory, "_DATA_DIR", tmp_path)
    project_memory.reset_memory_for_tests()
    key = "proj:astropy"
    project_memory.sync_from_evidence(
        key,
        {
            "changed_paths": ["astropy/wcs/wcsapi/fitswcs.py"],
            "fresh_green_test": True,
            "test_command": "python -m pytest -q astropy/wcs/wcsapi/tests/test_fitswcs.py",
        },
    )
    remembered = project_memory.known_test_commands(
        key, ["astropy/wcs/wcsapi/fitswcs.py"]
    )
    assert remembered == [
        "python -m pytest -q astropy/wcs/wcsapi/tests/test_fitswcs.py"
    ]
    command, source = derive_test_command(
        {"changed_paths": ["astropy/wcs/wcsapi/fitswcs.py"]},
        remembered=remembered,
    )
    assert command == "python -m pytest -q astropy/wcs/wcsapi/tests/test_fitswcs.py"
    assert source == "project_memory"


def test_a_failing_test_is_a_finding_not_a_broken_command(tmp_path, monkeypatch):
    from app.fusion import project_memory

    monkeypatch.setattr(project_memory, "_DATA_DIR", tmp_path)
    project_memory.reset_memory_for_tests()
    key = "proj:bank"
    project_memory.sync_from_evidence(
        key,
        {
            "last_event_failed": True,
            "last_tool_event": {
                "command": "python -m pytest -q tests/test_x.py",
                "return_code": 1,
                "is_test": True,
            },
        },
    )
    assert project_memory.failed_commands(key) == []
    project_memory.sync_from_evidence(
        key,
        {
            "last_event_failed": True,
            "last_tool_event": {
                "command": "rg --files",
                "return_code": 127,
                "is_test": False,
            },
        },
    )
    assert project_memory.failed_commands(key) == ["rg --files"]
    assert "do not retry" in project_memory.format_memory_block(key)


def test_memory_refuses_paths_that_escape_the_repo(tmp_path, monkeypatch):
    from app.fusion import project_memory

    monkeypatch.setattr(project_memory, "_DATA_DIR", tmp_path)
    project_memory.reset_memory_for_tests()
    key = "proj:escape"
    project_memory.remember_test_command(
        key,
        ["../../etc/passwd", "/etc/shadow", "app/ok.py"],
        "python -m pytest -q tests/test_ok.py",
    )
    assert project_memory.known_test_commands(key, ["../../etc/passwd"]) == []
    assert project_memory.known_test_commands(key, ["/etc/shadow"]) == []
    assert project_memory.known_test_commands(key, ["app/ok.py"]) == [
        "python -m pytest -q tests/test_ok.py"
    ]


def test_remembered_command_still_rotates_when_it_was_already_tried():
    command, source = derive_test_command(
        {
            "changed_paths": ["app/parser.py"],
            "test_commands_tried": ["python -m pytest -q tests/test_stale.py"],
        },
        remembered=["python -m pytest -q tests/test_stale.py"],
    )
    assert command != "python -m pytest -q tests/test_stale.py"
    assert source == "changed_paths"


def test_the_note_never_rewrites_an_earlier_message():
    transcript = [
        {"role": "system", "content": "client rules"},
        {"role": "user", "content": "Now fix the parser"},
    ]
    quiet = panel._stable_prefix_messages(
        list(transcript), plan="Patch and verify.", fresh_note=""
    )
    noisy = panel._stable_prefix_messages(
        list(transcript),
        plan="Patch and verify.",
        fresh_note="DeepSeek found an off-by-one.",
    )
    # Turns with crew output and turns without must share a prefix, otherwise
    # a single analyst remark re-prices the whole transcript.
    assert noisy[: len(quiet)] == quiet
    assert noisy[-1]["role"] == "system"
    assert "off-by-one" in noisy[-1]["content"]
    roles = [m["role"] for m in noisy]
    assert all(not (a == "user" and b == "user") for a, b in zip(roles, roles[1:]))


def test_read_only_command_that_missed_a_file_is_not_a_broken_tool(
    tmp_path, monkeypatch
):
    from app.fusion import project_memory

    monkeypatch.setattr(project_memory, "_DATA_DIR", tmp_path)
    project_memory.reset_memory_for_tests()
    key = "proj:readonly"
    project_memory.sync_from_evidence(
        key,
        {
            "last_event_failed": True,
            "last_tool_event": {
                "command": "cat astropy/missing.py",
                "return_code": 1,
                "is_test": False,
            },
        },
    )
    assert project_memory.failed_commands(key) == []


def test_project_memory_scope_is_namespaced_per_api_key():
    from app.routers.chat import _namespace_project_scope

    mine = _namespace_project_scope("key-a", "astropy")
    theirs = _namespace_project_scope("key-b", "astropy")
    assert mine != theirs
    assert mine == _namespace_project_scope("key-a", "astropy")
    assert "astropy" not in mine


def test_url_credentials_never_reach_the_evidence_store():
    from app.fusion.verify import sanitize_evidence_text

    cleaned = sanitize_evidence_text(
        "git clone https://bob:hunter2@github.com/acme/x.git && "
        "curl -H 'Authorization: Bearer abcdef123456'"
    )
    assert "hunter2" not in cleaned
    assert "abcdef123456" not in cleaned


def test_prose_in_a_required_tool_loop_is_rejected_without_hidden_retry():
    attempts: list[Any] = []

    async def chatty_then_obedient(model, messages, **kwargs):
        attempts.append(kwargs.get("tool_choice"))
        if len(attempts) == 1:
            return {
                "text": "helper_7 multiplies by 8; the fix is value * 7.",
                "tool_calls": [],
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "cached_tokens": 90,
            }
        return {
            "text": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "bash", "arguments": '{"command":"ls"}'},
                }
            ],
            "prompt_tokens": 110,
            "completion_tokens": 5,
            "cached_tokens": 100,
        }

    result = asyncio.run(
        panel.run_hands_doer(
            model_id="gpt-5.4",
            messages=[{"role": "user", "content": "fix it"}],
            crew_answer="Patch and verify.",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            require_tool_call=True,
            upstream_call=chatty_then_obedient,
        )
    )
    assert attempts == ["required"]
    assert result["tool_calls"] == []
    assert result["text"] == ""
    assert result["forced_tool_call"] is True
    assert result["ok"] is False
    assert result["prompt_tokens"] == 100
    assert result["cached_tokens"] == 90


def test_a_chat_turn_with_tools_may_still_answer_in_prose():
    attempts: list[Any] = []

    async def chatty(model, messages, **kwargs):
        attempts.append(kwargs.get("tool_choice"))
        return {
            "text": "This function parses the header.",
            "tool_calls": [],
            "prompt_tokens": 40,
            "completion_tokens": 8,
        }

    result = asyncio.run(
        panel.run_hands_doer(
            model_id="gpt-5.4",
            messages=[{"role": "user", "content": "what does this do?"}],
            crew_answer="",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            upstream_call=chatty,
        )
    )
    assert attempts == [None]
    assert result["tool_calls"] == []
    assert result["forced_tool_call"] is False
    assert result["ok"] is True


def test_task_card_parser_fallback_is_typed_and_cache_stable():
    from app.fusion.task_card import parse_task_card

    first = parse_task_card(
        {"goal": "missing required fields"},
        user_q="Fix parser",
        tier="compact",
    )
    restored = parse_task_card(
        first.to_dict(),
        user_q="Fix parser",
        tier="compact",
        degraded=first.degraded,
    )
    assert first.degraded is True
    assert first.assignments["leader"]
    assert first.assignments["doer"]
    assert restored.stable_prefix() == first.stable_prefix()
    malformed = parse_task_card(
        {
            "goal": {"pretends": "to be text"},
            "done_criteria": ["green"],
            "assignments": {"leader": "own", "doer": "act"},
        },
        user_q="Fix parser",
        tier="compact",
    )
    assert malformed.degraded is True
    assert malformed.goal == "Fix parser"


def test_task_card_redacts_credentials_and_control_sequences(tmp_path, monkeypatch):
    from app.fusion import project_memory
    from app.fusion.task_card import parse_task_card

    card = parse_task_card(
        {
            "goal": (
                "Fix https://alice:hunter2@example.com/api using "
                "Authorization: Bearer sk-supersecret123456789\x1b[31m"
            ),
            "motivation": "api_key=zeus_abcdefghijklmnop keep API behavior",
            "scope": ["Inspect token=ghp_abcdefghijklmnopqrstuv"],
            "test_command": "pytest -q",
            "done_criteria": ["No password: hunter2 remains"],
            "assignments": {
                "leader": "Own plan",
                "doer": "Use secret=github_pat_abcdefghijklmnop",
                "analyst": "Fresh errors only",
                "verifier": "Run tests",
            },
        },
        user_q="Fix credential handling",
        tier="serious",
    )
    emitted = card.stable_prefix()
    telemetry = json.dumps(card.to_dict(), ensure_ascii=False)
    monkeypatch.setattr(project_memory, "_DATA_DIR", tmp_path)
    project_memory.reset_memory_for_tests()
    project_memory.remember_task_card("proj:redaction", card)
    persisted = next(tmp_path.glob("*.json")).read_text(encoding="utf-8")
    emitted = "\n".join((emitted, telemetry, persisted))
    assert "hunter2" not in emitted
    assert "supersecret" not in emitted
    assert "ghp_" not in emitted
    assert "github_pat_" not in emitted
    assert "zeus_" not in emitted
    assert "\u001b" not in emitted
    assert "[REDACTED]" in emitted
    assert "example.com/api" in emitted
    assert "API behavior" in emitted


def test_restored_crew_recomputes_untrusted_budget_and_health():
    forged = CrewSession.from_dict(
        {
            "turn_kind": "bootstrap",
            "tier": "serious",
            "crew_size": 2,
            "roles": ["attacker"],
            "role_assignments": {
                "leader": "claude-opus-4-6",
                "doer": "gpt-5.4",
                "analyst": "deepseek-v4-pro",
                "verifier": "grok-4.5",
            },
            "max_internal_branches": 999,
            "remaining_internal_branches": 999,
            "degraded": True,
            "distinct_model_count": 1,
            "llm_calls_session": 7,
            "total_internal_branches": 9,
        }
    )
    assert forged.crew_size == 4
    assert forged.roles == ["leader", "doer", "analyst", "verifier"]
    assert forged.max_internal_branches == 4
    assert forged.remaining_internal_branches == 4
    assert forged.distinct_model_count == 4
    assert forged.degraded is False
    assert forged.llm_calls_session == 7
    assert forged.total_internal_branches == 9

    forged_red = CrewSession.from_dict(
        {
            "turn_kind": "tool_loop",
            "tier": "serious",
            "role_assignments": {
                "leader": "gpt-5.4",
                "doer": "gpt-5.4-mini",
            },
            "max_internal_branches": 999,
            "degraded": False,
            "distinct_model_count": 99,
        }
    )
    assert forged_red.max_internal_branches == 3
    assert forged_red.distinct_model_count == 1
    assert forged_red.degraded is True


def test_task_card_and_findings_are_persisted_with_outcomes(tmp_path, monkeypatch):
    from app.fusion import project_memory
    from app.fusion.task_card import fallback_task_card

    monkeypatch.setattr(project_memory, "_DATA_DIR", tmp_path)
    project_memory.reset_memory_for_tests()
    key = "proj:tenant-scoped"
    card = fallback_task_card("Fix parser", degraded=False)
    project_memory.remember_task_card(key, card)
    assert project_memory.load_task_card(key)["card_id"] == card.card_id
    project_memory.record_finding(
        key,
        card_id=card.card_id,
        evidence_hash="e1",
        report={"critical": True, "fix_hint": "off by one"},
    )
    assert project_memory.finding_outcomes(key, card_id=card.card_id)["open"] == 1
    assert (
        project_memory.close_open_findings(
            key, card_id=card.card_id, outcome="resolved"
        )
        == 1
    )
    assert project_memory.finding_outcomes(key, card_id=card.card_id)["resolved"] == 1


def test_task_card_and_analyst_mutations_do_not_lose_updates(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from app.fusion import project_memory
    from app.fusion.task_card import fallback_task_card

    monkeypatch.setattr(project_memory, "_DATA_DIR", tmp_path)
    project_memory.reset_memory_for_tests()
    key = "proj:atomic"
    card = fallback_task_card("Fix atomic memory", degraded=False)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(project_memory.remember_task_card, key, card)
        second = pool.submit(
            project_memory.remember_analyst_report,
            key,
            card_id=card.card_id,
            evidence_hash="fresh-evidence",
            report={"critical": False, "summary": "keep me"},
        )
        first.result()
        second.result()

    assert project_memory.load_task_card(key)["card_id"] == card.card_id
    assert project_memory.load_analyst_report(
        key, card_id=card.card_id, evidence_hash="fresh-evidence"
    ) == {"critical": False, "summary": "keep me"}


def test_tool_log_compression_preserves_error_tail():
    from app.fusion.context_compress import compress_tool_log

    error_tail = "Traceback\nValueError: exact fresh failure"
    compressed = compress_tool_log("x" * 9000 + error_tail, max_chars=1000)
    assert len(compressed) <= 1000
    assert compressed.endswith(error_tail)
    assert "tool log compressed" in compressed
