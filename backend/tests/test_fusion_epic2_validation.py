"""Epic 2 full validation — AC 2.1–2.5 + AD-3/5/11/15 gate checks."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

from app.fusion.panel import execute_cascade
from app.fusion.policy import (
    CLOSED_ROUTED_BY,
    bump_complexity,
    cascade_escalate_action,
    epic2_policy_enabled,
    mor_tip_escalate,
    next_leader_failover,
    resolve_custom_panel,
    resolve_request_policy,
    select_path_policy,
    ClassifyResult,
)
from app.fusion.verify import mini_verifier_passed, run_mini_verifier


def test_epic2_policy_default_on(monkeypatch):
    monkeypatch.delenv("ZEUS_FUSION_EPIC2_POLICY", raising=False)
    assert epic2_policy_enabled() is True
    monkeypatch.setenv("ZEUS_FUSION_EPIC2_POLICY", "0")
    assert epic2_policy_enabled() is False
    monkeypatch.setenv("ZEUS_FUSION_EPIC2_POLICY", "true")
    assert epic2_policy_enabled() is True


def test_effort_high_plus_one_no_floor():
    assert bump_complexity("light", "high") == "med"
    assert bump_complexity("med", "high") == "heavy"
    assert bump_complexity("heavy", "high") == "heavy"
    assert bump_complexity("light", "low") == "light"
    assert bump_complexity("med", "med") == "med"


def test_classify_fail_cascade_routed_by():
    d = select_path_policy(
        classify=ClassifyResult(
            classify_phase="chat",
            complexity_band="light",
            confidence=0.0,
            failed=True,
        ),
        effort="med",
        product_mode="power",
    )
    assert d.path == "CASCADE"
    assert d.routed_by == "classify_fallback_cascade"
    assert d.routed_by in CLOSED_ROUTED_BY


def test_simple_never_full_unless_forced():
    d = resolve_request_policy(
        user_q="спроектируй модуль auth",
        model_id="zeus/fusion",
        zeus={"mode": "simple"},
        clf_meta={
            "classify_phase": "plan",
            "complexity_band": "heavy",
            "confidence": 0.9,
        },
    )
    assert d.path == "CASCADE"
    assert d.routed_by == "mode_simple_clamp"


def test_kill_switch_fast():
    d = resolve_request_policy(
        user_q="heavy architecture",
        zeus={"kill_switch": True, "mode": "power"},
        clf_meta={"classify_phase": "plan", "complexity_band": "heavy", "confidence": 0.9},
    )
    assert d.path == "FAST"
    assert d.routed_by == "kill_switch"


def test_mor_tip_fast_only_by_default(monkeypatch):
    monkeypatch.delenv("ZEUS_FUSION_MOR_FULL_LADDER", raising=False)
    scores = {"s_quality": 0.9, "s_cost": 0.1, "s_latency": 0.2}
    assert mor_tip_escalate(scores, policy_path="FAST", kill_switch=False, forced_or_legacy=False) == 1
    assert mor_tip_escalate(scores, policy_path="CASCADE", kill_switch=False, forced_or_legacy=False) == 0
    monkeypatch.setenv("ZEUS_FUSION_MOR_FULL_LADDER", "1")
    assert mor_tip_escalate(scores, policy_path="CASCADE", kill_switch=False, forced_or_legacy=False) == 1


def test_mini_threshold_and_run_heuristic(monkeypatch):
    monkeypatch.setenv("ZEUS_FUSION_MINI_HEURISTIC", "1")
    r = asyncio.run(run_mini_verifier(answer="here is a solid fix for auth", user_q="fix auth"))
    assert r.passed is True
    assert r.threshold == 0.8
    bad = mini_verifier_passed({"good_enough": True, "confidence": 0.5, "reason": "x"})
    assert bad.passed is False


def test_cascade_escalate_map_and_failover():
    esc = cascade_escalate_action(
        kill_switch=False,
        product_mode="simple",
        complexity="med",
        phase="implement",
    )
    assert esc.action == "stronger_leader"
    assert esc.allow_full is False
    nxt = next_leader_failover(
        "deepseek-v4-flash",
        product_mode="simple",
        ready=["deepseek-v4-flash", "gemini-3-pro", "claude-haiku-4-5"],
    )
    assert nxt == "gemini-3-pro"
    assert next_leader_failover("claude-haiku-4-5", product_mode="simple", ready=[]) is None


def test_custom_panel_rules():
    one = resolve_custom_panel(["a"], ready=["a", "b", "c"])
    assert one.path_hint == "FAST" and one.models == ["a"]
    two = resolve_custom_panel(["a", "b", "dead"], ready=["a", "b"])
    assert two.path_hint == "CASCADE" and two.models == ["a", "b"]
    three = resolve_custom_panel(["a", "b", "c"], ready=["a", "b", "c"])
    assert three.path_hint == "FULL" and three.roles == ["A", "B", "C"]


def test_execute_cascade_mini_pass_and_failover():
    async def up(model_id, messages, *, temperature=None, max_tokens=None):
        if model_id == "dead-model":
            raise RuntimeError("down")
        return {
            "ok": True,
            "text": "fixed the button color to red properly",
            "prompt_tokens": 3,
            "completion_tokens": 5,
        }

    async def mini(*, answer, user_q):
        return mini_verifier_passed(
            {"good_enough": True, "confidence": 0.95, "reason": "ok"}
        )

    async def _run():
        return await execute_cascade(
            panel=["dead-model", "good-model"],
            leader="good-model",
            messages=[{"role": "user", "content": "fix button"}],
            user_q="fix button",
            product_mode="custom",
            complexity="light",
            phase="ui",
            ready=["dead-model", "good-model"],
            upstream_call=up,
            mini_verify_fn=mini,
        )

    out = asyncio.run(_run())
    assert out.path == "CASCADE"
    assert out.answer
    assert out.disaster is False
    assert out.routed_by == "policy_cascade_mini_pass"


def test_ad15_policy_returns_path_enum():
    d = resolve_request_policy(
        user_q="добавь кнопку",
        zeus={"mode": "power"},
        clf_meta={
            "classify_phase": "implement",
            "complexity_band": "light",
            "confidence": 0.8,
        },
    )
    assert d.path in ("FAST", "CASCADE", "RACE", "FULL")
    assert d.path == "CASCADE"
