"""Story 1.3 — Onestack Path fields + legacy vs forced routed_by."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.fusion import resolve_routing, resolve_routing_ex, run_fusion, stack_to_path
from app.routers.chat import _sync_onestack_from_fusion_result


def test_legacy_alias_not_forced():
    stack, by = resolve_routing("zeus/fusion-fast", None, "отрефакторь всё")
    assert stack == "fast"
    assert by == "legacy_fast_alias"
    assert by != "forced_fast"

    stack, by = resolve_routing("zeus/fusion-full", None, "привет")
    assert stack == "full"
    assert by == "legacy_full_alias"
    assert by != "forced_full"


def test_zeus_mode_force_codes():
    assert resolve_routing("zeus/fusion", {"mode": "fast"}, "x") == ("fast", "forced_fast")
    assert resolve_routing("zeus/fusion", {"mode": "full"}, "x") == ("full", "forced_full")


def test_never_conflate_legacy_and_forced():
    _, legacy, _prod = resolve_routing_ex("zeus/fusion-fast", {"mode": "full"}, "привет")
    # Model-id alias wins over zeus.mode in brownfield resolve order
    assert legacy == "legacy_fast_alias"
    _, forced, _ = resolve_routing_ex("zeus/fusion", {"mode": "full"}, "привет")
    assert forced == "forced_full"
    assert legacy != forced


async def _run_mocked(*, model_id: str, zeus: dict | None = None):
    async def _fake_chat(**kwargs):
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1},
        }

    with patch("app.fusion.upstream.chat_completions", new=AsyncMock(side_effect=_fake_chat)):
        return await run_fusion(
            messages=[{"role": "user", "content": "привет"}],
            model_id=model_id,
            zeus=zeus,
            show_thinking=False,
        )


def test_onestack_path_fields_legacy_fast():
    data = asyncio.run(_run_mocked(model_id="zeus/fusion-fast"))
    os_ = data["onestack"]
    assert os_["path"] == "FAST"
    assert os_["policy_path"] == "FAST"
    assert os_.get("escalate_from") is None
    assert os_["routed_by"] == "legacy_fast_alias"
    assert "fusion_mode" in os_  # legacy bridge retained
    assert os_["fusion_mode"] == "fast"


def test_onestack_path_fields_forced_full():
    data = asyncio.run(_run_mocked(model_id="zeus/fusion", zeus={"mode": "full"}))
    os_ = data["onestack"]
    assert os_["path"] == "FULL"
    assert os_["policy_path"] == "FULL"
    assert os_["routed_by"] == "forced_full"
    assert os_["routed_by"] != "legacy_full_alias"


def test_sync_onestack_prefers_fusion_result_path():
    from app.fusion import FusionResult, BranchUsage

    data = {
        "onestack": {
            "path": "INVENTED",
            "routed_by": "auto",
            "fusion_mode": "fast",
        },
        "_fusion_result": FusionResult(
            path="CASCADE",
            policy_path="FAST",
            routed_by="cascade_escalate_stronger",
            phase="implement",
            complexity="med",
            leader="m1",
            branches=[
                BranchUsage(
                    model_id="m1",
                    billable_state="completed",
                    prompt_tokens=1,
                    completion_tokens=1,
                )
            ],
            answer="a",
            trace_id="tr",
            escalate_from="FAST",
        ),
    }
    _sync_onestack_from_fusion_result(data)
    assert data["onestack"]["path"] == "CASCADE"
    assert data["onestack"]["policy_path"] == "FAST"
    assert data["onestack"]["escalate_from"] == "FAST"
    assert data["onestack"]["routed_by"] == "cascade_escalate_stronger"
    assert stack_to_path("fast") == "FAST"
