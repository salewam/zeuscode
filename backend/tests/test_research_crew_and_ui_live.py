"""Research×3→lead (DeepSeek) + UI live verify."""

from __future__ import annotations

import asyncio

from app.fusion.research_crew import (
    ResearchNote,
    build_coverage_checklist,
    format_research_digest,
    inject_digest_into_messages,
    is_stub_answer,
    merge_school_packs,
    missing_coverage_items,
    run_research_crew,
    should_run_research_crew,
)
from app.fusion.ui_live_verify import extract_html_document, extract_preview_url


def test_should_run_skips_light_chitchat():
    assert should_run_research_crew(user_q="привет", task_kind="light", phase="chat") is False
    assert should_run_research_crew(
        user_q="найди конкурентов Linear", task_kind="light", phase="chat"
    ) is True
    assert should_run_research_crew(
        user_q="сделай лендинг автосервиса", task_kind="ui", phase="ui"
    ) is False
    assert should_run_research_crew(
        user_q="найди в интернете примеры лендингов", task_kind="ui", phase="ui"
    ) is True
    assert should_run_research_crew(
        user_q="перепиши auth на JWT", task_kind="code", phase="implement"
    ) is False
    assert should_run_research_crew(
        user_q="проверь latest официальную документацию JWT", task_kind="code", phase="implement"
    ) is True
    assert should_run_research_crew(
        user_q="fix parser_2026.py", task_kind="code", phase="implement"
    ) is False
    assert should_run_research_crew(
        user_q="fix parser_2026.py using https://docs.example.com/parser",
        task_kind="code",
        phase="implement",
    ) is True


def test_research_crew_heuristic_digest(monkeypatch):
    monkeypatch.setenv("ZEUS_FUSION_RESEARCH_HEURISTIC", "1")

    async def fake_pack(user_q: str):
        return {
            "ok": True,
            "refs": [
                {
                    "url": "https://linear.app",
                    "title": "Linear",
                    "snippet": "issue tracker",
                    "text": "Hero CTA booking pricing",
                    "fetch_ok": True,
                    "fetch_backend": "httpx",
                }
            ],
            "queries": ["q"],
            "backend": "test",
        }

    monkeypatch.setattr(
        "app.fusion.research_crew.research_pack_for_critics", fake_pack
    )
    rc = asyncio.run(
        run_research_crew(
            user_q="landing for issue tracker",
            product_mode="power",
            stack=[
                "claude-opus-4-6",
                "gpt-5.4",
                "deepseek-v4-pro",
                "gemini-3-pro-preview",
                "gemini-3.1-pro",
                "grok-4.3",
            ],
        )
    )
    assert rc.ok
    assert len(rc.notes) == 3
    assert "research_digest" in rc.digest
    assert rc.digest_struct.get("summary") or rc.digest_struct.get("agreed")
    assert rc.meta.get("lead_role") == "face"
    assert "analyst" not in (rc.meta.get("models") or {})
    assert (rc.meta.get("models") or {}).get("lead") == "claude-sonnet-4-6"
    assert (rc.meta.get("models") or {}).get("researcher_a") == "gemini-3.1-pro-preview"
    msgs = inject_digest_into_messages(
        [{"role": "system", "content": "CLIENT"}, {"role": "user", "content": "hi"}],
        rc.digest,
    )
    assert "research_digest" in msgs[0]["content"]
    assert "CLIENT" in msgs[0]["content"]


def test_research_gather_isolates_one_school_exception(monkeypatch):
    monkeypatch.setenv("ZEUS_FUSION_RESEARCH_HEURISTIC", "1")

    async def fake_researcher(*, role, model_id, **_kwargs):
        if role == "researcher_b":
            raise RuntimeError("school unavailable")
        return ResearchNote(
            model_id=model_id,
            role=role,
            findings=[f"{role} useful finding"],
            sources=[f"https://example.com/{role}"],
        )

    monkeypatch.setattr(
        "app.fusion.research_crew._one_researcher", fake_researcher
    )
    result = asyncio.run(
        run_research_crew(
            user_q="latest official docs",
            stack=["grok-4.3", "deepseek-v4-pro", "claude-opus-4-6"],
        )
    )
    assert len(result.notes) == 3
    assert sum(bool(note.error) for note in result.notes) == 1
    assert sum(bool(note.findings) for note in result.notes) == 2


def test_merge_school_packs_keeps_filing_figures_and_extracts():
    packs = [
        {
            "ok": True,
            "browser_used": 0,
            "backend": "sec_edgar",
            "queries": ["akr 10-Q"],
            "filing_figures": ["[period 2024-03-31] Core Portfolio operating margin: 32.4%"],
            "refs": [
                {
                    "url": "https://www.sec.gov/a.htm",
                    "title": "AKR",
                    "snippet": "10-Q",
                    "text": "FILING FIGURES:\n- Core 32.4%\n\nbody",
                    "filing_figures": ["Core Portfolio operating margin: 32.4%"],
                    "ref_kind": "sec_filing",
                }
            ],
        },
        {
            "ok": True,
            "browser_used": 1,
            "backend": "duckduckgo_html",
            "queries": ["akr news"],
            "filing_figures": [],
            "refs": [
                {
                    "url": "https://example.com/news",
                    "title": "News",
                    "snippet": "deal",
                    "text": "Renaissance purchase",
                    "ref_kind": "roundup",
                }
            ],
        },
    ]
    merged = merge_school_packs(packs)
    assert merged["ok"] is True
    assert merged["browser_used"] == 1
    figs = " ".join(merged["filing_figures"])
    assert "32.4%" in figs
    assert any(r.get("url", "").endswith("a.htm") for r in merged["refs"])
    assert any("example.com/news" in str(r.get("url")) for r in merged["refs"])


def test_coverage_checklist_includes_query_periods():
    items = build_coverage_checklist(
        "Calculate Core Portfolio operating margin in Q1 2024 and ownership increased from 20%"
    )
    blob = " ".join(items).lower()
    assert "q1 2024" in blob
    assert "ownership" in blob


def test_format_digest_marks_disagreements():
    text = format_research_digest(
        {
            "summary": "A",
            "agreed": ["x"],
            "disagreements": ["A vs B: y"],
            "sources": ["https://a.test"],
        }
    )
    assert "Disagreements" in text
    assert "https://a.test" in text


def test_is_stub_answer_detects_placeholders():
    assert is_stub_answer(
        "Я соберу полный методологический анализ. Сначала проверю ключевые веб-источники, "
        "затем синтезирую всё в структурированный ответ."
    )
    assert is_stub_answer(
        "Начну с извлечения содержимого ключевых веб-источников, чтобы подкрепить анализ фактами."
    )
    assert is_stub_answer("I'll gather the sources and then write the answer.")
    assert not is_stub_answer(
        "TWFE is a variance-weighted average of 2×2 DiD contrasts including forbidden "
        "comparisons. Callaway-Sant'Anna estimates ATT(g,t) with never-treated controls. "
        "Sun-Abraham uses cohort × event-time interactions. Negative weights cause bias."
    )


def test_research_path_mode_deep_vs_fast():
    from app.fusion.research_crew import needs_deep_web_research, research_path_mode

    assert research_path_mode(
        "Analyze CME Group's cash generation efficiency and capital allocation"
    ) == "deep"
    assert needs_deep_web_research(
        "Acadia Realty Trust Core Portfolio Q1 2024 operating margins"
    )
    assert research_path_mode(
        "Methodological tensions in Difference-in-Differences TWFE Callaway"
    ) == "fast"
    assert research_path_mode(
        "Compare DMG MORI NLX spindle torque vs Mazak Integrex"
    ) == "deep"


def test_is_watery_answer_detects_framework_hedges():
    from app.fusion.research_crew import is_watery_answer, needs_primary_facts

    q = "Analyze NCD IPOs open in India as of Dec 8th 2025 for retiree fixed income"
    assert needs_primary_facts(q)
    water = (
        "Coverage Gap – Primary Market Data: No live data on specific NCD IPOs open "
        "as of December 8, 2025 is available from the provided sources. The analysis "
        "below addresses the methodological framework and credit assessment criteria "
        "that institutional committees require. Actionable recommendations require "
        "live issuance data. " + ("Typically rates vary. " * 80)
    )
    assert is_watery_answer(water, q)
    solid = (
        "As of Dec 8 2025, Issuer A NCD IPO offers 9.25% coupon, AA rating, 5-year tenure "
        "(https://example.com/ncd). Issuer B offers 8.90% with SEBI filing. "
        "Tax treatment under section 193 applies. Q1 2025 comparables show $120 million issue size."
    )
    assert not is_watery_answer(solid, q)


def test_coverage_checklist_for_staggered_did():
    q = (
        "Methodological tensions in Difference-in-Differences following "
        "Goodman-Bacon staggered adoption; Callaway and Sant'Anna; Sun and Abraham"
    )
    items = build_coverage_checklist(q)
    blob = " ".join(items).lower()
    assert "variance-weighted" in blob or "2×2" in blob or "2x2" in blob
    assert "att(g,t)" in blob
    assert "csdid" in blob


def test_missing_coverage_detects_absent_twfe_mechanics():
    checklist = build_coverage_checklist(
        "staggered DiD TWFE Goodman-Bacon Callaway Sun and Abraham"
    )
    thin = (
        "TWFE is biased in staggered designs. Callaway-Sant'Anna and Sun-Abraham "
        "are alternatives. Sources are limited."
    )
    missing = missing_coverage_items(thin, checklist)
    assert any("variance" in m.lower() or "2×2" in m or "2x2" in m.lower() for m in missing)
    rich = (
        "TWFE is a variance-weighted average of all 2×2 DiD contrasts, including "
        "forbidden comparisons that use already-treated units as controls. "
        "Under heterogeneous effects TWFE produces negative weights and can yield "
        "wrong-sign estimates even when all true treatment effects are positive. "
        "Callaway-Sant'Anna estimates ATT(g,t) with never-treated or not-yet-treated "
        "clean controls, then flexible aggregation to overall ATT and event-study paths "
        "under cohort-specific parallel trends with anticipation windows; software: "
        "R package did and Stata csdid. Sun-Abraham uses cohort × event-time "
        "interactions (interaction-weighted) with clean controls to avoid contamination "
        "in an event-study framework. Borusyak imputation differs on HTE/dynamics."
    )
    assert missing_coverage_items(rich, checklist) == []


def test_missing_coverage_no_did_bleed_on_dryer_query():
    q = (
        "Compare the Bosch Serie 8 heat pump dryer (WTX88M20AU), LG 9kg heat pump dryer "
        "(DVH9-09W), and Samsung 9kg heat pump dryer (DV90T6240LH) for a Melbourne "
        "household; consumer warranty claims and Victorian electricity rates"
    )
    checklist = build_coverage_checklist(q)
    blob = " ".join(checklist).lower()
    assert "stock-based" not in blob  # warranty ≠ warrant
    assert "kwh" in blob or "victorian" in blob or "veu" in blob
    draft = (
        "Bosch vs LG vs Samsung heat pump dryers for Melbourne. "
        "Energy labels and Victorian rates as loads increase; flexible aggregation "
        "of weekly drying cycles. Noise and warranty claims summarized."
    )
    missing = missing_coverage_items(draft, checklist)
    assert not any("twfe" in m.lower() or "did" in m.lower() or "callaway" in m.lower() for m in missing)
    assert not any("sun" in m.lower() and "abraham" in m.lower() for m in missing)


def test_extract_html_and_preview_url():
    html = extract_html_document(
        "вот:\n```html\n<!doctype html><html><body><button>Go</button></body></html>\n```"
    )
    assert html and "<button>" in html
    assert extract_preview_url("see http://127.0.0.1:5173/app") == "http://127.0.0.1:5173/app"
    assert extract_preview_url("x", zeus={"preview_url": "https://example.com"}) == "https://example.com"


def test_ui_live_verify_skips_without_daemon(monkeypatch):
    from app.fusion import ui_live_verify as mod

    monkeypatch.setattr(mod, "browser_available", lambda: False)
    res = asyncio.run(
        mod.run_ui_live_verify(
            answer="<!doctype html><html><body>hi</body></html>",
            user_q="check",
        )
    )
    assert res.get("skipped") is True
    assert res.get("error") in ("browser_unavailable", "disabled")
