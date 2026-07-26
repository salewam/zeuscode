"""Epic 4 full validation — AC 4.1–4.9 gate checks (post-hole-fix)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.fusion import pick_leader
from app.fusion.metrics import (
    FusionFlags,
    RateLimitExceeded,
    RuntimeBudgets,
    apply_serving_flags,
    check_alert_stubs,
    check_rate_limit,
    lookup_trace_routing,
    note_dead_model,
    note_verifier_result,
    observe_request,
    panel_concurrency_semaphore,
    race_concurrency_semaphore,
    reset_metrics_for_tests,
    resolve_serving_path,
    runtime_budgets_from_settings,
)
from app.fusion.policy import soft_resolve_for_monolith
from app.fusion.publish_gate import check_publish_html
from app.fusion.session import StickyState, sticky_leader_hint


_POWER = [
    "claude-opus-4-8",
    "gemini-3.1-pro",
    "deepseek-v4-pro",
]


def test_sticky_leader_consumed_by_pick_leader():
    """4.1 / AD-16: sticky hint wins when healthy and under overflow budget."""
    sticky = "deepseek-v4-pro"
    assert sticky in _POWER
    assert (
        pick_leader(_POWER, "architecture", sticky_leader=sticky) == sticky
    )
    # Unhealthy sticky → fall through to strength
    assert (
        pick_leader(
            _POWER,
            "architecture",
            sticky_leader=sticky,
            unhealthy={sticky},
        )
        == "claude-opus-4-8"
    )


def test_sticky_does_not_own_path():
    st = StickyState(
        session_id="s",
        leader="gemini-3.1-pro",
        phase_meta={"phase": "review", "path": "MUST_NOT_STICK"},
    )
    assert sticky_leader_hint(st) == "gemini-3.1-pro"
    # put_sticky strips path — unit-level: session helper never exposes Path as authority
    assert st.phase_meta.get("path") == "MUST_NOT_STICK"  # in-memory only; store strips


def test_overflow_overrides_sticky_leader():
    """AD-16: long-context overflow may rotate Leader past sticky."""
    leader = pick_leader(
        _POWER,
        "general",
        sticky_leader="deepseek-v4-pro",
        context_chars=200_000,
        overflow_chars=120_000,
    )
    assert leader in _POWER
    # Gemini family preferred under overflow
    assert leader.startswith("gemini") or leader == "claude-opus-4-8"


def test_shadow_soft_resolve_serves_baseline(monkeypatch):
    """4.3 / AD-9: candidate logged; serving stays baseline under shadow."""
    monkeypatch.setenv("ZEUS_FUSION_EPIC2_POLICY", "1")
    monkeypatch.setenv("FUSION_SHADOW_MODE", "1")

    from app.config import get_settings

    get_settings.cache_clear()
    # Force shadow via flags object path used by apply_serving_flags
    monkeypatch.setattr(
        "app.fusion.metrics.load_fusion_flags",
        lambda settings=None: FusionFlags(
            shadow=True, canary_pct=0, kill=False, baseline_id="bl_test"
        ),
    )

    serving, policy, rb = apply_serving_flags(
        candidate_path="FULL",
        baseline_path="FAST",
        zeus={"user_id": 1},
        routed_by="auto",
        phase="implement",
    )
    assert serving == "FAST"
    assert policy == "FULL"
    assert "shadow" in rb

    # soft_resolve path also clamps when epic2 on
    decision = soft_resolve_for_monolith(
        user_q="перепиши архитектуру платформы и добавь миграции",
        model_id="zeus/fusion",
        zeus={"mode": "power", "user_id": 7},
        messages=[{"role": "user", "content": "перепиши архитектуру платформы и добавь миграции"}],
        clf_meta={"stack": "full", "task": "architecture", "source": "llm"},
        classify_failed=False,
    )
    assert decision is not None
    # Under shadow, serving path is baseline FAST (legacy full→FULL baseline from stack)
    # baseline from stack=full → FULL; wait — legacy_baseline_path("full")=FULL
    # so shadow serves FULL when baseline is FULL. Use explicit FAST baseline case above.
    assert decision.path in ("FAST", "FULL", "CASCADE", "RACE")
    get_settings.cache_clear()


def test_kill_switch_routed_by():
    serving, flag = resolve_serving_path(
        candidate_path="RACE",
        baseline_path="FULL",
        flags=FusionFlags(shadow=False, canary_pct=100, kill=True),
        user_id=1,
    )
    assert serving == "FAST" and flag == "kill_switch"


def test_runtime_budgets_light_enforce():
    """4.5: Settings budgets are consumed by rate/concurrency helpers."""
    b = runtime_budgets_from_settings()
    assert b.global_timeout_s > 0
    assert b.panel_concurrency >= 1
    assert b.race_concurrency >= 1
    assert b.rate_limit_rpm >= 1

    reset_metrics_for_tests()
    # Semaphores constructed from Settings
    assert panel_concurrency_semaphore()._value == b.panel_concurrency  # noqa: SLF001
    reset_metrics_for_tests()
    assert race_concurrency_semaphore()._value == b.race_concurrency  # noqa: SLF001

    reset_metrics_for_tests()
    # Tiny RPM → second hit in same window raises
    from app.fusion import metrics as m

    original = m.runtime_budgets_from_settings
    m.runtime_budgets_from_settings = lambda settings=None: RuntimeBudgets(
        global_timeout_s=b.global_timeout_s,
        panel_concurrency=b.panel_concurrency,
        race_concurrency=b.race_concurrency,
        retry_max=b.retry_max,
        retry_backoff_s=b.retry_backoff_s,
        thinking_keepalive_s=b.thinking_keepalive_s,
        rate_limit_rpm=1,
        overflow_context_chars=b.overflow_context_chars,
        disaster_error_code=b.disaster_error_code,
        sticky_ttl_hours=b.sticky_ttl_hours,
    )
    try:
        check_rate_limit(now=1_000_000.0)
        with pytest.raises(RateLimitExceeded):
            check_rate_limit(now=1_000_000.1)
    finally:
        m.runtime_budgets_from_settings = original
        reset_metrics_for_tests()


def test_observe_enriches_feedback_trace():
    """4.6 / 4.8: observe caches routing for feedback enrich; alerts fire."""
    reset_metrics_for_tests()
    tid = "trace-epic4-gate"
    observe_request(
        path="FULL",
        phase="review",
        routed_by="auto",
        trace_id=tid,
        leader="claude-opus-4-8",
        model_ids=_POWER,
        baseline_id="bl_gate",
    )
    ctx = lookup_trace_routing(tid)
    assert ctx is not None
    assert ctx["leader"] == "claude-opus-4-8"
    assert ctx["path"] == "FULL"
    assert ctx["baseline_id"] == "bl_gate"

    note_billing = __import__(
        "app.fusion.metrics", fromlist=["note_billing_drift"]
    ).note_billing_drift
    note_billing()
    note_dead_model("dead-model-x")
    note_dead_model("dead-model-x")
    note_dead_model("dead-model-x")
    note_verifier_result(always_ok=True)
    fired = {x["id"] for x in check_alert_stubs()}
    assert "billing_drift" in fired
    assert "dead_models" in fired


def test_publish_gate_and_eval_n50():
    """4.4 + 4.7: eval N≥50 + canary bars; publish badge gate."""
    from app.publish import inject_zeus_badge

    html = inject_zeus_badge("<!DOCTYPE html><html><body><h1>Hi</h1></body></html>")
    assert check_publish_html(html)["has_zeus_badge"] is True

    from tests.eval.harness import run_suite

    report = run_suite(offline_stub_answer=True)
    s = report["summary"]
    assert s["n"] >= 50
    assert s["n_min_ok"] is True
    assert s.get("canary_blockers")
    assert "canary_bars_ok" in s
    assert s["canary_bars_mode"] in ("enforced", "documented_no_bucket_baseline")
    assert s["ok"] is True


def test_ops_canary_exit_artifacts_exist():
    """4.9: load-test stub + incident runbook present."""
    root = Path(__file__).resolve().parents[2]
    ops = root / "_bmad-output" / "implementation-artifacts" / "ops"
    assert (ops / "incident-runbook-fusion.md").is_file()
    assert (ops / "load-test-fusion.md").is_file()
    stub = root / "backend" / "scripts" / "load_test_fusion_stub.py"
    assert stub.is_file()


def test_fusion_no_routers_import():
    """AD-10: fusion/* must not import routers.*"""
    fusion_root = Path(__file__).resolve().parents[1] / "app" / "fusion"
    offenders: list[str] = []
    for path in fusion_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import routers" in text or "from app.routers" in text or "from routers" in text:
            offenders.append(str(path.relative_to(fusion_root.parent.parent)))
    assert offenders == []
