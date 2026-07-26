"""Role Routing Epic 4 — Pipeline v1 (Brief→Test Author→mid doers→merge)."""

from __future__ import annotations

import asyncio
import json
import os

from app.fusion.merge import (
    detect_file_conflicts,
    extract_file_sections,
    merge_artifacts,
    merge_artifacts_async,
)
from app.fusion.model_power import TEST_AUTHOR_MIN, power_score
from app.fusion.pipeline import pick_pipeline
from app.fusion.pipeline_v1 import (
    V1_HAPPY_PATH_MAX_CALLS,
    execute_pipeline_v1,
    local_contract_check,
    pick_mid_doer,
    pick_strong_model,
    validate_architect_brief,
)
from app.fusion.roles import resolve_roles


# --- Story 4.1: hard trigger ---


def test_v1_trigger_only_large_2nd_power_custom_strong():
    rr = resolve_roles(product_mode="power", task_kind="architecture")
    assert rr.has_strong
    d = pick_pipeline(
        size="large",
        second_signal=True,
        product_mode="power",
        kill_switch=False,
        roles=rr,
    )
    assert d.pipeline == "v1"
    assert d.serving_path_clamp == "FULL"


def test_v1_forbidden_without_second_signal_or_simple_or_kill():
    rr = resolve_roles(product_mode="power", task_kind="architecture")
    assert (
        pick_pipeline(
            size="large",
            second_signal=False,
            product_mode="power",
            kill_switch=False,
            roles=rr,
        ).pipeline
        != "v1"
    )
    assert (
        pick_pipeline(
            size="large",
            second_signal=True,
            product_mode="simple",
            kill_switch=False,
            roles=rr,
        ).pipeline
        != "v1"
    )
    assert (
        pick_pipeline(
            size="large",
            second_signal=True,
            product_mode="power",
            kill_switch=True,
            roles=rr,
        ).pipeline
        != "v1"
    )


# --- Story 4.2: Brief validate + degrade ---


def test_validate_brief_accepts_1_to_3_components():
    ok = validate_architect_brief(
        {
            "components": [
                {
                    "id": "c1",
                    "role": "doer_ui",
                    "goal": "Hero",
                    "acceptance_one_liner": "CTA visible",
                    "files_hint": ["index.html"],
                }
            ],
            "api_contract": "App.init",
            "files_contract": "index.html",
        }
    )
    assert ok is not None
    assert len(ok.components) == 1


def test_validate_brief_rejects_empty_or_over3():
    assert validate_architect_brief({"components": []}) is None
    assert validate_architect_brief(None) is None
    assert (
        validate_architect_brief(
            {
                "components": [
                    {
                        "id": f"c{i}",
                        "role": "doer_logic",
                        "goal": "g",
                        "acceptance_one_liner": "a",
                    }
                    for i in range(4)
                ],
                "api_contract": "x",
                "files_contract": "y",
            }
        )
        is None
    )
    assert (
        validate_architect_brief(
            {"components": [{"id": "c1", "role": "doer_logic", "goal": "", "acceptance_one_liner": "x"}]}
        )
        is None
    )


def test_validate_brief_requires_api_and_files_contract():
    base = {
        "components": [
            {
                "id": "c1",
                "role": "doer_logic",
                "goal": "g",
                "acceptance_one_liner": "a",
            }
        ]
    }
    assert validate_architect_brief({**base, "api_contract": "App", "files_contract": ""}) is None
    assert validate_architect_brief({**base, "api_contract": "", "files_contract": "a.js"}) is None
    assert (
        validate_architect_brief({**base, "api_contract": "App.init", "files_contract": "a.js"})
        is not None
    )


def test_execute_v1_degrades_on_invalid_brief():
    calls: list[str] = []

    async def _up(model, messages, **_k):
        calls.append(model)
        # Architect returns garbage
        return {
            "ok": True,
            "text": "sorry not json",
            "prompt_tokens": 1,
            "completion_tokens": 2,
        }

    stack = ["claude-opus-4-6", "gemini-3-flash", "deepseek-v4-flash"]
    out = asyncio.run(
        execute_pipeline_v1(
            stack=stack,
            curator="claude-opus-4-6",
            messages=[{"role": "user", "content": "landing"}],
            user_q="landing",
            product_mode="power",
            upstream_call=_up,
        )
    )
    assert out.meta.get("degrade_to_fallback") is True
    assert out.meta.get("degrade_reason") == "invalid_brief"
    assert len(calls) == 1  # architect only


def test_execute_v1_degrades_without_strong():
    out = asyncio.run(
        execute_pipeline_v1(
            stack=["deepseek-v4-flash", "gemini-3-flash"],
            curator="gemini-3-flash",
            messages=[{"role": "user", "content": "x"}],
            user_q="x",
            product_mode="custom",
        )
    )
    assert out.meta.get("degrade_to_fallback") is True
    assert out.meta.get("degrade_reason") == "no_strong_architect"


def test_execute_v1_skips_unhealthy_strong():
    """AD-16 / G3: unhealthy ≥950 must not be Architect."""
    called: list[str] = []

    async def _up(model, messages, **_k):
        called.append(model)
        return {
            "ok": True,
            "text": json.dumps(
                {
                    "components": [
                        {
                            "id": "c1",
                            "role": "doer_logic",
                            "goal": "g",
                            "acceptance_one_liner": "ok acceptance line",
                            "files_hint": ["a.js"],
                        }
                    ],
                    "api_contract": "init",
                    "files_contract": "a.js",
                }
            ),
            "prompt_tokens": 1,
            "completion_tokens": 10,
        }

    # Only strong is unhealthy → degrade (no other ≥950)
    out = asyncio.run(
        execute_pipeline_v1(
            stack=["claude-opus-4-6", "gemini-3-flash"],
            curator="gemini-3-flash",
            messages=[{"role": "user", "content": "x"}],
            user_q="x",
            product_mode="power",
            unhealthy={"claude-opus-4-6"},
            upstream_call=_up,
        )
    )
    assert out.meta.get("degrade_to_fallback") is True
    assert out.meta.get("degrade_reason") == "no_strong_architect"
    assert called == []


# --- Story 4.3–4.5: heuristic happy path ---


def test_execute_v1_heuristic_happy_path_call_budget():
    prev = os.environ.get("ZEUS_FUSION_V1_HEURISTIC")
    os.environ["ZEUS_FUSION_V1_HEURISTIC"] = "1"
    try:
        stack = ["claude-opus-4-6", "gemini-3-flash", "deepseek-v4-flash"]
        out = asyncio.run(
            execute_pipeline_v1(
                stack=stack,
                curator="claude-opus-4-6",
                messages=[{"role": "user", "content": "Сделай лендинг"}],
                user_q="Сделай лендинг для СТО",
                product_mode="power",
            )
        )
        assert out.meta.get("degrade_to_fallback") is False
        assert out.routed_by == "pipeline_v1"
        assert out.meta.get("pipeline") == "v1"
        assert out.meta.get("mid_parallel") is True
        calls = int(out.meta.get("llm_calls") or 0)
        assert calls <= V1_HAPPY_PATH_MAX_CALLS
        assert calls >= 4  # architect + test_author + ≥2 doers
        assert out.meta.get("call_budget_ok") is True
        assert "// file:" in (out.answer or "")
        roles = {b.role for b in out.branches}
        assert "architect" in roles
        assert "test_author" in roles
        assert any(r.startswith("doer_") for r in roles)
        brief = out.meta.get("brief") or {}
        assert 1 <= len(brief.get("components") or []) <= 3
    finally:
        if prev is None:
            os.environ.pop("ZEUS_FUSION_V1_HEURISTIC", None)
        else:
            os.environ["ZEUS_FUSION_V1_HEURISTIC"] = prev


def test_pick_mid_doer_prefers_800_920_band():
    stack = ["claude-opus-4-6", "gemini-3-flash", "deepseek-v4-flash"]
    mid = pick_mid_doer(stack, used=set())
    assert mid is not None
    assert 800 <= power_score(mid) <= 920
    assert power_score(mid) < TEST_AUTHOR_MIN
    strong = pick_strong_model(stack)
    assert strong == "claude-opus-4-6"
    assert power_score(strong) >= TEST_AUTHOR_MIN


def test_layer_b_skipped_meta_when_no_tests_needed_path():
    """Without ≥950, execute degrades before Layer B (FR9)."""
    assert pick_strong_model(["gemini-3-flash"]) is None


def test_one_red_fix_cycle_only_red_rewritten():
    calls: list[tuple[str, str]] = []

    async def _up(model, messages, **_k):
        blob = " ".join(str(m.get("content") or "") for m in messages)
        role_hint = "architect"
        if "Test Author" in blob or "contract tests" in blob:
            role_hint = "test_author"
        elif "Fix ONLY" in blob:
            role_hint = "fix"
        elif "component id=" in blob or "Your component" in blob:
            role_hint = "doer"
        calls.append((model, role_hint))
        if role_hint == "architect":
            return {
                "ok": True,
                "text": json.dumps(
                    {
                        "components": [
                            {
                                "id": "c1",
                                "role": "doer_logic",
                                "goal": "API handler",
                                "acceptance_one_liner": "exports initApp",
                                "files_hint": ["app.js"],
                            },
                            {
                                "id": "c2",
                                "role": "doer_ui",
                                "goal": "UI shell",
                                "acceptance_one_liner": "has hero CTA",
                                "files_hint": ["index.html"],
                            },
                        ],
                        "api_contract": "initApp",
                        "files_contract": "app.js,index.html",
                    }
                ),
                "prompt_tokens": 5,
                "completion_tokens": 40,
            }
        if role_hint == "test_author":
            return {
                "ok": True,
                "text": json.dumps(
                    {
                        "tests": [
                            {"component_id": "c1", "checks": ["exports initApp"]},
                            {"component_id": "c2", "checks": ["hero CTA"]},
                        ]
                    }
                ),
                "prompt_tokens": 5,
                "completion_tokens": 20,
            }
        if role_hint == "fix":
            return {
                "ok": True,
                "text": (
                    "// file: app.js\n"
                    "export function initApp() { return 'exports initApp working handler'; }\n"
                ),
                "prompt_tokens": 5,
                "completion_tokens": 30,
            }
        # Doers: c1 short stub (RED), c2 solid (GREEN)
        if "id=c1" in blob or "component id=c1" in blob:
            return {
                "ok": True,
                "text": "todo",  # too short → RED
                "prompt_tokens": 2,
                "completion_tokens": 1,
            }
        return {
            "ok": True,
            "text": (
                "// file: index.html\n"
                "<html><body><section class='hero'><button>CTA</button>"
                "has hero CTA layout ready</section></body></html>\n"
            ),
            "prompt_tokens": 5,
            "completion_tokens": 40,
        }

    stack = ["claude-opus-4-6", "gemini-3-flash", "deepseek-v4-flash"]
    out = asyncio.run(
        execute_pipeline_v1(
            stack=stack,
            curator="claude-opus-4-6",
            messages=[{"role": "user", "content": "build app"}],
            user_q="build app",
            product_mode="power",
            upstream_call=_up,
        )
    )
    assert out.meta.get("degrade_to_fallback") is False
    assert out.meta.get("test_fix_ran") is True
    fix_calls = [c for c in calls if c[1] == "fix"]
    assert len(fix_calls) == 1  # only RED rewritten once
    # escalate budget not touched in v1 meta
    assert "escalate_count" not in (out.meta or {}) or out.meta.get("escalate_count") in (
        None,
        0,
    )


def test_local_contract_check_basics():
    ok, _ = local_contract_check(
        answer=("visible CTA layout with real content " * 3),
        acceptance="visible CTA",
    )
    assert ok is True
    bad, reason = local_contract_check(answer="todo", acceptance="x")
    assert bad is False
    assert reason == "answer_too_short"


# --- Story 4.6: file-aware merge ---


def test_merge_file_aware_no_conflict_no_extra_call():
    chunks = [
        {
            "component_id": "c1",
            "answer": "// file: a.js\nexport const a = 1;\n",
            "files_hint": ["a.js"],
        },
        {
            "component_id": "c2",
            "answer": "// file: b.js\nexport const b = 2;\n",
            "files_hint": ["b.js"],
        },
    ]
    brief = {
        "components": [
            {"id": "c1", "files_hint": ["a.js"]},
            {"id": "c2", "files_hint": ["b.js"]},
        ],
        "api_contract": "a",
    }
    m = merge_artifacts(chunks, brief=brief)
    assert m["conflict"] is False
    assert m["strategy"] == "file_aware"
    assert "// file: a.js" in m["answer"]
    assert "// file: b.js" in m["answer"]
    assert detect_file_conflicts(chunks) == []


def test_merge_conflict_triggers_one_strong_call():
    chunks = [
        {
            "component_id": "c1",
            "answer": "// file: shared.js\nexport const x = 1;\n",
            "files_hint": ["shared.js"],
        },
        {
            "component_id": "c2",
            "answer": "// file: shared.js\nexport const x = 2;\n",
            "files_hint": ["shared.js"],
        },
    ]
    assert detect_file_conflicts(chunks) == ["shared.js"]
    calls: list[str] = []

    async def _up(model, messages, **_k):
        calls.append(model)
        return {
            "ok": True,
            "text": "// file: shared.js\nexport const x = 1; // merged\n",
            "prompt_tokens": 10,
            "completion_tokens": 20,
        }

    m = asyncio.run(
        merge_artifacts_async(
            chunks,
            brief={"api_contract": "x", "components": []},
            strong_model="claude-opus-4-6",
            curator_model="gemini-3-flash",
            upstream_call=_up,
        )
    )
    assert m["conflict"] is True
    assert m["conflict_call"] is True
    assert len(calls) == 1
    assert calls[0] == "claude-opus-4-6"
    assert m["strategy"] == "file_aware_conflict_strong"
    assert "merged" in m["answer"]


def test_extract_file_sections():
    text = "// file: a.ts\nA\n// file: b.ts\nB\n"
    sec = extract_file_sections(text)
    assert sec["a.ts"].strip() == "A"
    assert sec["b.ts"].strip() == "B"


def test_sibling_kept_when_one_doer_fails():
    async def _up(model, messages, **_k):
        blob = " ".join(str(m.get("content") or "") for m in messages)
        if "Architect" in blob or "Brief JSON" in blob:
            return {
                "ok": True,
                "text": json.dumps(
                    {
                        "components": [
                            {
                                "id": "c1",
                                "role": "doer_logic",
                                "goal": "ok part",
                                "acceptance_one_liner": "solid module export",
                                "files_hint": ["ok.js"],
                            },
                            {
                                "id": "c2",
                                "role": "doer_logic",
                                "goal": "bad part",
                                "acceptance_one_liner": "never arrives",
                                "files_hint": ["bad.js"],
                            },
                        ],
                        "api_contract": "solid",
                        "files_contract": "ok.js",
                    }
                ),
                "prompt_tokens": 1,
                "completion_tokens": 10,
            }
        if "contract tests" in blob or "Test Author" in blob:
            return {
                "ok": True,
                "text": json.dumps(
                    {
                        "tests": [
                            {"component_id": "c1", "checks": ["solid"]},
                            {"component_id": "c2", "checks": ["x"]},
                        ]
                    }
                ),
                "prompt_tokens": 1,
                "completion_tokens": 5,
            }
        if "id=c2" in blob or "component id=c2" in blob:
            raise RuntimeError("doer boom")
        if "Fix ONLY" in blob:
            return {
                "ok": True,
                "text": "// file: bad.js\nexport const never = true; never arrives ok\n",
                "prompt_tokens": 1,
                "completion_tokens": 5,
            }
        return {
            "ok": True,
            "text": (
                "// file: ok.js\n"
                "export function solid() { return 'solid module export working'; }\n"
            ),
            "prompt_tokens": 1,
            "completion_tokens": 20,
        }

    out = asyncio.run(
        execute_pipeline_v1(
            stack=["claude-opus-4-6", "gemini-3-flash", "deepseek-v4-flash"],
            curator="claude-opus-4-6",
            messages=[{"role": "user", "content": "x"}],
            user_q="x",
            product_mode="power",
            upstream_call=_up,
        )
    )
    assert out.meta.get("degrade_to_fallback") is False
    assert "ok.js" in (out.answer or "")
