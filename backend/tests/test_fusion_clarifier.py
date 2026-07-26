"""Clarifier — pre-dev interview (ask → confirm → enriched → pipeline)."""

from __future__ import annotations

import asyncio
import os

from app.fusion.clarifier import (
    ClarifierState,
    apply_enriched_to_messages,
    is_approval,
    pick_clarifier_model,
    run_clarifier_turn,
    should_run_clarifier,
    user_wants_skip,
)
from app.fusion.roles import assign_role_model, resolve_roles


def test_should_skip_simple_kill_trivia():
    assert (
        should_run_clarifier(
            product_mode="simple",
            size="large",
            second_signal=True,
            kill_switch=False,
            zeus={},
            user_q="лендинг",
        )
        is False
    )
    assert (
        should_run_clarifier(
            product_mode="power",
            size="large",
            second_signal=True,
            kill_switch=True,
            zeus={},
            user_q="лендинг",
        )
        is False
    )
    assert (
        should_run_clarifier(
            product_mode="power",
            size="small",
            second_signal=False,
            kill_switch=False,
            zeus={},
            user_q="поменяй цвет кнопки",
        )
        is False
    )


def test_should_run_large_or_second_or_flag():
    assert should_run_clarifier(
        product_mode="power",
        size="large",
        second_signal=False,
        kill_switch=False,
        zeus={},
        user_q="big feature",
    )
    assert should_run_clarifier(
        product_mode="power",
        size="small",
        second_signal=True,
        kill_switch=False,
        zeus={},
        user_q="landing",
    )
    assert should_run_clarifier(
        product_mode="power",
        size="small",
        second_signal=False,
        kill_switch=False,
        zeus={"clarify": True},
        user_q="anything",
    )
    assert (
        should_run_clarifier(
            product_mode="power",
            size="large",
            second_signal=True,
            kill_switch=False,
            zeus={"clarify": False},
            user_q="landing",
        )
        is False
    )


def test_user_skip_phrases():
    assert user_wants_skip("без уточнений, сразу делай")
    assert user_wants_skip("сразу делай лендинг")
    assert is_approval("да")
    assert is_approval("утверждаю")
    assert not is_approval("да, но поменяй цвет")


def test_pick_clarifier_prefers_gemini():
    mid = pick_clarifier_model(
        ["claude-opus-4-6", "gemini-3-flash", "deepseek-v4-flash"]
    )
    assert mid == "gemini-3-flash"
    # custom without gemini → from stack
    mid2 = pick_clarifier_model(["claude-opus-4-6", "deepseek-v4-flash"])
    assert mid2 in ("claude-opus-4-6", "deepseek-v4-flash")


def test_roles_clarifier_gemini_on_power():
    rr = resolve_roles(product_mode="power", task_kind="architecture")
    a = assign_role_model("clarifier", "power", rr.stack)
    assert a.model_id is not None
    assert "gemini" in a.model_id


def test_ask_confirm_done_flow_heuristic():
    os.environ["ZEUS_FUSION_CLARIFIER_HEURISTIC"] = "1"
    try:
        stack = ["gemini-3-flash", "claude-opus-4-6"]
        # Turn 1: ask
        t1 = asyncio.run(
            run_clarifier_turn(
                user_q="Сделай лендинг для СТО",
                state=ClarifierState(),
                stack=stack,
                curator="claude-opus-4-6",
                session_id="sess-1",
            )
        )
        assert t1.halt is True
        assert t1.phase == "ask"
        assert len(t1.state.questions) >= 5
        assert "уточню" in t1.user_text.lower() or "1)" in t1.user_text

        # Turn 2: answers → confirm
        t2 = asyncio.run(
            run_clarifier_turn(
                user_q="1) заявки 2) автовладельцы 3) html 4) hero+услуги 5) синий 6) форма работает",
                state=t1.state,
                stack=stack,
                session_id="sess-1",
            )
        )
        assert t2.halt is True
        assert t2.phase == "confirm"
        assert t2.state.spec_summary
        assert "да" in t2.user_text.lower()

        # Turn 3: approve → done with enriched prompt
        t3 = asyncio.run(
            run_clarifier_turn(
                user_q="да",
                state=t2.state,
                stack=stack,
                session_id="sess-1",
            )
        )
        assert t3.halt is False
        assert t3.phase == "done"
        assert t3.meta.get("brief_approved") is True
        assert "ТЗ" in t3.user_text or "лендинг" in t3.user_text.lower()
        assert t3.state.enriched_prompt
    finally:
        os.environ.pop("ZEUS_FUSION_CLARIFIER_HEURISTIC", None)


def test_revisions_then_force_done():
    os.environ["ZEUS_FUSION_CLARIFIER_HEURISTIC"] = "1"
    try:
        st = ClarifierState(
            phase="confirm",
            original_goal="app",
            questions=["q1"],
            answers="a1",
            spec_summary="— old",
            enriched_prompt="old prompt",
            revision_count=0,
        )
        stack = ["gemini-3-flash"]
        t1 = asyncio.run(
            run_clarifier_turn(user_q="добавь тёмную тему", state=st, stack=stack)
        )
        assert t1.halt is True and t1.phase == "confirm"
        assert t1.state.revision_count == 1
        t2 = asyncio.run(
            run_clarifier_turn(
                user_q="ещё правки раз", state=t1.state, stack=stack
            )
        )
        assert t2.state.revision_count == 2
        t3 = asyncio.run(
            run_clarifier_turn(
                user_q="ещё раз правки", state=t2.state, stack=stack
            )
        )
        # 3rd revision exceeds MAX → forced done
        assert t3.halt is False
        assert t3.phase == "done"
        assert t3.meta.get("forced_after_revisions") is True
    finally:
        os.environ.pop("ZEUS_FUSION_CLARIFIER_HEURISTIC", None)


def test_apply_enriched_replaces_last_user():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "old"},
    ]
    out = apply_enriched_to_messages(msgs, "ENRICHED BRIEF")
    assert out[-1]["content"] == "ENRICHED BRIEF"
    assert out[0]["content"] == "sys"


def test_skip_phrase_on_fresh_skips_clarifier_gate():
    assert (
        should_run_clarifier(
            product_mode="power",
            size="large",
            second_signal=True,
            kill_switch=False,
            zeus={},
            user_q="без уточнений сделай лендинг",
        )
        is False
    )
