"""Story 1.2 — FusionResult handoff + billable states."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.fusion import (
    BranchUsage,
    FusionResult,
    agents_to_branches,
    build_fusion_result,
    infer_billable_state,
    run_fusion,
    stack_to_path,
)
from app.routers.chat import _charge_amounts, _fusion_result_from_data


def test_stack_to_path_maps_brownfield():
    assert stack_to_path("fast") == "FAST"
    assert stack_to_path("full") == "FULL"
    assert stack_to_path("full-skip-judge") == "FULL"


def test_infer_billable_states():
    assert infer_billable_state({"ok": True, "prompt_tokens": 10, "completion_tokens": 5}) == (
        "completed"
    )
    assert infer_billable_state({"ok": False, "prompt_tokens": 0, "completion_tokens": 0}) == (
        "cancelled_no_tokens"
    )
    assert infer_billable_state({"ok": False, "prompt_tokens": 12, "completion_tokens": 0}) == (
        "cancelled_with_usage"
    )
    assert infer_billable_state({"ok": True, "partial": True, "prompt_tokens": 3}) == (
        "partial_stream"
    )
    assert (
        infer_billable_state({"billable_state": "cancelled_no_tokens", "ok": True})
        == "cancelled_no_tokens"
    )


def test_build_fusion_result_fields():
    agents = [
        {
            "role": "panel",
            "model": "deepseek-v4-flash",
            "ok": True,
            "prompt_tokens": 100,
            "completion_tokens": 20,
        },
        {
            "role": "panel",
            "model": "gemini-3-pro",
            "ok": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "billable_state": "cancelled_no_tokens",
        },
    ]
    fr = build_fusion_result(
        answer="hi",
        stack_mode="fast",
        routed_by="forced_fast",
        leader="deepseek-v4-flash",
        agents=agents,
        task_kind="light",
    )
    assert isinstance(fr, FusionResult)
    assert fr.path == "FAST"
    assert fr.policy_path == "FAST"
    assert fr.routed_by == "forced_fast"
    assert fr.leader == "deepseek-v4-flash"
    assert fr.trace_id
    states = {b.billable_state for b in fr.branches}
    assert "completed" in states
    assert "cancelled_no_tokens" in states


def test_charge_cancelled_no_tokens_is_zero():
    fr = FusionResult(
        path="FAST",
        policy_path="FAST",
        routed_by="forced_fast",
        phase="chat",
        complexity="light",
        leader="m1",
        branches=[
            BranchUsage(
                model_id="m1",
                billable_state="cancelled_no_tokens",
                prompt_tokens=0,
                completion_tokens=0,
            ),
            BranchUsage(
                model_id="m2",
                billable_state="cancelled_no_tokens",
                prompt_tokens=999,
                completion_tokens=999,
            ),
        ],
        answer="",
        trace_id="t1",
    )
    data = {"_fusion_result": fr, "usage": {"prompt_tokens": 999, "completion_tokens": 999}}
    upstream_cost, charged, prompt, completion = _charge_amounts(data, "deepseek-chat")
    assert charged == 0.0
    assert upstream_cost == 0.0
    assert prompt == 0
    assert completion == 0


def test_charge_from_fusion_result_not_token_heuristics():
    """Path/billing come from FusionResult branches — usage totals alone are ignored."""
    fr = FusionResult(
        path="FULL",
        policy_path="FULL",
        routed_by="legacy_full_alias",
        phase="implement",
        complexity="med",
        leader="m1",
        branches=[
            BranchUsage(
                model_id="deepseek-chat",
                billable_state="completed",
                prompt_tokens=10,
                completion_tokens=5,
            ),
        ],
        answer="ok",
        trace_id="t2",
    )
    data = {
        "_fusion_result": fr,
        # Misleading totals — Bill must not invent from these
        "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
        "onestack": {"agents": []},
    }
    _u, charged, prompt, completion = _charge_amounts(data, "deepseek-chat")
    assert prompt == 10
    assert completion == 5
    assert charged > 0
    assert _fusion_result_from_data(data) is fr


def test_agents_to_branches_roles():
    branches = agents_to_branches(
        [
            {
                "role": "judge",
                "model": "gemini-3.1-pro",
                "ok": True,
                "prompt_tokens": 1,
                "completion_tokens": 2,
            }
        ]
    )
    assert branches[0].role == "judge"
    assert branches[0].billable_state == "completed"


def test_run_fusion_attaches_fusion_result():
    async def _fake_chat(**kwargs):
        return {
            "choices": [{"message": {"content": "pong"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        }

    async def _run():
        with patch("app.fusion.upstream.chat_completions", new=AsyncMock(side_effect=_fake_chat)):
            data = await run_fusion(
                messages=[{"role": "user", "content": "привет"}],
                model_id="zeus/fusion-fast",
                show_thinking=False,
            )
        return data

    data = asyncio.run(_run())
    fr = data.get("_fusion_result")
    assert fr is not None
    assert getattr(fr, "path", None) == "FAST" or data["fusion_result"]["path"] == "FAST"
    onestack = data["onestack"]
    assert onestack["path"] == "FAST"
    assert onestack["routed_by"] == "legacy_fast_alias"
    assert "branches" in onestack
    assert onestack.get("trace_id")
