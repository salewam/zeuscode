"""Cheap public-web research for Fusion critics.

Cost ladder (cheapest first):
  1) Tavily / DuckDuckGo HTML search
  2) Jina / httpx fetch (no browser)
  3) browser-daemon navigate+get-text — only if cheap text is thin, ≤1 page

Token rules: compress extracts to craft signals; shared pack; tight char budgets.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus, unquote, urlparse

import httpx

from .browser_client import (
    browser_available,
    browser_fetch_text,
    web_get_text,
    web_navigate,
)

log = logging.getLogger("zeus.fusion.web")

_UA = "ZeusFusionResearch/0.1 (+public research; no cookies)"

_CRAFT_RE = re.compile(
    r"(?i)(hero|cta|nav|menu|booking|appoint|price|pricing|service|услуг|"
    r"отзыв|review|faq|mobile|responsive|warranty|гарант|trust|записы|"
    r"phone|телефон|адрес|hours|часов|button|form|sticky)"
)


def research_enabled() -> bool:
    try:
        from app.config import get_settings

        return bool(get_settings().WEB_RESEARCH_ENABLED)
    except Exception:  # noqa: BLE001
        return True


def _cfg() -> dict[str, Any]:
    try:
        from app.config import get_settings

        s = get_settings()
        return {
            "max_results": max(1, int(getattr(s, "WEB_RESEARCH_MAX_RESULTS", 2) or 2)),
            "max_fetch": max(1, int(getattr(s, "WEB_RESEARCH_MAX_FETCH", 2) or 2)),
            "char_budget": max(800, int(getattr(s, "WEB_REFS_CHAR_BUDGET", 2800) or 2800)),
            "extract_chars": max(300, int(getattr(s, "WEB_REF_EXTRACT_CHARS", 900) or 900)),
            "browser_max": max(0, int(getattr(s, "WEB_BROWSER_MAX_PAGES", 1) or 1)),
            "browser_live": max(0, int(getattr(s, "WEB_BROWSER_LIVE_COMPETITORS", 2) or 2)),
            "browser_chars": max(400, int(getattr(s, "WEB_BROWSER_FETCH_CHARS", 2200) or 2200)),
        }
    except Exception:  # noqa: BLE001
        return {
            "max_results": 3,
            "max_fetch": 3,
            "char_budget": 4200,
            "extract_chars": 850,
            "browser_max": 2,
            "browser_live": 2,
            "browser_chars": 2200,
        }


def _tavily_key() -> str:
    try:
        from app.config import get_settings

        return (get_settings().TAVILY_API_KEY or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _strip_html(raw: str, *, limit: int = 4000) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw or "")
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"&\w+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def compress_for_critics(text: str, *, limit: int = 900) -> str:
    """Keep craft-relevant sentences; drop boilerplate. Hard char cap."""
    raw = " ".join((text or "").split())
    if not raw:
        return ""
    if len(raw) <= limit:
        return raw
    # Prefer sentences with craft keywords
    parts = re.split(r"(?<=[.!?…])\s+|\n+", raw)
    picked: list[str] = []
    used = 0
    for p in parts:
        s = p.strip()
        if len(s) < 25:
            continue
        if _CRAFT_RE.search(s) or not picked:
            if used + len(s) + 1 > limit:
                remain = limit - used - 1
                if remain > 40:
                    picked.append(s[:remain])
                break
            picked.append(s)
            used += len(s) + 1
            if used >= limit:
                break
    out = " ".join(picked).strip()
    return (out or raw[:limit])[:limit]


def _thin_text(text: str, snippet: str = "") -> bool:
    t = (text or "").strip()
    if len(t) < 280:
        return True
    # Mostly nav junk / cookie walls
    low = t.lower()
    if low.count("cookie") + low.count("subscribe") > 6 and len(t) < 800:
        return True
    if not _CRAFT_RE.search(t) and len((snippet or "").strip()) < 40:
        return True
    return False


async def web_search_via_google(query: str, *, max_results: int | None = None) -> dict[str, Any]:
    """DJARVIS-style search: navigate Google HTML results + get-text / link scrape.

    Used when Tavily/DDG are thin and browser-daemon is up. Degrades honestly.
    """
    q = (query or "").strip()
    if not q:
        return {
            "ok": False,
            "degraded": True,
            "results": [],
            "backend": "google_browser",
            "error": "empty_query",
        }
    if not browser_available():
        return {
            "ok": False,
            "degraded": True,
            "results": [],
            "backend": "google_browser",
            "error": "unavailable",
        }
    n = max_results if max_results is not None else _cfg()["max_results"]
    url = f"https://www.google.com/search?q={quote_plus(q)}&hl=en&num={max(5, n)}"
    nav = await web_navigate(url)
    if not nav.get("ok"):
        return {
            "ok": False,
            "degraded": True,
            "results": [],
            "backend": "google_browser",
            "error": nav.get("error") or "navigate_failed",
        }
    # Prefer evaluate-free path: get-text for snippets; URLs from cheap httpx of same SERP as backup
    gt = await web_get_text(max_chars=4000)
    text = str(gt.get("text") or "")
    results: list[dict[str, Any]] = []
    # Pull http(s) URLs mentioned in visible text (rough but daemon-true)
    for m in re.finditer(r"https?://[^\s\"'<>]+", text):
        href = m.group(0).rstrip(".,);]")
        host = urlparse(href).netloc.lower()
        if not host or "google." in host or "gstatic." in host:
            continue
        if any(r["url"] == href for r in results):
            continue
        results.append({"title": "", "url": href, "snippet": text[:160]})
        if len(results) >= n:
            break
    if len(results) < n:
        # Fallback: fetch SERP HTML cheaply for result links while page is warm
        try:
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True, headers={"User-Agent": _UA}
            ) as client:
                r = await client.get(url)
                html = r.text or ""
            for m in re.finditer(r'href="(https?://[^"]+)"', html):
                href = m.group(1)
                host = urlparse(href).netloc.lower()
                if not host or "google." in host or "gstatic." in host or "youtube.com" in host:
                    continue
                if any(r["url"] == href for r in results):
                    continue
                results.append({"title": "", "url": href, "snippet": ""})
                if len(results) >= n:
                    break
        except Exception as e:  # noqa: BLE001
            log.debug("google serp html scrape: %s", e)
    return {
        "ok": bool(results),
        "degraded": not bool(results),
        "results": results[:n],
        "backend": "google_browser",
        "page_text_chars": len(text),
    }


async def web_search(query: str, *, max_results: int | None = None) -> dict[str, Any]:
    """Return {ok, degraded, results:[{title,url,snippet}], backend}."""
    if not research_enabled():
        return {
            "ok": False,
            "degraded": True,
            "results": [],
            "backend": "disabled",
            "error": "WEB_RESEARCH_ENABLED=false",
        }
    q = (query or "").strip()
    if not q:
        return {"ok": False, "degraded": True, "results": [], "backend": "none", "error": "empty_query"}
    n = max_results if max_results is not None else _cfg()["max_results"]
    key = _tavily_key()
    if key:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": key,
                        "query": q,
                        "max_results": n,
                        "include_answer": False,
                    },
                )
                if r.status_code < 400:
                    data = r.json()
                    results = []
                    for item in (data.get("results") or [])[:n]:
                        results.append(
                            {
                                "title": str(item.get("title") or "")[:160],
                                "url": str(item.get("url") or ""),
                                "snippet": str(item.get("content") or item.get("snippet") or "")[:220],
                            }
                        )
                    return {"ok": bool(results), "degraded": False, "results": results, "backend": "tavily"}
                log.warning("tavily search status=%s", r.status_code)
        except Exception as e:  # noqa: BLE001
            log.warning("tavily search failed: %s", e)

    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(q)}"
        async with httpx.AsyncClient(
            timeout=20.0, follow_redirects=True, headers={"User-Agent": _UA}
        ) as client:
            r = await client.get(url)
            html = r.text or ""
        results = []
        for m in re.finditer(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</(?:a|td)',
            html,
            re.I | re.S,
        ):
            href, title, snip = m.group(1), m.group(2), m.group(3)
            if "uddg=" in href:
                um = re.search(r"uddg=([^&]+)", href)
                if um:
                    href = unquote(um.group(1))
            title = _strip_html(title, limit=140)
            snip = _strip_html(snip, limit=200)
            if href.startswith("http"):
                results.append({"title": title, "url": href, "snippet": snip})
            if len(results) >= n:
                break
        if not results:
            for m in re.finditer(r'href="(https?://[^"]+)"[^>]*class="result__a"', html, re.I):
                href = m.group(1)
                if "duckduckgo.com" in href:
                    continue
                results.append({"title": "", "url": href, "snippet": ""})
                if len(results) >= n:
                    break
        if results:
            return {
                "ok": True,
                "degraded": False,
                "results": results,
                "backend": "duckduckgo_html",
            }
        # Empty SERP → try Google via browser-daemon (DJARVIS path)
        gb = await web_search_via_google(q, max_results=n)
        if gb.get("ok"):
            return gb
        return {
            "ok": False,
            "degraded": True,
            "results": [],
            "backend": "duckduckgo_html",
            "error": "empty_results",
            "google_browser_error": gb.get("error"),
        }
    except Exception as e:  # noqa: BLE001
        log.warning("ddg search failed: %s", e)
        # Last resort: DJARVIS browser → Google (same idea as Jarvis search)
        gb = await web_search_via_google(q, max_results=n)
        if gb.get("ok"):
            return gb
        return {
            "ok": False,
            "degraded": True,
            "results": [],
            "backend": "error",
            "error": str(e)[:200],
            "google_browser_error": gb.get("error"),
        }


async def web_fetch(url: str, *, limit: int = 2500) -> dict[str, Any]:
    """Cheap fetch: Jina then httpx. No browser."""
    if not research_enabled():
        return {"ok": False, "degraded": True, "url": url, "text": "", "backend": "disabled"}
    u = (url or "").strip()
    if not u.startswith("http"):
        return {"ok": False, "degraded": True, "url": u, "text": "", "error": "bad_url"}
    host = urlparse(u).netloc.lower()
    if any(x in host for x in ("facebook.com", "instagram.com", "tiktok.com", "youtube.com")):
        return {"ok": False, "degraded": True, "url": u, "text": "", "error": "skipped_host"}

    try:
        jina = f"https://r.jina.ai/{u}"
        async with httpx.AsyncClient(
            timeout=22.0, follow_redirects=True, headers={"User-Agent": _UA}
        ) as client:
            r = await client.get(jina)
            if r.status_code < 400 and (r.text or "").strip():
                text = (r.text or "").strip()[:limit]
                return {"ok": True, "degraded": False, "url": u, "text": text, "backend": "jina"}
    except Exception as e:  # noqa: BLE001
        log.debug("jina fetch fail: %s", e)

    try:
        async with httpx.AsyncClient(
            timeout=22.0, follow_redirects=True, headers={"User-Agent": _UA}
        ) as client:
            r = await client.get(u)
            if r.status_code >= 400:
                return {
                    "ok": False,
                    "degraded": True,
                    "url": u,
                    "text": "",
                    "backend": "httpx",
                    "error": f"HTTP {r.status_code}",
                }
            text = _strip_html(r.text or "", limit=limit)
            return {"ok": bool(text), "degraded": not bool(text), "url": u, "text": text, "backend": "httpx"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "degraded": True, "url": u, "text": "", "backend": "error", "error": str(e)[:200]}


_ROUNDUP_HINTS = (
    "colorlib",
    "webcitz",
    "squarestash",
    "awwwards",
    "land-book",
    "lapa.ninja",
    "onepagelove",
    "medium.com",
    "blog.",
    "/blog/",
    "inspiration",
    "examples",
    "best-",
    "top-",
    "portfolio",
)


def _looks_like_live_competitor(url: str) -> bool:
    u = (url or "").lower()
    if not u.startswith("http"):
        return False
    return not any(h in u for h in _ROUNDUP_HINTS)


def niche_queries(user_q: str) -> list[str]:
    """Mix of design roundups + real competitor-site queries."""
    q = " ".join((user_q or "").split())
    short = q[:90]
    low = q.lower()
    if any(x in low for x in ("автосервис", "сто", "шиномонтаж", "auto service", "repair shop", "моторхаус")):
        return [
            "автосервис сайт запись онлайн",
            "car repair shop website book appointment",
            "best auto repair shop website design examples",
        ]
    return [
        f"{short} official website",
        f"{short} booking website",
        f"{short} best landing page examples",
    ]


async def research_pack_for_critics(user_q: str) -> dict[str, Any]:
    """Search + cheap fetch; browser on thin pages AND live competitors."""
    if not research_enabled():
        return {"ok": False, "degraded": True, "refs": [], "queries": [], "backend": "disabled"}
    cfg = _cfg()
    max_r, max_f = cfg["max_results"], cfg["max_fetch"]
    queries = niche_queries(user_q)
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    backends: list[str] = []
    browser_used = 0
    browser_max = cfg["browser_max"] if browser_available() else 0
    live_budget = cfg.get("browser_live", 2) if browser_available() else 0
    live_used = 0

    for q in queries:
        sr = await web_search(q, max_results=max_r)
        backends.append(str(sr.get("backend") or ""))
        # Prefer live competitor URLs earlier in the pack
        items = list(sr.get("results") or [])
        items.sort(key=lambda it: (0 if _looks_like_live_competitor(str(it.get("url") or "")) else 1))
        for item in items:
            u = str(item.get("url") or "")
            if not u or u in seen:
                continue
            seen.add(u)
            live = _looks_like_live_competitor(u)
            fr = await web_fetch(u, limit=max(cfg["extract_chars"] * 2, 1800))
            backends.append(str(fr.get("backend") or ""))
            text = fr.get("text") or ""
            fetch_backend = str(fr.get("backend") or "")
            want_browser = browser_used < browser_max and (
                _thin_text(str(text), str(item.get("snippet") or ""))
                or not fr.get("ok")
                or (live and live_used < live_budget)
            )
            if want_browser:
                br = await browser_fetch_text(u, max_chars=cfg["browser_chars"])
                backends.append("browser")
                if br.get("ok") and (br.get("text") or "").strip():
                    text = br.get("text") or text
                    fetch_backend = "browser"
                    browser_used += 1
                    if live:
                        live_used += 1
                    fr = {**fr, "ok": True, "browser_escalated": True, "live_competitor": live}
                else:
                    fr = {
                        **fr,
                        "browser_attempted": True,
                        "browser_error": br.get("error"),
                        "live_competitor": live,
                    }

            packed = compress_for_critics(str(text), limit=cfg["extract_chars"])
            refs.append(
                {
                    "url": u,
                    "title": item.get("title") or "",
                    "snippet": (item.get("snippet") or "")[:220],
                    "text": packed,
                    "fetch_ok": bool(packed) or bool(fr.get("ok")),
                    "fetch_backend": fetch_backend,
                    "browser_escalated": bool(fr.get("browser_escalated")),
                    "live_competitor": live,
                    "ref_kind": "live_site" if live else "roundup",
                }
            )
            if len(refs) >= max_f:
                break
        if len(refs) >= max_f:
            break

    ok = any(r.get("fetch_ok") or r.get("snippet") for r in refs)
    return {
        "ok": ok,
        "degraded": not ok,
        "refs": refs,
        "queries": queries,
        "backend": ",".join(sorted(set(b for b in backends if b))),
        "browser_used": browser_used,
        "browser_live_used": live_used,
        "browser_available": browser_available(),
    }


def format_refs_for_prompt(pack: dict[str, Any], *, char_budget: int | None = None) -> str:
    cfg = _cfg()
    budget = char_budget if char_budget is not None else cfg["char_budget"]
    extract_n = cfg["extract_chars"]
    parts: list[str] = []
    used = 0
    for i, r in enumerate(pack.get("refs") or [], 1):
        extract = compress_for_critics(str(r.get("text") or ""), limit=extract_n)
        via = r.get("fetch_backend") or ""
        kind = r.get("ref_kind") or ("live_site" if r.get("live_competitor") else "roundup")
        block = (
            f"### Ref {i} [{kind}]: {(r.get('title') or 'untitled')[:80]}\n"
            f"URL: {r.get('url')}\n"
            f"Snippet: {(r.get('snippet') or '')[:180]}\n"
            f"Extract ({via}):\n{extract}\n"
        )
        if used + len(block) > budget:
            # try shorter
            short = (
                f"### Ref {i}: {(r.get('title') or '')[:60]}\n"
                f"URL: {r.get('url')}\n"
                f"{extract[: max(120, budget - used - 80)]}\n"
            )
            if used + len(short) <= budget and extract:
                parts.append(short)
            break
        parts.append(block)
        used += len(block)
    if not parts:
        return "(no live web refs — critique from craft rubric only; mark web_degraded)"
    note = ""
    if pack.get("browser_used"):
        note = f"\n(browser pages used: {pack.get('browser_used')})\n"
    elif pack.get("browser_available") is False:
        note = "\n(browser daemon off — cheap fetch only)\n"
    return "\n".join(parts) + note
