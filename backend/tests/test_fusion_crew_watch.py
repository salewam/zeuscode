"""Crew-linked watch: Mini → Test Author → Opus Architect → Judge."""

from __future__ import annotations

import asyncio
import os

from app.fusion.roles import resolve_roles
from app.fusion.verify import run_trusted_verify_loop


def test_crew_watch_architect_reject_triggers_judge():
    os.environ["ZEUS_FUSION_WATCH_HEURISTIC"] = "1"
    os.environ["ZEUS_FUSION_JUDGE_FIX_HEURISTIC"] = "1"
    os.environ["ZEUS_FUSION_MINI_HEURISTIC"] = "1"
    try:
        rr = resolve_roles(product_mode="power", task_kind="code")

        async def mini(*, answer, user_q, model=None):
            class R:
                passed = True
                confidence = 0.95
                degraded = False
                reason = "ok"
                good_enough = True

            return R()

        # Mini passes (custom fn); short body → heuristic architect_watch fails
        r = asyncio.run(
            run_trusted_verify_loop(
                answer="ok stub",  # <40 chars → architect heuristic reject
                user_q="напиши функцию sum",
                panel=list(rr.stack),
                models_by_role=dict(rr.models_by_role),
                curator_model=rr.curator_model,
                allow_green_without_mini=False,
                mini_verify_fn=mini,
                max_escalate=1,
                crew_watch=True,
                task_kind="code",
                skip_log=True,
            )
        )
        roles = [getattr(b, "role", None) for b in r.branches]
        assert "architect" in roles or "judge_fix" in roles
        assert r.escalate_count >= 1 or "architect_watch" in (r.gate_reasons or [])
    finally:
        for k in (
            "ZEUS_FUSION_WATCH_HEURISTIC",
            "ZEUS_FUSION_JUDGE_FIX_HEURISTIC",
            "ZEUS_FUSION_MINI_HEURISTIC",
        ):
            os.environ.pop(k, None)


def test_light_no_crew_watch_even_if_flag():
    os.environ["ZEUS_FUSION_WATCH_HEURISTIC"] = "1"
    os.environ["ZEUS_FUSION_MINI_HEURISTIC"] = "1"
    try:
        rr = resolve_roles(product_mode="power", task_kind="light")

        async def mini(*, answer, user_q, model=None):
            class R:
                passed = True
                confidence = 0.99
                degraded = False
                reason = "ok"
                good_enough = True

            return R()

        r = asyncio.run(
            run_trusted_verify_loop(
                answer="привет! чем помочь?",
                user_q="привет",
                panel=list(rr.stack),
                models_by_role=dict(rr.models_by_role),
                curator_model=rr.curator_model,
                mini_verify_fn=mini,
                max_escalate=0,
                crew_watch=True,  # even if forced
                task_kind="light",
                skip_log=True,
            )
        )
        roles = [getattr(b, "role", None) for b in r.branches]
        assert "architect" not in roles
        assert "test_author" not in roles
        assert r.gate == "GREEN"
    finally:
        os.environ.pop("ZEUS_FUSION_WATCH_HEURISTIC", None)
        os.environ.pop("ZEUS_FUSION_MINI_HEURISTIC", None)
