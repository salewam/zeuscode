"""Epic 1 full validation — AC + AD-6/8/10/14/15/17 gate checks."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.fusion import (
    BranchUsage,
    FusionResult,
    build_fusion_result,
    fusion_result_to_dict,
    prepare_messages_for_policy,
    run_fusion,
    scrub_secrets,
    stack_to_path,
)
from app.fusion.brief import build_satellite_brief
from app.routers.chat import _charge_amounts, _is_fusion_completion

_FUSION_ROOT = Path(__file__).resolve().parents[1] / "app" / "fusion"


def test_ad6_fusion_package_no_routers_import():
    bad: list[str] = []
    for path in _FUSION_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app.routers") or alias.name == "routers":
                        bad.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.startswith("app.routers") or mod == "routers":
                    bad.append(f"{path.name}: from {mod}")
    assert not bad, bad
    assert not (_FUSION_ROOT.parent / "fusion.py").exists()


def test_ad14_branch_shape_has_model_and_usage():
    fr = build_fusion_result(
        answer="x",
        stack_mode="fast",
        routed_by="forced_fast",
        leader="m1",
        agents=[{"role": "panel", "model": "m1", "ok": True, "prompt_tokens": 2, "completion_tokens": 3}],
        serving_path="FAST",
    )
    d = fusion_result_to_dict(fr)
    b = d["branches"][0]
    assert b["model"] == "m1"
    assert b["usage"] == {"prompt_tokens": 2, "completion_tokens": 3}
    assert BranchUsage(model_id="m1", billable_state="completed").model == "m1"


def test_ad14_no_agents_only_charge_for_fusion():
    """Fusion payload without FR must not bill via inflated agents rows."""
    data = {
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        "onestack": {
            "fusion_mode": "full",
            "path": "FULL",
            "agents": [
                {
                    "model": "deepseek-chat",
                    "prompt_tokens": 99999,
                    "completion_tokens": 99999,
                    "billable_state": "completed",
                }
            ],
        },
    }
    assert _is_fusion_completion(data)
    _u, charged, prompt, completion = _charge_amounts(data, "deepseek-chat")
    assert prompt == 10
    assert completion == 5
    # Must be far below agents-only inflation
    assert charged < estimate_ceiling()


def estimate_ceiling() -> float:
    from app.cost import estimate_user_rub

    return estimate_user_rub("deepseek-chat", 500, 500)


def test_ad15_serving_path_is_path_enum_not_stack():
    fr = build_fusion_result(
        answer="ok",
        stack_mode="fast",
        routed_by="legacy_fast_alias",
        leader="m1",
        agents=[{"role": "panel", "model": "m1", "ok": True, "prompt_tokens": 1, "completion_tokens": 1}],
        serving_path="CASCADE",
        policy_path="CASCADE",
    )
    assert fr.path == "CASCADE"
    assert fr.policy_path == "CASCADE"
    assert stack_to_path("fast") == "FAST"


def test_ad15_onestack_path_authoritative_after_run():
    async def _fake(**_k):
        return {
            "choices": [{"message": {"content": "pong"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    async def _run():
        with patch("app.fusion._monolith.upstream.chat_completions", new=AsyncMock(side_effect=_fake)):
            return await run_fusion(
                messages=[{"role": "user", "content": "привет"}],
                model_id="zeus/fusion-fast",
                show_thinking=False,
            )

    data = asyncio.run(_run())
    os_ = data["onestack"]
    assert os_["path"] in ("FAST", "CASCADE", "RACE", "FULL")
    assert os_["stack_size"] in ("fast", "full")
    # stack_size is Edge bridge; serving is path
    assert os_["path"] != os_["stack_size"]
    assert os_["path"] == "FAST"
    assert os_["stack_size"] == "fast"


def test_ad17_scrub_once_prepare_messages():
    raw = "token sk-abcdefghijklmnopqrstuvwx and bearer Bearer SECRETTOKEN123"
    msgs = [{"role": "user", "content": raw}]
    once = prepare_messages_for_policy(msgs)
    twice = prepare_messages_for_policy(once)
    assert once[0]["content"] == twice[0]["content"]
    assert "sk-abcdefghijklmnopqrstuvwx" not in once[0]["content"]
    assert scrub_secrets(once[0]["content"]) == once[0]["content"]


def test_ad17_brief_contract_only_three_fields():
    brief = build_satellite_brief(
        [
            {"role": "system", "content": "HUGE CURSOR DUMP " * 50},
            {"role": "assistant", "content": "prev ok\nValueError: boom"},
            {"role": "user", "content": "fix auth"},
        ]
    )
    d = brief.as_dict()
    assert set(d.keys()) == {"last_assistant", "errors", "goal"}
    assert "HUGE CURSOR DUMP" not in brief.as_prompt_block()
    assert "fix auth" in d["goal"]


def test_ad8_cancelled_still_zero():
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
                prompt_tokens=50,
                completion_tokens=50,
            )
        ],
        answer="",
        trace_id="v",
    )
    _u, charged, p, c = _charge_amounts({"_fusion_result": fr}, "deepseek-chat")
    assert charged == 0.0 and p == 0 and c == 0
