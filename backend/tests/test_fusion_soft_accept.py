"""Soft-accept: Mini fail must not Soft-Stop a usable doer answer."""

from __future__ import annotations

import asyncio
import os

from app.fusion.verify import answer_looks_usable, run_trusted_verify_loop


def test_answer_looks_usable_css():
    assert answer_looks_usable(
        "```css\nbutton { color: red; }\n```",
        "поменяй цвет кнопки Submit на красный в CSS",
    )


def test_soft_accept_skips_judge_on_mini_fail():
    os.environ["ZEUS_FUSION_MINI_HEURISTIC"] = "1"
    try:

        async def mini(*, answer, user_q, model=None):
            class R:
                passed = False
                confidence = 0.1
                degraded = True
                reason = "strict"
                good_enough = False

            return R()

        css = (
            "```css\n.submit-btn { color: #ff0000; background: red; }\n```\n"
            "Кнопка Submit теперь красная."
        )
        r = asyncio.run(
            run_trusted_verify_loop(
                answer=css,
                user_q="поменяй цвет кнопки Submit на красный в CSS",
                panel=["deepseek-v4-pro", "claude-opus-4-6"],
                models_by_role={
                    "mini_verifier": "deepseek-v4-pro",
                    "judge_fix": "claude-opus-4-6",
                },
                curator_model="claude-opus-4-6",
                mini_verify_fn=mini,
                max_escalate=2,
                soft_accept=True,
                skip_log=True,
                task_kind="ui",
                crew_watch=False,
            )
        )
        assert r.gate == "GREEN"
        assert r.soft_stop is False
        assert "soft_accept_doer" in (r.gate_reasons or [])
        assert "⚠️" not in (r.answer or "")
        assert not any(getattr(b, "role", None) == "judge_fix" for b in r.branches)
    finally:
        os.environ.pop("ZEUS_FUSION_MINI_HEURISTIC", None)
