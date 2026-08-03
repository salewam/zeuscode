#!/usr/bin/env python3
"""Smoke free-first web research stack (no API key required).

Usage:
  PYTHONPATH=backend .venv/bin/python backend/scripts/smoke_web_research.py
"""

from __future__ import annotations

import asyncio
import sys
import time


async def main() -> int:
    from app.fusion.roles import assign_role_model, resolve_stack
    from app.fusion.web_tools import (
        research_pack_for_critics,
        reset_web_caches_for_tests,
        web_search,
    )

    reset_web_caches_for_tests()
    queries = [
        "CME Group Q1 2025 operating cash flow 10-Q",
        "Goodman-Bacon staggered Difference-in-Differences TWFE",
        "Acadia Realty Trust Q1 2024 earnings Renaissance",
    ]
    ok_n = 0
    for q in queries:
        t0 = time.perf_counter()
        s = await web_search(q, max_results=4)
        dt = time.perf_counter() - t0
        n = len(s.get("results") or [])
        print(f"SEARCH backend={s.get('backend')} ok={s.get('ok')} n={n} {dt:.1f}s :: {q[:56]}")
        if s.get("ok") and n:
            ok_n += 1
            for r in (s.get("results") or [])[:2]:
                print(f"  - {(r.get('title') or '')[:64]} | {(r.get('url') or '')[:88]}")
        else:
            print(f"  ERR {s.get('error')}")

    t0 = time.perf_counter()
    pack = await research_pack_for_critics(
        "Analyze CME Group cash generation Q1 2024 to Q1 2025 operating cash flow",
        school="researcher_a",
    )
    dt = time.perf_counter() - t0
    refs = pack.get("refs") or []
    with_text = sum(1 for r in refs if (r.get("text") or r.get("snippet")))
    print(
        f"PACK ok={pack.get('ok')} backend={pack.get('backend')} "
        f"refs={len(refs)} usable={with_text} browser={pack.get('browser_used')} {dt:.1f}s"
    )
    for r in refs[:3]:
        print(
            f"  REF fetch={r.get('fetch_backend')} chars={len(r.get('text') or '')} "
            f"{(r.get('url') or '')[:88]}"
        )

    # cache hit
    t0 = time.perf_counter()
    pack2 = await research_pack_for_critics(
        "Analyze CME Group cash generation Q1 2024 to Q1 2025 operating cash flow",
        school="researcher_a",
    )
    print(f"CACHE_HIT={bool(pack2.get('cache_hit'))} {time.perf_counter() - t0:.2f}s")

    st = resolve_stack("power")
    models = {
        role: assign_role_model(role, "power", st).model_id
        for role in ("researcher_a", "researcher_b", "researcher_c")
    }
    print("ROLES", models)
    distinct = len(set(models.values()))
    print(f"ROLE_DIVERSITY distinct={distinct}/3")

    passed = ok_n >= 2 and pack.get("ok") and with_text >= 1 and distinct >= 2
    print("RESULT", "PASS" if passed else "FAIL", f"search_ok={ok_n}/3 pack_ok={pack.get('ok')}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
