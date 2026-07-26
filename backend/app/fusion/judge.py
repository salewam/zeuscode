"""Rank-then-fuse Structured Judge (Epic 3)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .verify import tokenize, token_jaccard

# FR-10 assumptions
RANK_DELTA_FOR_K2 = 0.15
# FR-13 anti-bias oracle
ANTI_BIAS_OVERLAP = 0.95


@dataclass
class RankedBranch:
    model_id: str
    text: str
    score: float
    is_leader: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class JudgeAnalysis:
    consensus: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    unique: list[str] = field(default_factory=list)
    blind_spots: list[str] = field(default_factory=list)
    final_answer: str = ""
    used_judge: bool = False
    top_k: list[RankedBranch] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_id: str | None = None
    anti_bias_fail: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


def score_branch(
    text: str,
    *,
    verifier_confidence: float = 0.0,
    is_leader: bool = False,
    ok: bool = True,
    latency_s: float = 0.0,
) -> float:
    """Local rank score — not Leader self-evaluation as an exit gate."""
    if not ok or not (text or "").strip():
        return -1.0
    length = len((text or "").strip())
    length_term = min(0.35, length / 8000.0)
    conf_term = max(0.0, min(1.0, verifier_confidence)) * 0.45
    leader_term = 0.08 if is_leader else 0.0
    # Mild latency preference (faster slightly higher) without dominating.
    lat_term = 0.05 * max(0.0, 1.0 - min(latency_s, 30.0) / 30.0)
    return round(0.12 + length_term + conf_term + leader_term + lat_term, 4)


def rank_branches(
    branches: list[dict[str, Any]] | list[RankedBranch],
) -> list[RankedBranch]:
    ranked: list[RankedBranch] = []
    for b in branches:
        if isinstance(b, RankedBranch):
            ranked.append(b)
            continue
        text = str(b.get("text") or "")
        ok = bool(b.get("ok", True)) and bool(text.strip())
        scored = score_branch(
            text,
            verifier_confidence=float(b.get("verifier_confidence") or 0.0),
            is_leader=bool(b.get("is_leader")),
            ok=ok,
            latency_s=float(b.get("latency_s") or 0.0),
        )
        ranked.append(
            RankedBranch(
                model_id=str(b.get("model_id") or b.get("model") or ""),
                text=text,
                score=scored,
                is_leader=bool(b.get("is_leader")),
                meta=dict(b.get("meta") or {}),
            )
        )
    ranked.sort(key=lambda r: (r.score, 1 if r.is_leader else 0), reverse=True)
    return ranked


def select_top_k(
    ranked: list[RankedBranch],
    *,
    delta: float = RANK_DELTA_FOR_K2,
) -> list[RankedBranch]:
    """K=2 if rank-1 − rank-3 ≥ Δ else top-3 (FR-10)."""
    usable = [r for r in ranked if r.score >= 0 and (r.text or "").strip()]
    if not usable:
        return []
    if len(usable) == 1:
        return usable[:1]
    if len(usable) == 2:
        return usable[:2]
    gap = usable[0].score - usable[2].score
    if gap >= delta:
        return usable[:2]
    return usable[:3]


def token_overlap(a: str, b: str) -> float:
    """Primary anti-bias metric (token overlap / Jaccard)."""
    return token_jaccard(a, b)


def anti_bias_fails(
    final_answer: str,
    rank1_text: str,
    contradictions: list[str] | None,
    *,
    threshold: float = ANTI_BIAS_OVERLAP,
) -> bool:
    """True when PR should fail: non-empty contradictions and overlap ≥ 0.95."""
    if not contradictions:
        return False
    # Ignore empty / whitespace-only contradiction rows
    real = [c for c in contradictions if (c or "").strip()]
    if not real:
        return False
    return token_overlap(final_answer or "", rank1_text or "") >= threshold


_JUDGE_SYSTEM = """You are the Structured Judge in Zeus Fusion.
Given independent panel answers, produce ONE final user-facing answer AND a short analysis.

Respond as JSON only:
{
  "consensus": ["..."],
  "contradictions": ["..."],
  "unique": ["..."],
  "blind_spots": ["..."],
  "final_answer": "..."
}

Rules:
- Resolve contradictions; do not clone the strongest branch blindly.
- final_answer is what the user sees (same language as the ask).
- If branches mostly agree, keep fuse short.
- No meta preamble outside JSON.
"""


def _extract_json_obj(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _as_str_list(val: Any) -> list[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x) for x in val if str(x).strip()]
    if isinstance(val, str) and val.strip():
        return [val.strip()]
    return []


def _local_fuse(top_k: list[RankedBranch], user_q: str) -> JudgeAnalysis:
    """Deterministic fallback when Judge LLM is unavailable."""
    if not top_k:
        return JudgeAnalysis(final_answer="", used_judge=False)
    if len(top_k) == 1:
        return JudgeAnalysis(
            consensus=["single_branch"],
            final_answer=top_k[0].text.strip(),
            used_judge=False,
            top_k=top_k,
        )
    # Cheap structural analysis without cloning blindly when texts diverge.
    j = token_jaccard(top_k[0].text, top_k[1].text)
    contradictions: list[str] = []
    consensus: list[str] = []
    if j >= 0.85:
        consensus.append("branches_mostly_agree")
        final = top_k[0].text.strip()
    else:
        contradictions.append("branch_approaches_diverge")
        # Prefer leader if present among top-K, else rank-1, but stitch unique bits.
        leader = next((r for r in top_k if r.is_leader), top_k[0])
        extra = []
        lead_tok = tokenize(leader.text)
        for r in top_k:
            if r is leader:
                continue
            uniq = sorted(tokenize(r.text) - lead_tok)
            if uniq[:8]:
                extra.append(" ".join(uniq[:8]))
        final = leader.text.strip()
        if extra and j < 0.5:
            final = final + "\n\n—\nДополнения из других веток: " + "; ".join(extra[:3])
    unique = []
    for r in top_k[1:]:
        unique.append(f"{r.model_id}:distinct")
    analysis = JudgeAnalysis(
        consensus=consensus,
        contradictions=contradictions,
        unique=unique,
        blind_spots=[],
        final_answer=final,
        used_judge=False,
        top_k=top_k,
        meta={"fuse": "local", "user_q_len": len(user_q or "")},
    )
    analysis.anti_bias_fail = anti_bias_fails(
        analysis.final_answer, top_k[0].text, analysis.contradictions
    )
    return analysis


async def run_structured_judge(
    *,
    top_k: list[RankedBranch],
    user_q: str,
    judge_model: str | None,
    call_fn: Any | None = None,
) -> JudgeAnalysis:
    """Run Structured Judge on top-K. 1 success handled by caller (no Judge)."""
    if not top_k:
        return JudgeAnalysis(final_answer="", used_judge=False)
    if len(top_k) == 1:
        return JudgeAnalysis(
            consensus=["single_success"],
            final_answer=top_k[0].text.strip(),
            used_judge=False,
            top_k=top_k,
        )

    if call_fn is None or not judge_model:
        return _local_fuse(top_k, user_q)

    blocks = []
    for i, r in enumerate(top_k):
        label = "A" if i == 0 else ("B" if i == 1 else "C")
        budget = 10000 if r.is_leader else 6000
        blocks.append(f"### Variant {label} ({r.model_id})\n{r.text[:budget]}")
    user_msg = (
        f"User ask:\n{(user_q or '')[:4000]}\n\n"
        f"Panel variants (ranked, top-{len(top_k)}):\n\n" + "\n\n".join(blocks)
    )
    try:
        raw = await call_fn(
            judge_model,
            [
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
        )
        if isinstance(raw, tuple):
            text, pt, ct = raw[0], int(raw[1] or 0), int(raw[2] or 0)
        else:
            text, pt, ct = str(raw or ""), 0, 0
        data = _extract_json_obj(str(text))
        if not data or not str(data.get("final_answer") or "").strip():
            fb = _local_fuse(top_k, user_q)
            fb.meta["judge_degrade"] = "parse_or_empty"
            return fb
        analysis = JudgeAnalysis(
            consensus=_as_str_list(data.get("consensus")),
            contradictions=_as_str_list(data.get("contradictions")),
            unique=_as_str_list(data.get("unique")),
            blind_spots=_as_str_list(data.get("blind_spots")),
            final_answer=str(data.get("final_answer") or "").strip(),
            used_judge=True,
            top_k=top_k,
            prompt_tokens=pt,
            completion_tokens=ct,
            model_id=judge_model,
        )
        analysis.anti_bias_fail = anti_bias_fails(
            analysis.final_answer, top_k[0].text, analysis.contradictions
        )
        return analysis
    except Exception as e:  # noqa: BLE001
        fb = _local_fuse(top_k, user_q)
        fb.meta["judge_degrade"] = str(e)[:200]
        return fb


def rank_then_fuse_plan(
    branches: list[dict[str, Any]] | list[RankedBranch],
    *,
    delta: float = RANK_DELTA_FOR_K2,
) -> tuple[list[RankedBranch], list[RankedBranch]]:
    """Return (ranked_all, top_k)."""
    ranked = rank_branches(branches)
    return ranked, select_top_k(ranked, delta=delta)
