"""Epic 3 — rank-then-fuse + Structured Judge + anti-bias oracle."""

from __future__ import annotations

import asyncio

from app.fusion.judge import (
    ANTI_BIAS_OVERLAP,
    RANK_DELTA_FOR_K2,
    anti_bias_fails,
    rank_branches,
    rank_then_fuse_plan,
    run_structured_judge,
    select_top_k,
    token_overlap,
)


def test_top_k_uses_two_when_delta_large():
    ranked = rank_branches(
        [
            {
                "model_id": "a",
                "text": "alpha " * 40,
                "ok": True,
                "verifier_confidence": 0.95,
            },
            {
                "model_id": "b",
                "text": "beta " * 10,
                "ok": True,
                "verifier_confidence": 0.2,
            },
            {"model_id": "c", "text": "gamma", "ok": True, "verifier_confidence": 0.05},
        ]
    )
    top = select_top_k(ranked, delta=RANK_DELTA_FOR_K2)
    assert len(ranked) >= 3
    gap = ranked[0].score - ranked[2].score
    if gap >= RANK_DELTA_FOR_K2:
        assert len(top) == 2
    else:
        assert len(top) == 3


def test_top_k_uses_three_when_scores_close():
    texts = [
        "answer one with similar length and substance for ranking purposes xxx",
        "answer two with similar length and substance for ranking purposes yyy",
        "answer three with similar length and substance for ranking purposes zzz",
    ]
    ranked = rank_branches(
        [
            {"model_id": "a", "text": texts[0], "ok": True, "verifier_confidence": 0.5},
            {"model_id": "b", "text": texts[1], "ok": True, "verifier_confidence": 0.49},
            {"model_id": "c", "text": texts[2], "ok": True, "verifier_confidence": 0.48},
        ]
    )
    top = select_top_k(ranked)
    assert ranked[0].score - ranked[2].score < RANK_DELTA_FOR_K2
    assert len(top) == 3


def test_rank_then_fuse_plan_filters_failures():
    ranked, top = rank_then_fuse_plan(
        [
            {"model_id": "ok", "text": "good substantial answer here", "ok": True},
            {"model_id": "bad", "text": "", "ok": False},
        ]
    )
    assert [r.model_id for r in top] == ["ok"]
    assert ranked


def test_single_success_no_judge_call():
    calls = {"n": 0}

    async def boom(model, msgs):
        calls["n"] += 1
        raise AssertionError("Judge must not be called for single success")

    async def _run():
        ranked, top = rank_then_fuse_plan(
            [{"model_id": "only", "text": "sole survivor answer", "ok": True}]
        )
        return await run_structured_judge(
            top_k=top,
            user_q="q",
            judge_model="gemini-3.1-pro",
            call_fn=boom,
        )

    analysis = asyncio.run(_run())
    assert analysis.used_judge is False
    assert analysis.final_answer == "sole survivor answer"
    assert calls["n"] == 0


def test_structured_judge_emits_analysis_fields():
    async def judge_call(model, msgs):
        payload = """{
          "consensus": ["use JWT"],
          "contradictions": ["refresh vs session cookie"],
          "unique": ["branch B adds rate limit"],
          "blind_spots": ["no rotation policy"],
          "final_answer": "Use JWT with refresh rotation and rate limits."
        }"""
        return payload, 11, 22

    async def _run():
        _, top = rank_then_fuse_plan(
            [
                {
                    "model_id": "a",
                    "text": "Use JWT access tokens only for auth middleware.",
                    "ok": True,
                    "is_leader": True,
                },
                {
                    "model_id": "b",
                    "text": "Prefer session cookies and skip refresh tokens entirely.",
                    "ok": True,
                },
            ]
        )
        return await run_structured_judge(
            top_k=top,
            user_q="auth design",
            judge_model="gemini-3.1-pro",
            call_fn=judge_call,
        )

    analysis = asyncio.run(_run())
    assert analysis.used_judge
    assert analysis.consensus
    assert analysis.contradictions
    assert analysis.unique
    assert analysis.blind_spots
    assert "JWT" in analysis.final_answer
    assert analysis.prompt_tokens == 11


def test_anti_bias_oracle_fails_on_clone_with_contradictions():
    rank1 = "Alpha beta gamma delta epsilon zeta eta theta iota kappa"
    final = rank1
    assert token_overlap(final, rank1) >= ANTI_BIAS_OVERLAP
    assert anti_bias_fails(final, rank1, ["A says X", "B says Y"]) is True
    assert anti_bias_fails(final, rank1, []) is False
    other = "Completely different fused answer about cookies and CSRF tokens"
    assert anti_bias_fails(other, rank1, ["A says X"]) is False
