"""FR-28 cheap-path fixture harness (Story 2.5).

Cases: F1, F2, F5, F7, F8a, F8b, F9, F10, F14, F15, F16, I1–I3.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.fusion.policy import (
    ClassifyResult,
    resolve_zeus_mode_fields,
    select_path_policy,
)

FIXTURES = Path(__file__).parent / "fixtures" / "fusion_policy" / "cases.json"


def _load_cases() -> list[dict]:
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    return list(data["cases"])


def _run_case(case: dict):
    g = case["given"]
    user_q = str(g.get("user_q") or "")
    if g.get("user_chars"):
        user_q = (user_q or "x")[0] * int(g["user_chars"])

    forced = None
    legacy = None
    mode_ignored = False
    product_mode = g.get("product_mode") or "power"
    zeus_mode = g.get("zeus_mode")
    model_id = g.get("model_id")

    if zeus_mode or model_id:
        prod, forced, legacy, mode_ignored = resolve_zeus_mode_fields(
            model_id=model_id,
            zeus={"mode": zeus_mode} if zeus_mode else None,
            prefs_product_mode=product_mode,
        )
        product_mode = prod

    if g.get("classify_failed"):
        classify = ClassifyResult(
            classify_phase="implement",
            complexity_band="med",
            confidence=0.0,
            failed=True,
        )
    else:
        classify = ClassifyResult(
            classify_phase=g["classify_phase"],
            complexity_band=g["complexity_band"],
            confidence=float(g["confidence"]),
            design_lexicon=bool(
                g.get("design_lexicon")
                or ("спроектируй" in user_q.lower() or "спроектировать" in user_q.lower())
            ),
            failed=False,
        )

    return select_path_policy(
        classify=classify,
        effort=g.get("effort") or "med",
        product_mode=product_mode,
        kill_switch=bool(g.get("kill_switch")),
        forced_code=forced,
        legacy_code=legacy,
        mode_ignored=mode_ignored,
        user_q=user_q,
        has_last_assistant=bool(g.get("has_last_assistant")),
        has_new_traceback=bool(g.get("has_new_traceback")),
        stream=bool(g.get("stream")),
    )


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_policy_fixture_case(case: dict):
    decision = _run_case(case)
    exp = case["expect"]

    if "path" in exp:
        assert decision.path == exp["path"], (
            f"{case['id']}: path {decision.path} != {exp['path']} "
            f"(routed_by={decision.routed_by})"
        )
    if "not_path" in exp:
        assert decision.path != exp["not_path"]
    if "routed_by" in exp:
        assert decision.routed_by == exp["routed_by"], (
            f"{case['id']}: routed_by {decision.routed_by} != {exp['routed_by']}"
        )
    if "routed_by_family" in exp:
        fam = exp["routed_by_family"]
        assert decision.routed_by.startswith(fam) or fam in decision.routed_by, (
            f"{case['id']}: routed_by {decision.routed_by} not in family {fam}"
        )
    if "complexity" in exp:
        assert decision.complexity == exp["complexity"]
    if "interactive" in exp:
        assert decision.interactive is exp["interactive"], (
            f"{case['id']}: interactive {decision.interactive} != {exp['interactive']}"
        )
    if "design_lexicon" in exp:
        assert decision.design_lexicon is exp["design_lexicon"]
