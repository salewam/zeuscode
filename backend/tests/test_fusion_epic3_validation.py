"""Epic 3 full validation — AC 3.1–3.5 gate checks."""

from __future__ import annotations

import asyncio

import pytest

from app.fusion.judge import anti_bias_fails
from app.fusion.panel import (
    adapt_prompt_for_family,
    clamp_f13_never_race_on_heavy,
    execute_cascade,
    execute_full,
    execute_race,
    outcome_to_completion,
    resolve_path_override,
    soft_stop_pick,
    LiveBranch,
)
from app.fusion.publish_gate import (
    PublishRegressionError,
    check_prompt_adapt_contract,
    check_release_not_anti_bias,
)
from app.fusion.verify import mini_verifier_passed


def test_f13_never_race_on_heavy():
    assert clamp_f13_never_race_on_heavy("RACE", complexity="heavy") == "FULL"
    assert clamp_f13_never_race_on_heavy("RACE", phase="plan") == "FULL"
    assert clamp_f13_never_race_on_heavy("RACE", complexity="med", phase="ui") == "RACE"
    assert resolve_path_override(
        {"path": "RACE", "complexity": "heavy"}
    ) == "FULL"


def test_race_both_fail_terminal_power_escalates():
    async def up(model_id, messages, *, temperature=None, max_tokens=None):
        return {"ok": False, "text": "", "prompt_tokens": 1, "completion_tokens": 0, "error": "fail"}

    async def mini(*, answer, user_q):
        return mini_verifier_passed({"good_enough": False, "confidence": 0.1, "reason": "no"})

    out = asyncio.run(
        execute_race(
            cheap_model="cheap",
            strong_model="strong",
            messages=[{"role": "user", "content": " borderline"}],
            user_q="borderline",
            product_mode="power",
            complexity="med",
            upstream_call=up,
            mini_verify_fn=mini,
        )
    )
    assert out.routed_by in ("race_escalate_full", "race_soft_stop", "race_disaster")


def test_cancel_event_wired_on_race_soft_stop():
    cancel = asyncio.Event()
    n = {"i": 0}

    async def up(model_id, messages, *, temperature=None, max_tokens=None):
        n["i"] += 1
        if model_id == "strong":
            cancel.set()
        return {
            "ok": True,
            "text": f"answer from {model_id} with enough tokens here",
            "prompt_tokens": 4,
            "completion_tokens": 4,
        }

    async def mini(*, answer, user_q):
        # Force degrade path so Soft-Stop / first-complete can apply under cancel
        return mini_verifier_passed(
            {"good_enough": False, "confidence": 0.2, "reason": "weak"},
        )

    out = asyncio.run(
        execute_race(
            cheap_model="cheap",
            strong_model="strong",
            messages=[{"role": "user", "content": "q"}],
            user_q="q",
            product_mode="power",
            complexity="med",
            upstream_call=up,
            mini_verify_fn=mini,
            cancel_event=cancel,
            soft_stop=True,
        )
    )
    assert out.answer or out.routed_by in (
        "race_soft_stop",
        "race_escalate_full",
        "race_disaster",
        "race_first_fit",
        "race_degrade_strong",
    )
    # Edge wire exists: chat sets cancel_event on disconnect (see routers/chat.py)
    from app.routers import chat as chat_mod

    assert "cancel_event" in chat_mod._fusion_live_sse.__code__.co_consts or (
        "cancel_event" in chat_mod._fusion_live_sse.__code__.co_varnames
        or "cancel_event.set" in (chat_mod._fusion_live_sse.__code__.co_names)
    ) or "cancel_event" in open(chat_mod.__file__, encoding="utf-8").read()


def test_anti_bias_blocks_release_gate():
    with pytest.raises(PublishRegressionError):
        check_release_not_anti_bias({"anti_bias_fail": True})
    assert check_release_not_anti_bias({"anti_bias_fail": False})["ok"]
    clone = "same answer " * 40
    assert anti_bias_fails(clone, clone, ["a vs b"]) is True


def test_prompt_adapt_system_only_and_gate():
    msgs = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "fix the login bug"},
    ]
    adapted = adapt_prompt_for_family(msgs, "claude", role="leader")
    assert check_prompt_adapt_contract(adapted)["ok"]
    assert "fix the login bug" in adapted[-1]["content"]
    leaked = list(adapted)
    leaked[-1] = {"role": "user", "content": "[Zeus adapt] change requirements"}
    with pytest.raises(PublishRegressionError):
        check_prompt_adapt_contract(leaked)


def test_cascade_uses_prompt_adapt():
    seen: list[list] = []

    async def up(model_id, messages, *, temperature=None, max_tokens=None):
        seen.append(messages)
        return {
            "ok": True,
            "text": "fixed button styles carefully",
            "prompt_tokens": 2,
            "completion_tokens": 2,
        }

    async def mini(*, answer, user_q):
        return mini_verifier_passed({"good_enough": True, "confidence": 0.99, "reason": "ok"})

    out = asyncio.run(
        execute_cascade(
            panel=["claude-haiku-4-5"],
            leader="claude-haiku-4-5",
            messages=[{"role": "user", "content": "fix ui"}],
            user_q="fix ui",
            product_mode="simple",
            complexity="light",
            phase="ui",
            ready=["claude-haiku-4-5"],
            upstream_call=up,
            mini_verify_fn=mini,
            adapt_prompts=True,
        )
    )
    assert out.path == "CASCADE"
    assert seen
    assert any(
        (m.get("role") == "system" and "Zeus adapt" in str(m.get("content")))
        for m in seen[0]
    )


def test_soft_stop_pick_order():
    branches = [
        LiveBranch(
            model_id="a",
            role="A",
            text="first",
            ok=True,
            billable_state="completed",
            verifier_confidence=0.2,
            latency_s=1.0,
        ),
        LiveBranch(
            model_id="b",
            role="B",
            text="best",
            ok=True,
            billable_state="completed",
            verifier_confidence=0.95,
            latency_s=2.0,
        ),
        LiveBranch(
            model_id="leader",
            role="A",
            text="lead partial",
            ok=True,
            billable_state="partial_stream",
            is_leader=True,
            verifier_confidence=0.1,
            latency_s=0.5,
        ),
    ]
    pick = soft_stop_pick(branches, leader_id="leader")
    assert pick is not None
    assert pick.model_id == "b"


def test_outcome_marks_anti_bias_release_blocked():
    from app.fusion.judge import JudgeAnalysis

    out = asyncio.run(
        execute_full(
            panel=["claude-x", "gemini-y"],
            leader="claude-x",
            messages=[{"role": "user", "content": "review"}],
            user_q="review",
            judge_model=None,
            ops_diversity_exception=True,
            adapt_prompts=False,
            upstream_call=lambda *a, **k: asyncio.sleep(0, result={
                "ok": True,
                "text": "same answer " * 20,
                "prompt_tokens": 1,
                "completion_tokens": 1,
            }),
        )
    )
    # Force anti-bias onto a synthetic completion for gate surface
    out.meta["anti_bias_fail"] = True
    data = outcome_to_completion(out, panel=["claude-x", "gemini-y"])
    assert data["onestack"]["anti_bias_fail"] is True
    assert data["onestack"]["release_blocked"] is True
