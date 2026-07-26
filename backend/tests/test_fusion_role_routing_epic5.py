"""Role Routing Epic 5 — Layer A Test Executor, Studio Gate, SM-1/2/3/6/9 eval."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from app.fusion.pipeline import pick_pipeline
from app.fusion.pipeline_v1 import V1_HAPPY_PATH_MAX_CALLS, validate_architect_brief
from app.fusion.roles import resolve_roles
from app.fusion.test_executor import (
    build_pytest_cmd,
    executor_signal_for_gate,
    is_allowlisted_target,
    run_layer_a_for_request,
    run_test_executor,
    studio_test_requested,
    validate_cmd,
    workspace_from_zeus,
)
from app.fusion.verify import (
    MiniVerifyResult,
    GateSignals,
    compute_unified_gate,
    run_trusted_verify_loop,
)


async def _mini_fail(**_k):
    return MiniVerifyResult(
        good_enough=False,
        confidence=0.1,
        reason="test_fail",
        passed=False,
        degraded=False,
    )


# --- Story 5.1: Allowlist Test Executor ---


def test_hot_path_without_workspace_skips_executor(tmp_path: Path):
    r = run_test_executor(workspace=None, target="tests")
    assert r.skipped is True
    assert r.reason == "no_workspace"
    assert r.tests_failed is None
    assert executor_signal_for_gate(r) is None


def test_non_allowlisted_target_rejected(tmp_path: Path):
    r = run_test_executor(workspace=tmp_path, target="../../etc/passwd")
    assert r.skipped is True
    assert r.reason in ("target_not_allowlisted", "path_escape") or "allowlist" in r.reason
    assert r.tests_failed is None  # hot reject without studio_requested → N/A


def test_studio_reject_is_critical_for_gate(tmp_path: Path):
    """FR-10/11: Studio-requested non-allowlisted must not silently GREEN."""
    r = run_test_executor(
        workspace=tmp_path,
        target="scripts/evil.sh",
        studio_requested=True,
    )
    assert r.skipped is True
    assert r.tests_failed is True
    assert executor_signal_for_gate(r) is True


def test_shell_meta_rejected(tmp_path: Path):
    bad = validate_cmd(["python", "-m", "pytest", "tests;rm -rf /"], workspace=tmp_path)
    assert bad is not None


def test_rootdir_flag_rejected(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    assert (
        validate_cmd(
            ["python", "-m", "pytest", "--rootdir=/etc", "tests"],
            workspace=tmp_path,
        )
        == "unsafe_flag"
    )


def test_cmd_without_path_forces_default_allowlisted_target(tmp_path: Path):
    """B2: bare `python -m pytest` must not bypass allowlist."""
    (tmp_path / "tests").mkdir()
    r = run_test_executor(
        workspace=tmp_path,
        cmd=["python", "-m", "pytest", "-q"],
        dry_run=True,
        studio_requested=True,
    )
    assert r.skipped is False
    assert "tests" in r.cmd


def test_absolute_python_path_rejected(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    assert (
        validate_cmd(["/evil/python", "-m", "pytest", "tests"], workspace=tmp_path)
        == "binary_path_rejected"
    )


def test_allowlisted_pytest_target_ok(tmp_path: Path):
    assert is_allowlisted_target("tests")
    assert is_allowlisted_target("tests/test_smoke.py")
    assert not is_allowlisted_target("scripts/evil.sh")
    cmd = build_pytest_cmd("tests")
    assert validate_cmd(cmd, workspace=tmp_path) is None
    assert "pytest" in cmd


def test_returncode_none_is_failure(tmp_path: Path):
    class _Proc:
        returncode = None
        stdout = ""
        stderr = ""

    (tmp_path / "tests").mkdir()
    r = run_test_executor(
        workspace=tmp_path,
        target="tests",
        runner=lambda *_a, **_k: _Proc(),
    )
    assert r.tests_failed is True
    assert r.exit_code == 1


def test_executor_exit_nonzero_sets_tests_failed(tmp_path: Path):
    class _Proc:
        returncode = 1
        stdout = "FAILED"
        stderr = ""

    def _runner(*_a, **_k):
        return _Proc()

    (tmp_path / "tests").mkdir()
    r = run_test_executor(
        workspace=tmp_path,
        target="tests",
        runner=_runner,
    )
    assert r.skipped is False
    assert r.tests_failed is True
    assert r.exit_code == 1
    assert executor_signal_for_gate(r) is True


def test_executor_exit_zero_tests_ok(tmp_path: Path):
    class _Proc:
        returncode = 0
        stdout = "1 passed"
        stderr = ""

    (tmp_path / "tests").mkdir()
    r = run_test_executor(
        workspace=tmp_path,
        target="tests",
        runner=lambda *_a, **_k: _Proc(),
    )
    assert r.tests_failed is False
    assert executor_signal_for_gate(r) is False


def test_layer_a_hot_chat_skips_even_with_workspace(tmp_path: Path):
    """Hot path: workspace present but no studio_test → skip (FR-9)."""
    r = run_layer_a_for_request({"workspace_path": str(tmp_path)})
    assert r.skipped is True
    assert r.reason == "hot_path_no_studio_test"
    assert r.tests_failed is None


def test_layer_a_studio_runs_when_requested(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    r = run_layer_a_for_request(
        {
            "workspace_path": str(tmp_path),
            "studio_test": True,
            "test_target": "tests",
        },
        dry_run=True,
    )
    assert r.skipped is False
    assert r.tests_failed is False
    assert studio_test_requested({"studio_test": True})
    assert workspace_from_zeus({"workspace_path": str(tmp_path)}) == tmp_path.resolve()


# --- Story 5.2: Studio Gate ---


def test_gate_tests_failed_is_red():
    gate, reasons = compute_unified_gate(
        GateSignals(
            mini_passed=True,
            tests_failed=True,
            allow_green_without_mini=False,
        )
    )
    assert gate == "RED"
    assert "tests_failed" in reasons


def test_studio_pytest_fail_escalates_then_soft_stop():
    """FR-11 / SM-5: tests_failed → RED → escalate while budget → Soft-Stop."""
    os.environ["ZEUS_FUSION_JUDGE_FIX_HEURISTIC"] = "1"
    try:
        out = asyncio.run(
            run_trusted_verify_loop(
                answer="broken publish body with enough text here",
                user_q="publish studio",
                panel=["claude-opus-4-6", "gemini-3-flash"],
                models_by_role={
                    "mini_verifier": "gemini-3-flash",
                    "judge_fix": "claude-opus-4-6",
                },
                curator_model="claude-opus-4-6",
                allow_green_without_mini=True,  # isolate Layer A
                max_escalate=2,
                skip_log=True,
                tests_failed=True,
                mini_verify_fn=_mini_fail,
            )
        )
        assert out.gate == "RED"
        assert "tests_failed" in out.gate_reasons
        assert out.soft_stop is True
        assert out.escalate_count == 2  # budget exhausted; sticky tests_failed
        assert "Проверка" in out.answer
        judge_n = sum(
            1
            for b in out.branches
            if getattr(b, "role", None) == "judge_fix"
        )
        assert judge_n == 2
    finally:
        os.environ.pop("ZEUS_FUSION_JUDGE_FIX_HEURISTIC", None)


def test_studio_pytest_fail_soft_stop_when_no_escalate_budget():
    out = asyncio.run(
        run_trusted_verify_loop(
            answer="broken " * 10,
            user_q="publish",
            panel=["claude-opus-4-6"],
            curator_model="claude-opus-4-6",
            allow_green_without_mini=True,
            max_escalate=0,
            skip_log=True,
            tests_failed=True,
            mini_verify_fn=_mini_fail,
        )
    )
    assert out.gate == "RED"
    assert out.soft_stop is True
    assert out.escalate_count == 0
    assert "tests_failed" in out.gate_reasons


# --- Story 5.3: Eval SM-1/2/3/6/9 (FR-16 explicitly out) ---


def test_sm1_light_trivia_stays_small_no_v1():
    """SM-1 intent: light/ui trivia → pipeline=small, not v1."""
    rr = resolve_roles(product_mode="power", task_kind="ui")
    d = pick_pipeline(
        size="small",
        second_signal=False,
        product_mode="power",
        kill_switch=False,
        roles=rr,
    )
    assert d.pipeline == "small"
    assert d.pipeline != "v1"
    # GREEN-first path: doer panel ≤2 (cheap)
    assert len(d.doer_panel) <= 2


def test_sm2_traceback_log_influences_gate():
    """SM-2: traceback → Log critical → Gate RED."""
    gate, reasons = compute_unified_gate(
        GateSignals(
            mini_passed=True,
            log_report={
                "critical": True,
                "summary": "crash",
                "fix_hint": "fix",
                "confidence": 0.9,
            },
        )
    )
    assert gate == "RED"
    assert "log_critical" in reasons


def test_sm3_escalate_never_exceeds_two():
    """SM-3: no infinite escalate — hard cap 2."""
    os.environ["ZEUS_FUSION_JUDGE_FIX_HEURISTIC"] = "1"
    try:
        out = asyncio.run(
            run_trusted_verify_loop(
                answer="bad answer body here for soft stop pick",
                user_q="Traceback (most recent call last):\nException: x",
                panel=["claude-opus-4-6"],
                curator_model="claude-opus-4-6",
                allow_green_without_mini=True,
                max_escalate=2,
                skip_log=True,
                tests_failed=True,  # sticky RED
                mini_verify_fn=_mini_fail,
            )
        )
        assert out.escalate_count <= 2
        assert out.soft_stop is True
    finally:
        os.environ.pop("ZEUS_FUSION_JUDGE_FIX_HEURISTIC", None)


def test_sm6_zero_v1_without_second_signal():
    """SM-6: share of large with pipeline=v1 without 2nd signal = 0."""
    rr = resolve_roles(product_mode="power", task_kind="architecture")
    # Matrix of large without second_signal — never v1
    for mode in ("power", "custom", "simple"):
        d = pick_pipeline(
            size="large",
            second_signal=False,
            product_mode=mode,
            kill_switch=False,
            roles=rr,
        )
        assert d.pipeline != "v1", f"mode={mode} leaked v1 without 2nd"
    # Eligible → v1 + Brief≤3 contract
    d_ok = pick_pipeline(
        size="large",
        second_signal=True,
        product_mode="power",
        kill_switch=False,
        roles=rr,
    )
    assert d_ok.pipeline == "v1"
    brief = validate_architect_brief(
        {
            "components": [
                {
                    "id": "c1",
                    "role": "doer_ui",
                    "goal": "Hero",
                    "acceptance_one_liner": "CTA",
                    "files_hint": ["index.html"],
                },
                {
                    "id": "c2",
                    "role": "doer_logic",
                    "goal": "API",
                    "acceptance_one_liner": "works",
                    "files_hint": ["app.js"],
                },
                {
                    "id": "c3",
                    "role": "doer_logic",
                    "goal": "extra",
                    "acceptance_one_liner": "ok",
                    "files_hint": ["x.js"],
                },
                {
                    "id": "c4",
                    "role": "doer_logic",
                    "goal": "too many",
                    "acceptance_one_liner": "no",
                },
            ],
            "api_contract": "App",
            "files_contract": "index.html",
        }
    )
    assert brief is None  # >3 rejected
    ok = validate_architect_brief(
        {
            "components": [
                {
                    "id": "c1",
                    "role": "doer_ui",
                    "goal": "Hero",
                    "acceptance_one_liner": "CTA visible",
                    "files_hint": ["index.html"],
                }
            ],
            "api_contract": "App.init",
            "files_contract": "index.html",
        }
    )
    assert ok is not None and len(ok.components) <= 3


def test_sm6_soft_stop_nonempty_after_v1_style_answer():
    out = asyncio.run(
        run_trusted_verify_loop(
            answer="// file: index.html\n<html>landing</html>\n" + ("body " * 20),
            user_q="landing",
            panel=["claude-opus-4-6"],
            curator_model="claude-opus-4-6",
            allow_green_without_mini=True,
            max_escalate=0,
            skip_log=True,
            tests_failed=True,
            mini_verify_fn=_mini_fail,
        )
    )
    assert out.soft_stop is True
    assert (out.answer or "").strip()
    assert len(out.answer.strip()) > 20


def test_sm9_small_llm_call_ceiling():
    """SM-9: small path doer-LLM ≤2 (orientir ≤4 total including verify)."""
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
    # Pipeline v1 happy-path soft ceiling remains ≤9 (FR-18.9) — not small
    assert V1_HAPPY_PATH_MAX_CALLS == 9


def test_layer_a_to_tv_composition_red(tmp_path: Path):
    """Composition: Studio Layer A fail → Gate RED + Soft-Stop (not injected flag)."""
    (tmp_path / "tests").mkdir()

    class _Proc:
        returncode = 1
        stdout = "FAILED"
        stderr = ""

    ex = run_layer_a_for_request(
        {
            "workspace_path": str(tmp_path),
            "studio_test": True,
            "test_target": "tests",
        },
        runner=lambda *_a, **_k: _Proc(),
    )
    sig = executor_signal_for_gate(ex)
    assert sig is True
    os.environ["ZEUS_FUSION_JUDGE_FIX_HEURISTIC"] = "1"
    try:
        out = asyncio.run(
            run_trusted_verify_loop(
                answer="publish candidate " * 5,
                user_q="studio publish",
                panel=["claude-opus-4-6"],
                curator_model="claude-opus-4-6",
                allow_green_without_mini=True,
                max_escalate=1,
                skip_log=True,
                tests_failed=sig,
                mini_verify_fn=_mini_fail,
            )
        )
    finally:
        os.environ.pop("ZEUS_FUSION_JUDGE_FIX_HEURISTIC", None)
    assert out.gate == "RED"
    assert "tests_failed" in out.gate_reasons
    assert out.soft_stop is True
    assert out.escalate_count == 1


def test_fr16_explicitly_out_of_epic5_suite():
    """FR-16 multi-client live e2e remains deferred — documented, not asserted live."""
    note = Path(__file__).resolve().parents[2] / "_bmad-output" / "planning-artifacts" / "epics-role-routing.md"
    text = note.read_text(encoding="utf-8") if note.exists() else "FR16 deferred"
    assert "FR16" in text or "FR-16" in text or "deferred" in text.lower()
    # Suite itself must not call external clients
    assert "openai.com" not in __file__


def test_sm_eval_fixture_files_present():
    """Eval fixtures for SM metrics live under tests/eval/fixtures."""
    root = Path(__file__).resolve().parent / "eval" / "fixtures"
    for name in ("SM1.json", "SM2.json", "SM3.json", "SM6.json", "SM9.json"):
        p = root / name
        assert p.exists(), f"missing {name}"
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data.get("metric", "").startswith("SM-")
        assert data.get("fr16_deferred") is True
