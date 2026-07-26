"""UI Crew: strongest Author + web-informed Critics + Author revise.

Replaces 3-way HTML mash + weak judge rewrite for site/UI tasks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from .model_power import pick_author, pick_critics, power_score, power_scores
from .panel import (
    CancelFlag,
    ExecuteOutcome,
    LiveBranch,
    UpstreamCall,
    _run_one_model,
    billable_for_branch,
    live_to_usage,
)
from .types import PathName
from .web_tools import format_refs_for_prompt, research_pack_for_critics

log = logging.getLogger("zeus.fusion.ui_crew")

_HTML_ASK_RE = re.compile(
    r"(?i)(<!doctype|</html>|\bhtml\b|\bcss\b|лендинг|landing|одностранич|"
    r"сайт|webpage|web\s*page|витрин|hero|вёрстк|верстк)"
)


def is_ui_crew_task(
    *,
    task_kind: str | None,
    user_q: str,
    phase: str | None = None,
) -> bool:
    tk = (task_kind or "").lower()
    ph = (phase or "").lower()
    if tk in ("ui", "design") or ph == "ui":
        return True
    return bool(_HTML_ASK_RE.search(user_q or ""))


def ui_crew_enabled() -> bool:
    try:
        from app.config import get_settings

        return bool(get_settings().FUSION_UI_CREW_ENABLED)
    except Exception:  # noqa: BLE001
        return True


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
    except Exception:  # noqa: BLE001
        return None


def _html_complete(text: str) -> bool:
    t = (text or "").lower()
    return "<html" in t and "</html>" in t


def _has_phone_breakpoint(html: str) -> bool:
    return bool(re.search(r"@media[^{]{0,80}(768|720|640|600|480|420|390)", html or "", re.I))


def _critical_mobile_holes(html: str) -> int:
    """Count blocking mobile failures (viewport / @media / phone bp)."""
    h = html or ""
    low = h.lower()
    n = 0
    if 'name="viewport"' not in low and "name='viewport'" not in low:
        n += 1
    if "@media" not in h:
        n += 2
    elif not _has_phone_breakpoint(h):
        n += 1
    return n


def _gate_keeps_revise(v1: str, v2: str) -> bool:
    if not (v2 or "").strip():
        return False
    if _html_complete(v1) and not _html_complete(v2):
        return False
    if len(v1) > 2000 and len(v2) < int(len(v1) * 0.8):
        return False
    # Keep key signals if present in v1
    for sig in ("@media", "<form", "100vh"):
        if sig in v1 and sig not in v2:
            return False
    if "@media" in v1 and "@media" not in v2:
        return False
    # Hard mobile gate: revise must not worsen critical phone holes
    if _critical_mobile_holes(v2) > _critical_mobile_holes(v1):
        return False
    # If v1 had no @media, revise must add it (otherwise useless polish)
    if "@media" not in (v1 or "") and "@media" not in (v2 or ""):
        return False
    # Prefer phone breakpoint when adding media queries
    if "@media" in (v2 or "") and not _has_phone_breakpoint(v1) and not _has_phone_breakpoint(v2):
        # has @media but no phone width — still accept if better than v1 missing media
        if "@media" not in (v1 or ""):
            return True
        return False
    return True


def _mobile_gaps(html: str) -> list[str]:
    """Deterministic mobile holes for critics (phone UX)."""
    h = html or ""
    low = h.lower()
    gaps: list[str] = []
    if 'name="viewport"' not in low and "name='viewport'" not in low:
        gaps.append("Add <meta name=viewport content=\"width=device-width, initial-scale=1\">")
    if "@media" not in h:
        gaps.append(
            "Add @media (max-width: 768px) and (max-width: 480px): stack grids to 1 col, "
            "shrink hero type, full-width CTA, reduce section padding"
        )
    elif not re.search(r"@media[^{]{0,80}(768|720|640|600|480|420|390)", h, re.I):
        gaps.append("Add a real phone breakpoint (@media max-width 480px or 640px), not only tablet")
    if not re.search(r"hamburger|nav-toggle|menu-btn|aria-expanded|js-nav|nav-open", low):
        if re.search(r"<nav\b", low) and ("flex" in low or "header" in low):
            gaps.append(
                "Mobile nav: hamburger or compact menu; desktop links must not wrap/overflow on ~390px"
            )
    if "position:fixed" in low or "position: sticky" in low or "position:sticky" in low:
        if not re.search(r"safe-area|padding-bottom:\s*\d+|bottom:\s*0", low):
            gaps.append(
                "Fixed/sticky bars need safe spacing on phones (bottom CTA/nav must not cover form fields)"
            )
    if re.search(r"grid-template-columns:\s*repeat\s*\(\s*[3-9]", low) and "@media" not in h:
        gaps.append("Multi-column grids must collapse to 1 column under 768px")
    if re.search(r"font-size:\s*([5-9]\d|\d{3,})px", low) and "@media" not in h:
        gaps.append("Huge desktop type needs clamp() or smaller mobile sizes so hero fits one screen")
    if "<form" in low and not re.search(r"input[^>]*(font-size:\s*16px|font-size:16px)", low):
        # iOS zoom on focus if inputs < 16px — soft hint
        if "font-size:16px" not in low.replace(" ", ""):
            gaps.append("Form inputs on mobile: font-size ≥16px to avoid iOS zoom; full-width fields + large tap targets")
    return gaps[:6]


def _agent_max_tokens() -> int:
    try:
        from app.config import get_settings

        return max(1024, int(get_settings().FUSION_AGENT_MAX_TOKENS or 65536))
    except Exception:  # noqa: BLE001
        return 65536


def _author_retries() -> int:
    try:
        from app.config import get_settings

        return max(0, min(4, int(getattr(get_settings(), "FUSION_UI_AUTHOR_RETRIES", 2) or 2)))
    except Exception:  # noqa: BLE001
        return 2


# Craft rubric: maximally thought-through site (not median AI landing).
CRAFT_RUBRIC = """## Craft rubric (maximally продуманный сайт)
1. Brand-first hero: brand name is the hero signal; one headline + one short line + CTA; full-bleed atmosphere (not flat gray / inset card).
2. Atmosphere: real place/product feel (photo/texture/gradient with intent) — not decorative purple mush.
3. Mobile ≈390px: viewport, @media ≤768 and ≤480, stacked grids, readable type, tap targets ≥44px, usable nav, no horizontal scroll.
4. Motion: 2–3 intentional motions (presence/hierarchy), not noise.
5. Trust density: services with real copy, reviews, FAQ, contacts — not sparse AI filler.
6. Form: working UX (not alert-only if avoidable); inputs ≥16px on phone; sticky bars must not cover fields.
7. Anti-cliché: no Inter/Roboto default stack, no indigo-purple AI theme, no emoji sticker soup, no fake Lorem.
8. Ground upgrades in refs_used (live competitor / niche sites) — steal structure & trust patterns, not copy.
"""


_CRITIC_SYSTEM = f"""You are a Fusion UI critic (NOT the author).
You review the Author's HTML against the user brief AND live web references.
Return JSON only:
{{
  "upgrades": ["concrete improvement 1", "..."],
  "must_fix": ["blocking issue if any"],
  "praise": ["what to keep"],
  "refs_used": ["https://..."],
  "mobile_score": 1
}}
Rules:
- Do NOT rewrite the full HTML.
- Prefer upgrades grounded in refs (layout hierarchy, atmosphere, trust, mobile, CTA clarity).
- MOBILE IS PRIORITY: at least 2 upgrades OR must_fix must be phone-specific
  (≈390px width): stacked layout, readable type, tap targets ≥44px, no horizontal scroll,
  usable nav, hero that fits, sticky CTA that does not hide the form, @media breakpoints.
- mobile_score: 1–5 (5 = excellent on phone). If ≤3, put concrete phone fixes in must_fix.
- Aim for a maximally crafted site using the craft rubric below.
- Keep upgrades actionable and finite (max 10 upgrades, max 6 must_fix).

{CRAFT_RUBRIC}
"""


_REVISE_SYSTEM = f"""You are the Fusion Author revising YOUR OWN HTML.
Apply critic upgrades that improve craft — especially mobile. Preserve visual identity and completeness.
Return ONLY the full final HTML document (no markdown fences, no commentary).
Rules:
- Do not simplify or shrink the page.
- Keep </html> closed.
- MOBILE FIRST IN THIS PASS: ship working @media for ≤768px and ≤480px; stack grids;
  readable type (clamp or smaller mobile sizes); hamburger or compact nav; full-width CTAs;
  form inputs usable on phone (font-size ≥16px); no horizontal overflow; sticky bars must not cover content.
- Prefer adding polish (nav, @media, motion, richer services, better form UX, atmosphere) over redesign from scratch.
- If an upgrade conflicts with a stronger choice already in the HTML, keep the stronger choice —
  except mobile breakage: always fix phone layout.
- Raise the page toward the craft rubric; never average it down into a generic AI landing.

{CRAFT_RUBRIC}
"""


async def execute_ui_crew(
    *,
    panel: list[str],
    leader: str | None,
    messages: list[dict[str, Any]],
    user_q: str,
    policy_path: PathName = "FULL",
    upstream_call: UpstreamCall | None = None,
    cancel_event: CancelFlag = None,
) -> ExecuteOutcome:
    panel = [m for m in (panel or []) if (m or "").strip()][:3]
    author_order = sorted(
        panel,
        key=lambda m: (power_score(m), 1 if leader and m == leader else 0),
        reverse=True,
    )
    scores = power_scores(panel)
    live: list[LiveBranch] = []
    meta: dict[str, Any] = {
        "crew": "ui_author_critics",
        "author": None,
        "critics": [],
        "power_scores": scores,
        "author_attempts": [],
    }

    if not author_order:
        return ExecuteOutcome(
            path="FULL",
            policy_path=policy_path,
            routed_by="ui_crew_disaster",
            answer="",
            leader=leader,
            branches=[],
            live=[],
            disaster=True,
            disaster_code="ui_crew_no_author",
            meta=meta,
        )

    # --- Author v1: retry strongest hard, only then failover ---
    author = ""
    v1 = ""
    author_branch: LiveBranch | None = None
    preferred = author_order[0]
    retries = _author_retries()
    for cand in author_order:
        attempts = (retries + 1) if cand == preferred else 1
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                await asyncio.sleep(min(4.0, 1.2 * attempt))
                log.warning(
                    "ui_crew retry strongest author model=%s attempt=%s/%s",
                    cand,
                    attempt,
                    attempts,
                )
            b = await _run_one_model(
                model_id=cand,
                messages=messages,
                role="A",
                is_leader=True,
                upstream_call=upstream_call,
                temperature=0.45,
                max_tokens=_agent_max_tokens(),
                cancel_event=cancel_event,
            )
            b.meta["crew_role"] = "author_v1"
            b.meta["author_attempt"] = attempt
            b.meta["author_preferred"] = cand == preferred
            live.append(b)
            text = (b.text or "").strip()
            meta["author_attempts"].append(
                {
                    "model": cand,
                    "attempt": attempt,
                    "ok": bool(text),
                    "error": b.error,
                    "preferred": cand == preferred,
                }
            )
            if text:
                author = cand
                author_branch = b
                v1 = text
                break
            log.warning(
                "ui_crew author empty model=%s attempt=%s err=%s",
                cand,
                attempt,
                b.error,
            )
        if v1:
            break

    if not v1 or not author:
        return ExecuteOutcome(
            path="FULL",
            policy_path=policy_path,
            routed_by="ui_crew_disaster",
            answer="",
            leader=leader,
            branches=[live_to_usage(b) for b in live],
            live=live,
            disaster=True,
            disaster_code="ui_author_empty",
            meta=meta,
        )

    critics = pick_critics(panel, author, n=2)
    meta["author"] = author
    meta["critics"] = critics
    # keep pick_author for meta parity / debugging
    meta["author_preferred"] = pick_author(panel, hint=leader)

    # --- Web research pack (shared by critics) ---
    pack = await research_pack_for_critics(user_q)
    meta["web"] = {
        "ok": pack.get("ok"),
        "degraded": pack.get("degraded"),
        "backend": pack.get("backend"),
        "queries": pack.get("queries"),
        "refs_used": [r.get("url") for r in (pack.get("refs") or []) if r.get("url")],
        "browser_used": pack.get("browser_used", 0),
        "browser_live_used": pack.get("browser_live_used", 0),
        "browser_available": pack.get("browser_available"),
        "live_refs": [
            r.get("url")
            for r in (pack.get("refs") or [])
            if r.get("live_competitor") or r.get("ref_kind") == "live_site"
        ],
    }
    refs_prompt = format_refs_for_prompt(pack)
    mobile_gaps = _mobile_gaps(v1)
    meta["mobile_gaps"] = mobile_gaps
    mobile_block = (
        "## Mobile audit (phone ~390px) — treat as must_fix if still true\n- "
        + "\n- ".join(mobile_gaps)
        if mobile_gaps
        else "## Mobile audit\n- Basic signals present; still push polish for 390px phones."
    )

    # --- Critics in parallel ---
    async def _critic_one(mid: str) -> LiveBranch:
        critic_messages = [
            {"role": "system", "content": _CRITIC_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"User brief:\n{(user_q or '')[:4000]}\n\n"
                    f"## Live web references\n{refs_prompt}\n\n"
                    f"{mobile_block}\n\n"
                    # Keep critic context lean — full HTML is Author's job.
                    f"## Author HTML (truncated)\n{v1[:9000]}\n"
                ),
            },
        ]
        b = await _run_one_model(
            model_id=mid,
            messages=critic_messages,
            role="B",
            is_leader=False,
            upstream_call=upstream_call,
            temperature=0.2,
            max_tokens=min(4096, _agent_max_tokens()),
            cancel_event=cancel_event,
        )
        b.meta["crew_role"] = "critic"
        parsed = _extract_json_obj(b.text)
        b.meta["critique"] = parsed or {"raw": (b.text or "")[:800]}
        return b

    if critics:
        critic_branches = await asyncio.gather(*[_critic_one(m) for m in critics])
        live.extend(critic_branches)
    else:
        critic_branches = []

    upgrades: list[str] = []
    must_fix: list[str] = []
    praise: list[str] = []
    critic_refs: list[str] = []
    for b in critic_branches:
        c = b.meta.get("critique") if isinstance(b.meta.get("critique"), dict) else {}
        for key, bucket in (("upgrades", upgrades), ("must_fix", must_fix), ("praise", praise)):
            for item in c.get(key) or []:
                s = str(item).strip()
                if s and s not in bucket:
                    bucket.append(s)
        for ref in c.get("refs_used") or []:
            u = str(ref).strip()
            if u.startswith("http") and u not in critic_refs:
                critic_refs.append(u)

    # Ensure deterministic mobile holes reach the Author even if critics skip them
    for gap in mobile_gaps:
        if gap not in must_fix and gap not in upgrades:
            must_fix.insert(0, gap)
    must_fix = must_fix[:8]

    pack_refs = list((meta.get("web") or {}).get("refs_used") or [])
    refs_used = list(dict.fromkeys([*pack_refs, *critic_refs]))
    meta["refs_used"] = refs_used
    if isinstance(meta.get("web"), dict):
        meta["web"]["critic_refs_used"] = critic_refs
        meta["web"]["refs_used"] = refs_used

    meta["critique_merged"] = {
        "upgrades": upgrades[:12],
        "must_fix": must_fix[:8],
        "praise": praise[:8],
        "mobile_gaps": mobile_gaps,
        "refs_used": refs_used,
    }

    # If no critics / no upgrades — still force mobile revise when gaps exist
    if not upgrades and not must_fix:
        return ExecuteOutcome(
            path="FULL",
            policy_path=policy_path,
            routed_by="ui_author_only",
            answer=v1,
            leader=author,
            branches=[live_to_usage(b) for b in live],
            live=live,
            early_exit="no_upgrades",
            meta=meta,
        )

    # --- Author revise ---
    revise_messages = [
        {"role": "system", "content": _REVISE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"User brief:\n{(user_q or '')[:3000]}\n\n"
                f"Must fix (mobile first):\n- "
                + "\n- ".join(must_fix[:8] or ["(none)"])
                + "\n\n"
                f"Upgrades:\n- " + "\n- ".join(upgrades[:12] or ["(polish mobile + craft)"]) + "\n\n"
                f"Keep / praise:\n- "
                + "\n- ".join(praise[:8] or ["(keep strongest visual choices)"])
                + "\n\n"
                f"Refs used (ground polish in these):\n- "
                + "\n- ".join(refs_used[:8] or ["(no live refs — follow craft rubric)"])
                + "\n\n"
                "Phone check before you finish: open mental viewport 390×844 — no horizontal scroll, "
                "nav usable, hero readable, form tappable, @media present.\n\n"
                f"Your HTML v1:\n{v1[:20000]}\n"
            ),
        },
    ]
    revise_branch = await _run_one_model(
        model_id=author,
        messages=revise_messages,
        role="A",
        is_leader=True,
        upstream_call=upstream_call,
        temperature=0.35,
        max_tokens=_agent_max_tokens(),
        cancel_event=cancel_event,
    )
    revise_branch.meta["crew_role"] = "author_revise"
    live.append(revise_branch)
    v2 = (revise_branch.text or "").strip()
    # Strip accidental fences
    m = re.search(r"```(?:html)?\s*([\s\S]*?)```", v2, re.I)
    if m:
        v2 = m.group(1).strip()

    # Extra mobile-only pass if critical phone holes remain
    cand = v2 if _gate_keeps_revise(v1, v2) else v1
    remain_gaps = _mobile_gaps(cand)
    crit_left = _critical_mobile_holes(cand)
    if crit_left > 0 and remain_gaps:
        mobile_messages = [
            {"role": "system", "content": _REVISE_SYSTEM},
            {
                "role": "user",
                "content": (
                    "MOBILE-ONLY FIX PASS. Keep brand/content. Return full HTML only.\n"
                    "Must fix now:\n- "
                    + "\n- ".join(remain_gaps[:6])
                    + "\n\nCurrent HTML:\n"
                    + cand[:20000]
                ),
            },
        ]
        mob = await _run_one_model(
            model_id=author,
            messages=mobile_messages,
            role="A",
            is_leader=True,
            upstream_call=upstream_call,
            temperature=0.2,
            max_tokens=_agent_max_tokens(),
            cancel_event=cancel_event,
        )
        mob.meta["crew_role"] = "author_mobile_fix"
        live.append(mob)
        mv = (mob.text or "").strip()
        mm = re.search(r"```(?:html)?\s*([\s\S]*?)```", mv, re.I)
        if mm:
            mv = mm.group(1).strip()
        if _gate_keeps_revise(cand, mv) or (
            _html_complete(mv)
            and _critical_mobile_holes(mv) < _critical_mobile_holes(cand)
            and len(mv) >= int(len(cand) * 0.75)
        ):
            v2 = mv
            meta["mobile_fix_pass"] = True
        else:
            meta["mobile_fix_pass"] = False

    if _gate_keeps_revise(v1, v2):
        final = v2
        routed = "ui_author_critics_web"
        early = None
    else:
        final = v1
        routed = "ui_author_rollback"
        early = "revise_regressed"
        meta["rollback_reason"] = "gate_failed"

    meta["mobile_final_gaps"] = _mobile_gaps(final)
    meta["mobile_critical_holes"] = _critical_mobile_holes(final)

    # Normalize billable on author_v1 if revise used tokens (both billable)
    for b in live:
        if b.billable_state == "cancelled_no_tokens" and (b.text or "").strip():
            b.billable_state = billable_for_branch(
                ok=True,
                prompt_tokens=b.prompt_tokens,
                completion_tokens=b.completion_tokens,
                text=b.text,
                cancelled=False,
            )

    return ExecuteOutcome(
        path="FULL",
        policy_path=policy_path,
        routed_by=routed,
        answer=final,
        leader=author,
        branches=[live_to_usage(b) for b in live],
        live=live,
        early_exit=early,
        meta=meta,
    )
