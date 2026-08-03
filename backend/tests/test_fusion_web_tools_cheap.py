"""Cheap web research: compress + browser escalate only when thin."""

from __future__ import annotations

import asyncio

from app.fusion.web_tools import (
    compress_for_critics,
    extract_filing_figures,
    format_refs_for_prompt,
    is_sec_filing_url,
    research_pack_for_critics,
    research_queries,
    reset_web_caches_for_tests,
    web_search,
    _sec_period_matches,
    _sec_period_suffix,
)


def test_extract_filing_figures_ocf_and_debt():
    blob = (
        "(in millions) "
        "Cash and cash equivalents $ 1,405.3 $ 2,892.4 "
        "Long-term debt 3,419.4 2,678.2 "
        "Net Cash Provided by Operating Activities 1,116.6 892.7 "
        "Cash Flows from Investing Activities Proceeds from maturities "
    )
    figs = extract_filing_figures(blob)
    joined = " | ".join(figs).lower()
    assert any("operating" in f.lower() or "ocf" in f.lower() for f in figs)
    assert "1,116.6" in joined
    assert any("long-term debt" in f.lower() for f in figs)
    assert "3,419.4" in joined


def test_extract_filing_figures_used_in_and_parens():
    blob = (
        "Net cash provided by (used in) operating activities 11,477 ( 321,285 ) "
        "Investing activities: Cash paid for acquisitions "
    )
    figs = extract_filing_figures(blob)
    joined = " ".join(figs)
    assert "11,477" in joined
    assert "321,285" in joined


def test_extract_reit_margins_and_renaissance_purchase():
    blob = (
        "Core Portfolio Funds Structured Financing Unallocated Total "
        "Total Revenues $ 53,538 $ 37,818 $ $ $ 91,356 "
        "Depreciation and amortization expenses ( 18,267 ) ( 16,673 ) ( 34,940 ) "
        "General and administrative expenses ( 9,768 ) ( 9,768 ) "
        "Property operating expenses, other operating and real estate taxes "
        "( 17,919 ) ( 13,523 ) ( 31,442 ) "
        "Operating income 17,352 6,424 ( 9,768 ) 14,008 "
        "acquired an additional 48 % economic ownership interest, and increased its "
        "existing 20 % interest to 68 %, in the Renaissance Portfolio primarily "
        "located in Washington D.C. The 48 % interest was acquired for a purchase "
        "price of $ 117.9 million, based upon a gross portfolio fair value of "
        "$ 245.7 million, which included existing mortgage loan indebtedness of "
        "$ 156.1 million in aggregate. recognized a $ 9.6 million loss on change "
        "in control. the venture modified the property mortgage loan to reduce "
        "the interest rate to SOFR + 1.55 %. This reduction was achieved through "
        "a $ 50.0 million principal paydown. "
        # Noise that must NOT win over Renaissance ownership:
        "Ownership interest increased from 91.85% to 94.35% at Gotham Plaza. "
        "Principal paydown / repayment $807 million term loan unrelated. "
    )
    figs = extract_filing_figures(blob)
    joined = " ".join(figs)
    assert "32.4%" in joined
    assert "17.0%" in joined
    assert "15.4" in joined
    assert "117.9" in joined
    assert "20%" in joined and "68%" in joined
    assert "91.85" not in joined
    assert "50.0" in joined
    assert "SOFR" in joined and "1.55" in joined
    assert "9.6" in joined


def test_extract_bond_notes_and_sbc():
    blob = (
        "(in thousands) "
        "Stock-based compensation expense 2,757 1,578 "
        # CME-style — face+due+coupon must stay atomic (no remix with table peers).
        "$750.0 million fixed rate notes due March 2025, stated rate of 3.00% "
        "$500.0 million fixed rate notes due June 2028, stated rate of 3.75% "
        "$750.0 million fixed rate notes due March 2030, stated rate of 4.4% "
        "$750.0 million fixed rate notes due March 2032, stated rate of 2.65% "
        "$750.0 million fixed rate notes due September 2043, stated rate of 5.30% "
    )
    figs = extract_filing_figures(blob)
    joined = " ".join(figs).lower()
    assert "stock-based" in joined or "sbc" in joined
    assert "2,757" in joined or "2757" in joined.replace(",", "")
    # Exact triples (regression: old regex paired $750m with 3.75%/June 2028).
    assert "500.0" in joined and "3.75" in joined and "june 2028" in joined
    assert "750.0" in joined and "2.65" in joined and "march 2032" in joined
    assert "5.30" in joined and "september 2043" in joined
    assert not (
        "fixed-rate notes: $750.0 million at 3.75% due june 2028" in joined
        or "fixed-rate notes: $750.0 million at 3.00% due june 2028" in joined
    )


def test_research_queries_nvidia_not_generic_cpu_datasheet():
    qs = research_queries(
        "Compare YOLO v8 and NVIDIA TAO DetectNet_v2 on Jetson AGX Orin INT8",
        school="researcher_a",
    )
    blob = " ".join(qs).lower()
    assert "nvidia" in blob or "tao" in blob or "detectnet" in blob
    assert "filetype:pdf" not in blob


def test_research_queries_machine_tools_cover_all_oems():
    qs = research_queries(
        "Choose DMG MORI NLX 2500SY vs Mazak Integrex i-400S vs Okuma Multus U4000",
        school="researcher_a",
    )
    blob = " ".join(qs).lower()
    assert "nlx" in blob or "dmg" in blob
    assert "integrex" in blob or "mazak" in blob
    assert "multus" in blob or "okuma" in blob


def test_sec_period_prefers_first_quarter():
    q = "margins in Q1 2024 vs Q1 2025 for Acadia Realty"
    assert _sec_period_suffix(q) == "20240331"
    assert _sec_period_matches(q) == ["20240331", "20250331"]


def test_sec_pick_period_seeds_covers_each_named_quarter():
    from app.fusion.web_tools import _sec_pick_period_seeds

    rows = [
        {
            "title": "CME GROUP INC (CME)",
            "url": "https://www.sec.gov/Archives/edgar/data/1156375/000115637523000190/cme-20230930.htm",
        },
        {
            "title": "CME GROUP INC (CME)",
            "url": "https://www.sec.gov/Archives/edgar/data/1156375/000115637524000072/cme-20240331.htm",
        },
        {
            "title": "CME GROUP INC (CME)",
            "url": "https://www.sec.gov/Archives/edgar/data/1156375/000115637525000103/cme-20250331.htm",
        },
    ]
    picked = _sec_pick_period_seeds(
        rows,
        period_suffixes=["20240331", "20250331"],
        needles=["CME", "CME GROUP"],
        max_n=3,
    )
    names = " ".join(r["url"] for r in picked)
    assert "20240331" in names
    assert "20250331" in names


def test_research_queries_use_query_years_not_hardcoded_2025():
    qs = research_queries(
        "Analyze Acadia Realty Trust Core Portfolio Q1 2024 operating margins",
        school="researcher_a",
    )
    blob = " ".join(qs).lower()
    assert "2024" in blob
    # Must not force a lone 2025 bias when query only names 2024.
    assert "2025" not in blob or "2024" in blob


def test_research_queries_non_finance_never_default_to_10q():
    qs = research_queries(
        "There's been a lot of talk about how quantum computing is progressing "
        "toward practical applications in drug discovery and cryptography",
        school="researcher_a",
    )
    blob = " ".join(qs).lower()
    assert "10-q" not in blob
    assert "earnings" not in blob
    assert "wellcome" in blob or "quantinuum" in blob or "ionq" in blob


def test_research_queries_hci_and_stat_extract():
    from app.fusion.web_tools import extract_stat_figures

    hci = " ".join(
        research_queries(
            "ERP interfaces transitioning from AS/400 with hamburger navigation "
            "and progressive disclosure for manufacturing supervisors",
            school="escalate",
        )
    ).lower()
    assert "hamburger" in hci or "discoverability" in hci
    assert "as/400" not in hci or "discoverability" in hci

    stats = extract_stat_figures(
        "In Camp-4, approximately 71.6% of Rohingya refugee women reported antenatal care. "
        "In 2018 facility-based delivery reached 22%. Hidden navigation slows task "
        "completion by approximately 30-40% compared to persistent navigation."
    )
    blob = " ".join(stats).lower()
    assert "71.6%" in blob
    assert "30-40%" in blob or "30" in blob


def test_research_queries_humanitarian_and_ncd_and_fridge():
    roh = " ".join(
        research_queries(
            "Analyze maternal mortality among Rohingya in Cox's Bazar vs Mae La",
            school="researcher_a",
        )
    ).lower()
    assert "rohingya" in roh or "maternal" in roh
    assert "10-q" not in roh

    ncd = " ".join(
        research_queries(
            "Analyze NCD IPOs open in India as of Dec 8th 2025",
            school="researcher_a",
        )
    ).lower()
    assert "ncd" in ncd or "debenture" in ncd
    assert "india" in ncd

    fridge = " ".join(
        research_queries(
            "Compare Panasonic MDF-DU702VH-PA, Helmer GX Solutions, and "
            "Thermo Fisher TSX Series for vaccine storage",
            school="researcher_a",
        )
    ).lower()
    assert "helmer" in fridge
    assert "thermo" in fridge or "tsx" in fridge


def test_extract_entities_vticker_and_quantum_topic():
    from app.fusion.web_tools import extract_research_entities, is_offtopic_finance_url

    ents = extract_research_entities(
        "Evaluate vTv's equity financing and share-based compensation 2023-2024"
    )
    blob = " ".join(ents).lower()
    assert "vtv" in blob

    q_ents = extract_research_entities(
        "There's been a lot of talk about how quantum computing is progressing"
    )
    assert any("quantum" in e.lower() for e in q_ents)

    assert is_offtopic_finance_url(
        "https://www.investopedia.com/terms/c/cash-flow-from-operating-activities.asp",
        "quantum computing drug discovery",
    )
    assert not is_offtopic_finance_url(
        "https://www.sec.gov/Archives/edgar/data/1/a.htm",
        "vTv Therapeutics 10-Q share-based compensation",
    )



def test_is_sec_filing_url():
    assert is_sec_filing_url(
        "https://www.sec.gov/Archives/edgar/data/1156375/000115637525000103/cme-20250331.htm"
    )
    assert not is_sec_filing_url("https://example.com/10-q-summary")


def test_prioritize_figures_for_query_puts_matching_period_first():
    from app.fusion.web_tools import prioritize_figures_for_query

    figs = [
        "[period 2025-03-31] OCF: 999",
        "[period 2024-03-31] OCF: 111",
        "unlabeled margin: 10%",
    ]
    out = prioritize_figures_for_query(
        "Core Portfolio operating margin in Q1 2024 vs Q1 2025", figs
    )
    assert "2024-03-31" in out[0]


def test_format_refs_surfaces_filing_figures_first():
    pack = {
        "filing_figures": [
            "Net cash from operating activities (OCF): 1,116.6; 892.7 (in millions)",
        ],
        "refs": [
            {
                "title": "CME 10-Q",
                "url": "https://www.sec.gov/Archives/edgar/data/1/2/cme.htm",
                "snippet": "10-Q",
                "text": "FILING FIGURES:\n- Net cash from operating activities (OCF): 1,116.6; 892.7\n\nother text",
                "filing_figures": [
                    "Net cash from operating activities (OCF): 1,116.6; 892.7 (in millions)",
                ],
                "fetch_backend": "httpx",
                "ref_kind": "sec_filing",
            }
        ],
        "browser_used": 0,
        "browser_available": False,
    }
    text = format_refs_for_prompt(pack, char_budget=1200)
    assert "Filing figures" in text
    assert "1,116.6" in text
    assert text.index("Filing figures") < text.index("sec.gov")


def test_compress_keeps_craft_signals_and_caps():
    blob = (
        "Cookie policy accept all tracking partners forever. " * 20
        + "Hero section with booking CTA and sticky mobile nav for services. "
        + "Warranty trust bar and pricing from 1500. "
        + "Lorem ipsum dolor sit amet " * 40
    )
    out = compress_for_critics(blob, limit=400)
    assert len(out) <= 400
    assert "hero" in out.lower() or "cta" in out.lower() or "nav" in out.lower()


def test_format_refs_respects_budget():
    pack = {
        "refs": [
            {
                "title": "A",
                "url": "https://example.com/a",
                "snippet": "hero cta",
                "text": "Hero booking CTA sticky nav services pricing reviews FAQ " * 80,
                "fetch_backend": "jina",
            },
            {
                "title": "B",
                "url": "https://example.com/b",
                "snippet": "x",
                "text": "More services and warranty trust signals " * 80,
                "fetch_backend": "jina",
            },
        ],
        "browser_used": 0,
        "browser_available": False,
    }
    text = format_refs_for_prompt(pack, char_budget=900)
    assert len(text) <= 980
    assert "example.com/a" in text
    assert "browser daemon off" in text


def test_research_pack_escalates_browser_once(monkeypatch):
    async def fake_search(query, max_results=None):
        return {
            "ok": True,
            "degraded": False,
            "backend": "test",
            "results": [
                {"title": "Thin", "url": "https://example.com/thin", "snippet": "ok"},
                {"title": "Fat", "url": "https://example.com/fat", "snippet": "hero cta nav"},
            ],
        }

    async def fake_fetch(url, limit=2500):
        if "thin" in url:
            return {"ok": True, "degraded": False, "url": url, "text": "short", "backend": "jina"}
        fat = (
            "Hero section with clear booking CTA. Sticky mobile nav. "
            "Six services with pricing. Warranty trust bar. FAQ accordion. "
        ) * 5
        return {"ok": True, "degraded": False, "url": url, "text": fat, "backend": "jina"}

    calls = {"n": 0}

    async def fake_browser(url, max_chars=2200):
        calls["n"] += 1
        return {
            "ok": True,
            "degraded": False,
            "url": url,
            "text": "Browser hero CTA sticky nav booking form services pricing reviews",
            "backend": "browser",
        }

    monkeypatch.setattr("app.fusion.web_tools.web_search", fake_search)
    monkeypatch.setattr("app.fusion.web_tools.web_fetch", fake_fetch)
    monkeypatch.setattr("app.fusion.web_tools.browser_available", lambda: True)
    monkeypatch.setattr("app.fusion.web_tools.browser_fetch_text", fake_browser)
    monkeypatch.setattr(
        "app.fusion.web_tools._cfg",
        lambda: {
            "max_results": 3,
            "max_fetch": 3,
            "char_budget": 4200,
            "extract_chars": 850,
            "browser_max": 1,
            "browser_live": 0,
            "browser_chars": 2200,
            "cache_ttl": 0,
            "search_conc": 4,
            "browser_slots": 2,
            "serp_timeout": 12.0,
        },
    )
    reset_web_caches_for_tests()

    pack = asyncio.run(research_pack_for_critics("автосервис сайт"))
    assert pack["ok"] is True
    assert pack["browser_used"] == 1
    assert calls["n"] == 1
    assert any(r.get("browser_escalated") for r in pack["refs"])


def test_research_pack_standard_three_refs(monkeypatch):
    async def fake_search(query, max_results=None):
        return {
            "ok": True,
            "backend": "test",
            "results": [
                {"title": f"R{i}", "url": f"https://example.com/r{i}", "snippet": "hero cta nav"}
                for i in range(1, 5)
            ],
        }

    async def fake_fetch(url, limit=2500):
        body = (
            "Hero section with booking CTA. Sticky mobile nav. "
            "Services pricing warranty reviews FAQ. "
        ) * 4
        return {"ok": True, "url": url, "text": body, "backend": "jina"}

    monkeypatch.setattr("app.fusion.web_tools.web_search", fake_search)
    monkeypatch.setattr("app.fusion.web_tools.web_fetch", fake_fetch)
    monkeypatch.setattr("app.fusion.web_tools.browser_available", lambda: False)

    pack = asyncio.run(research_pack_for_critics("автосервис сайт"))
    assert len(pack["refs"]) == 3
    assert pack["ok"] is True


def test_research_pack_skips_browser_when_unavailable(monkeypatch):
    async def fake_search(query, max_results=None):
        return {
            "ok": True,
            "backend": "test",
            "results": [{"title": "T", "url": "https://example.com/x", "snippet": ""}],
        }

    async def fake_fetch(url, limit=2500):
        return {"ok": False, "url": url, "text": "", "backend": "httpx"}

    async def boom(*a, **k):
        raise AssertionError("browser must not be called")

    monkeypatch.setattr("app.fusion.web_tools.web_search", fake_search)
    monkeypatch.setattr("app.fusion.web_tools.web_fetch", fake_fetch)
    monkeypatch.setattr("app.fusion.web_tools.browser_available", lambda: False)
    monkeypatch.setattr("app.fusion.web_tools.browser_fetch_text", boom)

    pack = asyncio.run(research_pack_for_critics("landing page"))
    assert pack["browser_used"] == 0
    assert pack["browser_available"] is False


def test_web_search_cache_hit(monkeypatch):
    reset_web_caches_for_tests()
    calls = {"n": 0}

    async def fake_ddg(query, n):
        calls["n"] += 1
        return {
            "ok": True,
            "degraded": False,
            "results": [{"title": "A", "url": "https://example.com/a", "snippet": "x"}],
            "backend": "duckduckgo_html",
            "error": None,
        }

    monkeypatch.setattr("app.fusion.web_tools._tavily_key", lambda: "")
    monkeypatch.setattr("app.fusion.web_tools._web_search_ddg", fake_ddg)
    monkeypatch.setattr(
        "app.fusion.web_tools._cfg",
        lambda: {
            "max_results": 3,
            "max_fetch": 3,
            "char_budget": 4200,
            "extract_chars": 850,
            "browser_max": 0,
            "browser_live": 0,
            "browser_chars": 2200,
            "cache_ttl": 900,
            "search_conc": 4,
            "browser_slots": 0,
            "serp_timeout": 12.0,
        },
    )

    async def run():
        a = await web_search("cache me please query", max_results=3)
        b = await web_search("cache me please query", max_results=3)
        return a, b

    a, b = asyncio.run(run())
    assert a["ok"] and b["ok"]
    assert calls["n"] == 1
    assert b.get("cache_hit") is True
