"""Epic 4: sticky, prefs, shadow/canary, budgets, publish gate, metrics."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.fusion import apply_user_fusion_pref, extract_session_id
from app.fusion.metrics import (
    DEFAULT_BASELINE_ID,
    FusionFlags,
    check_alert_stubs,
    clamp_path_for_kill_switch,
    compute_baseline_id,
    ensure_trace_id,
    legacy_baseline_path,
    log_shadow_compare,
    normalize_effort,
    observe_request,
    reset_metrics_for_tests,
    resolve_serving_path,
    runtime_budgets_from_settings,
    snapshot_metrics,
)
from app.fusion.publish_gate import PublishRegressionError, check_publish_html
from app.fusion.session import StickyState, sticky_leader_hint


def test_extract_session_id_header_and_zeus():
    assert extract_session_id(header_value="abc") == "abc"
    assert extract_session_id(headers={"X-Zeus-Session-Id": "hdr-1"}) == "hdr-1"
    assert extract_session_id(zeus={"session_id": "z-9"}) == "z-9"
    assert extract_session_id(headers={}, zeus={}) is None


def test_sticky_state_does_not_own_path():
    st = StickyState(session_id="s1", leader="claude-opus-4-8", stack=["a", "b"], phase_meta={"phase": "review"})
    assert sticky_leader_hint(st) == "claude-opus-4-8"
    assert "path" not in st.phase_meta or st.phase_meta.get("path") is None


def test_effort_and_kill_prefs_apply():
    class U:
        fusion_pref = "power"
        fusion_models = ""
        fusion_effort = "high"
        fusion_kill_switch = 1

    z, _p = apply_user_fusion_pref(U(), zeus={}, models=None)
    assert z["effort"] == "high"
    assert z["kill_switch"] is True
    assert z["mode"] == "fast"
    assert z.get("kill_forced") is True


def test_effort_zeus_overrides_pref():
    class U:
        fusion_pref = "power"
        fusion_models = ""
        fusion_effort = "low"
        fusion_kill_switch = 0

    z, _ = apply_user_fusion_pref(U(), zeus={"effort": "max"}, models=None)
    assert z["effort"] == "max"
    assert z["mode"] == "power"


def test_normalize_effort():
    assert normalize_effort("HIGH") == "high"
    assert normalize_effort(None) == "normal"


def test_baseline_id_stable_and_embeds_lexicon():
    a = compute_baseline_id()
    b = compute_baseline_id()
    assert a == b == DEFAULT_BASELINE_ID
    assert a.startswith("bl_")


def test_shadow_serves_baseline():
    serving, flag = resolve_serving_path(
        candidate_path="FULL",
        baseline_path="FAST",
        flags=FusionFlags(shadow=True, canary_pct=0, kill=False, baseline_id="bl_x"),
    )
    assert serving == "FAST"
    assert flag == "shadow_baseline"


def test_kill_switch_clamps_fast():
    assert clamp_path_for_kill_switch("FULL", {"kill_switch": True}) == "FAST"
    serving, flag = resolve_serving_path(
        candidate_path="RACE",
        baseline_path="FULL",
        flags=FusionFlags(shadow=False, canary_pct=100, kill=True),
        user_id=1,
    )
    assert serving == "FAST" and flag == "kill_switch"


def test_canary_cohort_stable():
    flags = FusionFlags(shadow=False, canary_pct=50.0, kill=False)
    a, fa = resolve_serving_path(
        candidate_path="FULL", baseline_path="FAST", flags=flags, user_id=42
    )
    b, fb = resolve_serving_path(
        candidate_path="FULL", baseline_path="FAST", flags=flags, user_id=42
    )
    assert (a, fa) == (b, fb)
    assert a in ("FULL", "FAST")


def test_legacy_baseline_1v3():
    assert legacy_baseline_path("fast") == "FAST"
    assert legacy_baseline_path("full") == "FULL"


def test_runtime_budgets_present():
    b = runtime_budgets_from_settings()
    assert b.global_timeout_s > 0
    assert b.panel_concurrency >= 1
    assert b.race_concurrency >= 1
    assert b.retry_max >= 0
    assert b.thinking_keepalive_s > 0
    assert b.rate_limit_rpm > 0
    assert b.overflow_context_chars > 0
    assert b.disaster_error_code


def test_observe_and_shadow_metrics():
    reset_metrics_for_tests()
    tid = ensure_trace_id(None)
    observe_request(path="FULL", phase="review", routed_by="auto", escalate_from="CASCADE", trace_id=tid)
    log_shadow_compare(
        candidate_path="FULL",
        serving_path="FAST",
        baseline_id="bl_test",
        trace_id=tid,
    )
    snap = snapshot_metrics()
    assert snap["requests_total"] == 1
    assert snap["escalate_pct"] > 0
    assert snap["shadow_mismatch"] == 1
    assert "auto" in snap["routed_by"]


def test_alert_stubs_billing():
    reset_metrics_for_tests()
    from app.fusion.metrics import note_billing_drift

    note_billing_drift()
    fired = check_alert_stubs()
    assert any(x["id"] == "billing_drift" for x in fired)


def test_publish_gate_requires_badge():
    html = "<!DOCTYPE html><html><body><h1>Hi</h1></body></html>"
    # inject happens inside check via publish helpers
    from app.publish import inject_zeus_badge

    ok = check_publish_html(inject_zeus_badge(html))
    assert ok["has_zeus_badge"] is True


def test_publish_gate_rejects_empty():
    with pytest.raises(PublishRegressionError):
        check_publish_html("x")


def test_sticky_crud_sqlite(tmp_path, monkeypatch):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'sticky.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    from app.config import get_settings

    get_settings.cache_clear()
    # Rebuild engine bound to temp DB
    import app.db as dbmod
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(db_url, echo=False)
    dbmod.engine = engine
    dbmod.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async def _run():
        from app.db import Base, SessionLocal
        from app.fusion.session import get_sticky, put_sticky
        from app import models  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with SessionLocal() as db:
            await put_sticky(
                db,
                "sess-1",
                leader="gemini-3.1-pro",
                stack=["gemini-3.1-pro", "deepseek-v4-pro"],
                phase_meta={"phase": "code", "path": "SHOULD_NOT_STICK"},
            )
            st = await get_sticky(db, "sess-1")
            assert st is not None
            assert st.leader == "gemini-3.1-pro"
            assert "path" not in st.phase_meta
            assert st.stack[0] == "gemini-3.1-pro"

    asyncio.run(_run())
    get_settings.cache_clear()


def test_eval_suite_n_ge_50():
    eval_dir = Path(__file__).resolve().parent / "eval"
    import importlib.util

    def _load(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        return mod

    gen_mod = _load("eval_generate_fixtures", eval_dir / "generate_fixtures.py")
    suite = gen_mod.build_suite(50)
    assert len(suite) >= 50
    gen_mod.main()
    fixtures = list((eval_dir / "fixtures").glob("*.json"))
    fixtures = [p for p in fixtures if p.name != "index.json"]
    assert len(fixtures) >= 50

    harness = _load("eval_harness", eval_dir / "harness.py")
    report = harness.run_suite(offline_stub_answer=True)
    assert report["summary"]["n_min_ok"] is True
