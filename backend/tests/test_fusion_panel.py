"""Epic 3 — RACE/FULL panel, Soft-Stop, Aspects, prompt adapt (mocked upstream)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from app.fusion.panel import (
    LiveBranch,
    PanelDiversityError,
    adapt_prompt_for_family,
    assert_panel_diversity,
    billable_for_branch,
    build_satellite_brief,
    execute_full,
    execute_race,
    extract_brief_parts,
    model_family,
    race_both_fail_terminal,
    soft_stop_pick,
)
from app.fusion.verify import (
    AspectBundle,
    AspectVerdict,
    aspects_block_tau_exit,
    near_duplicate_among,
    run_aspect_verifiers_v1,
)


@dataclass
class _Mini:
    good_enough: bool
    confidence: float
    reason: str = ""
    passed: bool = False
    degraded: bool = False

    def __post_init__(self) -> None:
        if not self.passed and self.good_enough and self.confidence >= 0.8:
            self.passed = True


def _upstream_factory(answers: dict[str, str], *, tokens: int = 10):
    async def _call(model, messages, **kwargs):
        text = answers.get(model, "")
        return {
            "ok": bool(text.strip()),
            "text": text,
            "prompt_tokens": tokens if text else 0,
            "completion_tokens": tokens if text else 0,
        }

    return _call


def test_race_first_fit_cancels_loser():
    async def mini(*, answer, user_q):
        ok = "STRONG" in answer
        return _Mini(good_enough=ok, confidence=0.9 if ok else 0.2, passed=ok)

    async def _run():
        return await execute_race(
            cheap_model="deepseek-v4-flash",
            strong_model="claude-opus-4-8",
            messages=[{"role": "user", "content": "fix the bug in auth"}],
            user_q="fix the bug in auth",
            product_mode="power",
            complexity="med",
            mini_verify_fn=mini,
            upstream_call=_upstream_factory(
                {
                    "deepseek-v4-flash": "CHEAP ok answer with enough text here",
                    "claude-opus-4-8": "STRONG ok answer with enough text here",
                }
            ),
            adapt_prompts=False,
        )

    out = asyncio.run(_run())
    assert out.path == "RACE"
    assert "STRONG" in out.answer
    states = {b.model_id: b.billable_state for b in out.branches}
    assert states.get("claude-opus-4-8") == "completed"
    assert states.get("deepseek-v4-flash") in {
        "cancelled_with_usage",
        "cancelled_no_tokens",
        "partial_stream",
    }


def test_race_both_fail_escalates_full_for_power_med():
    async def mini(*, answer, user_q):
        return _Mini(good_enough=False, confidence=0.1, passed=False)

    async def _run():
        return await execute_race(
            cheap_model="deepseek-v4-flash",
            strong_model="claude-opus-4-8",
            messages=[{"role": "user", "content": "borderline"}],
            user_q="borderline",
            product_mode="power",
            complexity="med",
            mini_verify_fn=mini,
            upstream_call=_upstream_factory(
                {
                    "deepseek-v4-flash": "weak cheap reply that fails verifier checks xx",
                    "claude-opus-4-8": "weak strong reply that fails verifier checks xx",
                }
            ),
            adapt_prompts=False,
        )

    out = asyncio.run(_run())
    assert out.routed_by == "race_escalate_full"
    assert out.path == "FULL"
    assert out.escalate_from == "RACE"


def test_race_both_fail_simple_soft_stop_terminal():
    branches = [
        LiveBranch(
            model_id="cheap",
            role="cheap",
            text="partial cheap",
            ok=True,
            billable_state="partial_stream",
            prompt_tokens=5,
            completion_tokens=5,
            verifier_confidence=0.4,
        ),
        LiveBranch(
            model_id="strong",
            role="strong",
            text="",
            ok=False,
            billable_state="cancelled_no_tokens",
            is_leader=True,
        ),
    ]
    out = race_both_fail_terminal(
        product_mode="simple",
        complexity="med",
        branches=branches,
        leader_id="strong",
    )
    assert out.routed_by == "race_soft_stop"
    assert out.answer == "partial cheap"


def test_race_disaster_when_no_partial():
    branches = [
        LiveBranch(
            model_id="cheap",
            role="cheap",
            billable_state="cancelled_no_tokens",
        ),
        LiveBranch(
            model_id="strong",
            role="strong",
            billable_state="cancelled_no_tokens",
            is_leader=True,
        ),
    ]
    out = race_both_fail_terminal(
        product_mode="simple",
        complexity="light",
        branches=branches,
        leader_id="strong",
    )
    assert out.disaster and out.routed_by == "race_disaster"


def test_panel_diversity_blocks_same_family():
    with pytest.raises(PanelDiversityError):
        assert_panel_diversity(
            ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat"]
        )
    fams = assert_panel_diversity(
        ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat"],
        ops_exception=True,
    )
    assert set(fams.values()) == {"deepseek"}


def test_brief_contains_goal_last_assistant_errors_not_full_history():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "old turn 1 " * 200},
        {"role": "assistant", "content": "prev answer with Traceback: boom"},
        {"role": "user", "content": "refactor the auth module please"},
    ]
    parts = extract_brief_parts(messages, "refactor the auth module please")
    assert "auth" in parts["goal"]
    assert "prev answer" in parts["last_assistant"]
    assert "Traceback" in parts["errors"]
    brief = build_satellite_brief(messages, "refactor the auth module please")
    blob = " ".join(str(m.get("content")) for m in brief)
    assert "old turn 1" not in blob
    assert "Goal" in blob


def test_full_aspects_before_tau_must_fail_blocks_exit():
    # Identical clones would hit τ — Aspects must still run first and can block τ exit.
    clone = (
        "Implement auth middleware with JWT validation, refresh tokens, "
        "and clear error handling for expired sessions in the API gateway layer."
    )
    assert near_duplicate_among([clone, clone])[0]

    async def aspect_fail(messages):
        return '{"pass": false, "confidence": 0.9, "reason": "missing tests"}'

    async def _run():
        return await execute_full(
            panel=["claude-opus-4-8", "deepseek-v4-pro", "gemini-3.1-pro"],
            leader="claude-opus-4-8",
            messages=[{"role": "user", "content": "design auth middleware with JWT"}],
            user_q="design auth middleware with JWT refresh and error handling",
            judge_model="gemini-3.1-pro",
            upstream_call=_upstream_factory(
                {
                    "claude-opus-4-8": clone,
                    "deepseek-v4-pro": clone,
                    "gemini-3.1-pro": clone,
                }
            ),
            aspect_call=aspect_fail,
            adapt_prompts=False,
        )

    out = asyncio.run(_run())
    assert out.early_exit != "near_duplicate"
    assert out.aspects is not None and out.aspects.must_fail
    assert aspects_block_tau_exit(out.aspects)
    assert out.judge is not None or out.routed_by in {
        "full_judge",
        "full_local_fuse",
    }


def test_full_near_duplicate_early_exit_when_aspects_pass():
    text = (
        "Here is a complete landing page structure with hero, features, pricing, "
        "and a contact form implemented in semantic HTML and accessible markup."
    )

    async def _run():
        return await execute_full(
            panel=["claude-opus-4-8", "deepseek-v4-pro", "gemini-3.1-pro"],
            leader="claude-opus-4-8",
            messages=[
                {
                    "role": "user",
                    "content": "make a landing page with hero features pricing",
                }
            ],
            user_q="make a landing page with hero features pricing contact",
            judge_model=None,
            upstream_call=_upstream_factory(
                {
                    "claude-opus-4-8": text,
                    "deepseek-v4-pro": text,
                    "gemini-3.1-pro": text,
                }
            ),
            adapt_prompts=False,
        )

    out = asyncio.run(_run())
    assert out.early_exit == "near_duplicate"
    assert out.routed_by == "full_near_duplicate"
    assert out.judge is None


def test_full_single_success_skips_judge():
    async def _run():
        return await execute_full(
            panel=["claude-opus-4-8", "deepseek-v4-pro", "gemini-3.1-pro"],
            leader="claude-opus-4-8",
            messages=[{"role": "user", "content": "hello task"}],
            user_q="hello task with enough detail for a real coding answer",
            judge_model="gemini-3.1-pro",
            upstream_call=_upstream_factory(
                {
                    "claude-opus-4-8": (
                        "Only leader survived with a substantial coding answer about "
                        "refactoring the router and adding tests for edge cases."
                    ),
                    "deepseek-v4-pro": "",
                    "gemini-3.1-pro": "",
                }
            ),
            adapt_prompts=False,
        )

    out = asyncio.run(_run())
    assert out.early_exit == "single_success"
    assert out.judge is None
    assert "Only leader" in out.answer


def test_soft_stop_pick_order_and_cancel_states():
    async def _run():
        cancel = asyncio.Event()
        started = asyncio.Event()

        async def slow_call(model, messages, **kwargs):
            started.set()
            await asyncio.sleep(0.05)
            if cancel.is_set():
                return {
                    "ok": True,
                    "text": f"partial from {model} with useful content for the user",
                    "prompt_tokens": 3,
                    "completion_tokens": 4,
                }
            return {
                "ok": True,
                "text": f"full from {model} with useful content for the user review",
                "prompt_tokens": 8,
                "completion_tokens": 12,
            }

        async def trip():
            await started.wait()
            await asyncio.sleep(0.01)
            cancel.set()

        tripper = asyncio.create_task(trip())
        out = await execute_full(
            panel=["claude-opus-4-8", "deepseek-v4-pro", "gemini-3.1-pro"],
            leader="claude-opus-4-8",
            messages=[{"role": "user", "content": "architecture review please"}],
            user_q="architecture review please",
            cancel_event=cancel,
            soft_stop=False,
            upstream_call=slow_call,
            adapt_prompts=False,
        )
        await tripper
        return out

    out = asyncio.run(_run())
    assert out.early_exit == "soft_stop"
    assert out.answer
    for b in out.branches:
        assert b.billable_state in {
            "completed",
            "partial_stream",
            "cancelled_no_tokens",
            "cancelled_with_usage",
        }
        if b.billable_state == "cancelled_no_tokens":
            assert b.prompt_tokens + b.completion_tokens == 0


def test_soft_stop_pick_prefers_verifier_confidence():
    branches = [
        LiveBranch(
            model_id="a",
            role="A",
            text="first",
            billable_state="completed",
            verifier_confidence=0.2,
            latency_s=0.1,
        ),
        LiveBranch(
            model_id="b",
            role="B",
            text="best",
            billable_state="completed",
            verifier_confidence=0.9,
            latency_s=0.5,
        ),
        LiveBranch(
            model_id="leader",
            role="A",
            text="leader partial",
            billable_state="partial_stream",
            is_leader=True,
            verifier_confidence=0.1,
        ),
    ]
    pick = soft_stop_pick(branches, leader_id="leader")
    assert pick is not None and pick.model_id == "b"


def test_prompt_adaptation_touches_system_only():
    messages = [
        {"role": "system", "content": "Base system"},
        {"role": "user", "content": "Do not change this requirement: add dark mode"},
    ]
    out = adapt_prompt_for_family(messages, "claude", role="leader")
    user = [m for m in out if m["role"] == "user"][0]
    assert user["content"] == messages[1]["content"]
    sys = [m for m in out if m["role"] == "system"][0]
    assert "[Zeus adapt]" in sys["content"]
    assert "Base system" in sys["content"]


def test_billable_cancelled_no_tokens_not_chargable_signal():
    assert (
        billable_for_branch(
            ok=False, prompt_tokens=0, completion_tokens=0, text="", cancelled=True
        )
        == "cancelled_no_tokens"
    )
    assert (
        billable_for_branch(
            ok=False, prompt_tokens=2, completion_tokens=0, text="", cancelled=True
        )
        == "cancelled_with_usage"
    )


def test_model_family_heuristic():
    assert model_family("claude-opus-4-8") == "claude"
    assert model_family("gemini-3.1-pro") == "gemini"
    assert model_family("deepseek-v4-pro") == "deepseek"


def test_aspect_bundle_must_fail_property():
    bundle = AspectBundle(
        verdicts=[
            AspectVerdict(aspect="correctness", passed=True, must=True),
            AspectVerdict(aspect="completeness", passed=False, must=True),
        ]
    )
    assert bundle.must_fail

    async def _run():
        return await run_aspect_verifiers_v1(
            answer=(
                "Complete solution covering architecture, API routes, auth middleware, "
                "and tests for the refactor request."
            ),
            user_q="architecture API routes auth middleware refactor tests",
        )

    ok = asyncio.run(_run())
    assert ok.all_passed or not ok.must_fail
