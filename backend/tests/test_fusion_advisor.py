"""Read-only Advisor + plan artifact (omp-inspired)."""

from __future__ import annotations

import asyncio
import os

from app.fusion.advisor import (
    pick_advisor_model,
    run_advisor_pass,
    should_run_advisor,
)
from app.fusion.plan_artifact import (
    build_plan_artifact,
    extract_plan_artifact,
    plan_artifact_from_clarify_state,
)


def test_should_skip_simple_and_kill():
    assert (
        should_run_advisor(
            product_mode="simple",
            kill_switch=False,
            zeus={},
            answer="hello world answer long enough",
        )
        is False
    )
    assert (
        should_run_advisor(
            product_mode="power",
            kill_switch=True,
            zeus={},
            answer="hello world answer long enough",
        )
        is False
    )
    # Default off — opt-in via zeus.advisor
    assert (
        should_run_advisor(
            product_mode="power",
            kill_switch=False,
            zeus={},
            answer="hello world answer long enough",
        )
        is False
    )
    assert should_run_advisor(
        product_mode="power",
        kill_switch=False,
        zeus={"advisor": True},
        answer="hello world answer long enough",
    )


def test_pick_advisor_prefers_alias():
    mid = pick_advisor_model(
        stack=["claude-opus-4-8", "gpt-5.4", "deepseek-v4-pro"],
        model_aliases={"advisor": "gpt-5.4"},
        models_by_role={"judge_fix": "claude-opus-4-8"},
    )
    assert mid == "gpt-5.4"


def test_advisor_heuristic_blocker_short():
    os.environ["ZEUS_FUSION_ADVISOR_HEURISTIC"] = "1"
    try:
        r = asyncio.run(
            run_advisor_pass(
                answer="ok",
                user_q="сделай лендинг",
                model_id="deepseek-v4-pro",
            )
        )
        assert r.skipped is False
        assert r.severity == "blocker"
        assert r.note
    finally:
        os.environ.pop("ZEUS_FUSION_ADVISOR_HEURISTIC", None)


def test_advisor_never_rewrites_answer_contract():
    """AdvisorResult has no answer field — read-only by design."""
    os.environ["ZEUS_FUSION_ADVISOR_HEURISTIC"] = "1"
    try:
        r = asyncio.run(
            run_advisor_pass(
                answer="A" * 80,
                user_q="hi",
                model_id="deepseek-v4-pro",
            )
        )
        assert not hasattr(r, "answer") or not callable(getattr(r, "answer", None))
        assert "answer" not in r.to_dict()
        assert r.severity in ("nit", "concern", "blocker")
    finally:
        os.environ.pop("ZEUS_FUSION_ADVISOR_HEURISTIC", None)


def test_plan_artifact_build_and_extract():
    art = build_plan_artifact(
        content="1) hero\n2) form",
        spec_summary="— лендинг",
        title="СТО лендинг",
        original_goal="сайт для сто",
    )
    assert art["scheme"] == "zeus://plan"
    assert art["content"].startswith("1)")
    assert "plan.md" in art["id"]

    from_state = plan_artifact_from_clarify_state(
        {
            "dev_plan": "1) a\n2) b",
            "spec_summary": "spec",
            "original_goal": "goal",
        }
    )
    assert from_state["content"]

    got = extract_plan_artifact(
        zeus={"plan_artifact": art},
        clarify_state=None,
    )
    assert got["content"] == art["content"]
