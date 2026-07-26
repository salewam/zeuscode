"""Pipeline v1 orchestrator (Epic 4 / AD-20..26 / FR-18).

Order: Architect Brief → Test Author contracts → isolated parallel doers
→ one RED→FIX cycle → file-aware merge → (TV loop outside).

``fusion/*`` must not import ``routers.*``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .model_power import TEST_AUTHOR_MIN, power_score
from .merge import merge_artifacts_async
from .panel import (
    ExecuteOutcome,
    LiveBranch,
    UpstreamCall,
    _agent_max_tokens,
    _cancelled,
    _default_upstream,
    _run_one_model,
    adapt_prompt_for_family,
    live_to_usage,
    model_family,
)
from .types import BranchUsage

# Soft ceiling (FR-18.9): typical 6–8; hard defect if happy-path >9 without extras
V1_HAPPY_PATH_MAX_CALLS = 9
MID_BAND_LO = 800
MID_BAND_HI = 920

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

_ARCHITECT_SYSTEM = (
    "Ты Architect Zeus Pipeline v1. Ответ — ТОЛЬКО JSON объект:\n"
    '{"components":[{"id":"c1","role":"doer_ui|doer_logic","goal":"...",'
    '"acceptance_one_liner":"...","files_hint":["path"]}],'
    '"api_contract":"...","files_contract":"..."}\n'
    "components length 1..3. Без prose вне JSON."
)

_TEST_AUTHOR_SYSTEM = (
    "Ты Test Author Zeus Pipeline v1. Ответ — ТОЛЬКО JSON:\n"
    '{"tests":[{"component_id":"c1","checks":["short contract check",...]}]}\n'
    "Короткие контрактные checks на компонент (не гигантский suite)."
)


@dataclass
class BriefComponent:
    id: str
    role: str
    goal: str
    acceptance_one_liner: str
    files_hint: list[str] = field(default_factory=list)


@dataclass
class ArchitectBrief:
    components: list[BriefComponent]
    api_contract: str = ""
    files_contract: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "components": [
                {
                    "id": c.id,
                    "role": c.role,
                    "goal": c.goal,
                    "acceptance_one_liner": c.acceptance_one_liner,
                    "files_hint": list(c.files_hint),
                }
                for c in self.components
            ],
            "api_contract": self.api_contract,
            "files_contract": self.files_contract,
        }


def _extract_json(raw: str | dict[str, Any] | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    if text.startswith("```"):
        text = _JSON_FENCE_RE.sub("", text).strip()
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def validate_architect_brief(raw: str | dict[str, Any] | None) -> ArchitectBrief | None:
    """AD-24: components 1..3 with required fields. Invalid → None (degrade)."""
    data = _extract_json(raw)
    if not data:
        return None
    comps = data.get("components")
    if not isinstance(comps, list) or not (1 <= len(comps) <= 3):
        return None
    out: list[BriefComponent] = []
    for i, row in enumerate(comps):
        if not isinstance(row, dict):
            return None
        cid = str(row.get("id") or f"c{i+1}").strip()
        role = str(row.get("role") or "doer_logic").strip()
        goal = str(row.get("goal") or "").strip()
        acc = str(row.get("acceptance_one_liner") or "").strip()
        if not goal or not acc:
            return None
        hints = row.get("files_hint") or []
        if not isinstance(hints, list):
            hints = []
        out.append(
            BriefComponent(
                id=cid,
                role=role if role.startswith("doer") else "doer_logic",
                goal=goal[:800],
                acceptance_one_liner=acc[:400],
                files_hint=[str(h)[:200] for h in hints if str(h).strip()][:8],
            )
        )
    # FR-18.2 / AD-24: shared API + files contract are mandatory
    api_c = str(data.get("api_contract") or data.get("api") or "").strip()[:1200]
    files_c = str(data.get("files_contract") or "").strip()[:1200]
    if not api_c or not files_c:
        return None
    return ArchitectBrief(
        components=out,
        api_contract=api_c,
        files_contract=files_c,
        raw=data,
    )


def pick_strong_model(
    stack: list[str], *, unhealthy: set[str] | None = None
) -> str | None:
    dead = set(unhealthy or ())
    strong = [m for m in stack if m not in dead and power_score(m) >= TEST_AUTHOR_MIN]
    if not strong:
        return None
    return max(strong, key=power_score)


def pick_mid_doer(
    stack: list[str],
    *,
    used: set[str] | None = None,
    unhealthy: set[str] | None = None,
    prefer_role: str = "doer_logic",
) -> str | None:
    """Prefer mid-band 800–920 from user stack (FR-18.4 / Decision 1Б)."""
    dead = set(unhealthy or ())
    taken = set(used or ())
    ready = [m for m in stack if m not in dead and m not in taken]
    if not ready:
        # Prefer healthy (even if already used) over unhealthy stack members (AD-16)
        ready = [m for m in stack if m not in dead] or []
    mid = [m for m in ready if MID_BAND_LO <= power_score(m) <= MID_BAND_HI]
    pool = mid or ready
    if not pool:
        return None
    if prefer_role == "doer_ui":
        for pref in ("gemini-3.1-pro", "gemini-3-pro", "claude-haiku-4-5"):
            if pref in pool:
                return pref
    return max(pool, key=lambda m: (power_score(m), -ready.index(m) if m in ready else 0))


def _heuristic_v1() -> bool:
    return (os.environ.get("ZEUS_FUSION_V1_HEURISTIC") or "").strip().lower() in (
        "1",
        "true",
        "on",
        "yes",
    )


def _heuristic_brief(user_q: str) -> ArchitectBrief:
    q = (user_q or "feature")[:120]
    return ArchitectBrief(
        components=[
            BriefComponent(
                id="c1",
                role="doer_ui",
                goal=f"UI shell for: {q}",
                acceptance_one_liner="Visible layout with main CTA",
                files_hint=["index.html", "styles.css"],
            ),
            BriefComponent(
                id="c2",
                role="doer_logic",
                goal=f"Core logic for: {q}",
                acceptance_one_liner="Working handlers without crash",
                files_hint=["app.js"],
            ),
        ],
        api_contract="window.App = {init()}",
        files_contract="index.html, styles.css, app.js",
    )


def local_contract_check(
    *,
    answer: str,
    acceptance: str,
    checks: list[str] | None = None,
) -> tuple[bool, str]:
    """Cheap Layer-B stand-in when no real executor (Epic 5 owns allowlist runner)."""
    text = (answer or "").strip()
    if len(text) < 40:
        return False, "answer_too_short"
    acc = (acceptance or "").strip().lower()
    # Pass if non-empty solid answer; fail obvious stubs
    bad = ("todo", "not implemented", "pass", "lorem ipsum")
    low = text.lower()
    if any(b in low and len(text) < 120 for b in bad):
        return False, "stub_answer"
    if acc and acc.split()[0:1] and acc.split()[0] not in low and len(text) < 80:
        return False, "acceptance_not_addressed"
    _ = checks
    return True, "ok"


async def _call_json_role(
    *,
    model_id: str,
    system: str,
    user: str,
    role: str,
    upstream_call: UpstreamCall | None,
    cancel_event: Any,
    branches: list[BranchUsage],
) -> tuple[str, LiveBranch]:
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if not _heuristic_v1():
        msgs = adapt_prompt_for_family(msgs, model_family(model_id), role="leader")
    branch = await _run_one_model(
        model_id=model_id,
        messages=msgs,
        role=role,
        is_leader=role in ("architect", "test_author"),
        upstream_call=upstream_call,
        temperature=0.1,
        max_tokens=min(4096, _agent_max_tokens()),
        cancel_event=cancel_event,
    )
    branches.append(live_to_usage(branch, role=role))
    return (branch.text or "").strip(), branch


async def execute_pipeline_v1(
    *,
    stack: list[str],
    curator: str | None,
    messages: list[dict[str, Any]],
    user_q: str,
    product_mode: str = "power",
    unhealthy: set[str] | None = None,
    upstream_call: UpstreamCall | None = None,
    cancel_event: Any = None,
    complexity: str = "med",
    phase: str = "implement",
) -> ExecuteOutcome:
    """Full Pipeline v1. On Brief failure sets ``meta.degrade_to_fallback``."""
    t0 = time.perf_counter()
    branches: list[BranchUsage] = []
    live: list[LiveBranch] = []
    llm_calls = 0
    stack = [m for m in (stack or []) if (m or "").strip()]
    curator = (curator or "").strip() or (stack[0] if stack else "")
    cx = complexity if complexity in ("light", "med", "heavy") else "med"
    ph = phase if phase in (
        "chat", "ui", "docs", "test", "implement", "debug", "plan", "review"
    ) else "implement"

    def _degrade(reason: str) -> ExecuteOutcome:
        return ExecuteOutcome(
            path="FULL",
            policy_path="FULL",
            routed_by="pipeline_v1_degrade_fallback",
            answer="",
            leader=curator or None,
            branches=list(branches),
            live=list(live),
            complexity=cx,  # type: ignore[arg-type]
            phase=ph,
            meta={
                "pipeline": "v1",
                "degrade_to_fallback": True,
                "degrade_reason": reason,
                "llm_calls": llm_calls,
            },
        )

    architect = pick_strong_model(stack, unhealthy=unhealthy)
    if not architect:
        return _degrade("no_strong_architect")

    # --- Architect Brief ---
    if _heuristic_v1():
        brief = _heuristic_brief(user_q)
        llm_calls += 1
        branches.append(
            BranchUsage(
                model_id=architect,
                billable_state="completed",
                prompt_tokens=0,
                completion_tokens=8,
                role="architect",
                meta={"heuristic": True},
            )
        )
    else:
        raw_brief, b_live = await _call_json_role(
            model_id=architect,
            system=_ARCHITECT_SYSTEM,
            user=f"User goal:\n{(user_q or '')[:3000]}\n\nEmit Brief JSON (≤3 components).",
            role="architect",
            upstream_call=upstream_call,
            cancel_event=cancel_event,
            branches=branches,
        )
        live.append(b_live)
        llm_calls += 1
        err = str(b_live.error or "").lower()
        if "timeout" in err or "timed out" in err:
            return _degrade("architect_timeout")
        if not b_live.ok and not (raw_brief or "").strip():
            return _degrade("architect_empty")
        brief = validate_architect_brief(raw_brief)
        if brief is None:
            return _degrade("invalid_brief")

    if _cancelled(cancel_event):
        return _degrade("cancelled")

    # --- Test Author (Layer B) ---
    test_author = pick_strong_model(stack, unhealthy=unhealthy)
    tests_by_c: dict[str, list[str]] = {c.id: [] for c in brief.components}
    if test_author:
        if _heuristic_v1():
            llm_calls += 1
            for c in brief.components:
                tests_by_c[c.id] = [
                    f"accept: {c.acceptance_one_liner[:80]}",
                    "non_empty_output",
                ]
            branches.append(
                BranchUsage(
                    model_id=test_author,
                    billable_state="completed",
                    prompt_tokens=0,
                    completion_tokens=6,
                    role="test_author",
                    meta={"heuristic": True},
                )
            )
        else:
            raw_t, t_live = await _call_json_role(
                model_id=test_author,
                system=_TEST_AUTHOR_SYSTEM,
                user=(
                    f"Brief:\n{json.dumps(brief.as_dict(), ensure_ascii=False)[:3500]}\n\n"
                    "Emit short contract tests JSON."
                ),
                role="test_author",
                upstream_call=upstream_call,
                cancel_event=cancel_event,
                branches=branches,
            )
            live.append(t_live)
            llm_calls += 1
            parsed = _extract_json(raw_t) or {}
            for row in parsed.get("tests") or []:
                if not isinstance(row, dict):
                    continue
                cid = str(row.get("component_id") or "")
                ch = row.get("checks") or []
                if cid in tests_by_c and isinstance(ch, list):
                    tests_by_c[cid] = [str(x)[:200] for x in ch if str(x).strip()][:8]
        # FR-18.3: each component must have short checks — synthesize from acceptance
        for c in brief.components:
            if not tests_by_c.get(c.id):
                tests_by_c[c.id] = [c.acceptance_one_liner[:200], "non_empty_output"]

    # --- Isolated parallel mid doers ---
    used: set[str] = set()
    doer_assignments: list[tuple[BriefComponent, str]] = []
    for c in brief.components:
        mid = pick_mid_doer(
            stack,
            used=used,
            unhealthy=unhealthy,
            prefer_role=c.role,
        ) or curator or architect
        used.add(mid)
        doer_assignments.append((c, mid))

    # AD-24: doers see full Brief metadata + own chunk/tests — never peer outputs
    brief_plan = json.dumps(
        {
            "api_contract": brief.api_contract,
            "files_contract": brief.files_contract,
            "components": [
                {
                    "id": c.id,
                    "role": c.role,
                    "goal": c.goal,
                    "acceptance_one_liner": c.acceptance_one_liner,
                    "files_hint": c.files_hint,
                }
                for c in brief.components
            ],
        },
        ensure_ascii=False,
    )[:3500]

    async def _run_doer(comp: BriefComponent, model_id: str) -> dict[str, Any]:
        peer_ban = (
            "You must NOT invent peer component implementations. "
            "Peer outputs are invisible until merge. Only deliver your component."
        )
        prompt = (
            f"Brief (shared plan, no peer code):\n{brief_plan}\n\n"
            f"YOUR component id={comp.id} role={comp.role}\n"
            f"Goal: {comp.goal}\n"
            f"Acceptance: {comp.acceptance_one_liner}\n"
            f"files_hint: {comp.files_hint}\n"
            f"YOUR contract checks: {tests_by_c.get(comp.id) or []}\n\n"
            f"User goal: {(user_q or '')[:1500]}\n\n{peer_ban}\n"
            "Return the implementation artifact for YOUR files only. "
            "Prefix each file with `// file: path`."
        )
        if _heuristic_v1():
            text = (
                f"// file: {(comp.files_hint[0] if comp.files_hint else comp.id + '.txt')}\n"
                f"/* {comp.goal} */\n"
                f"export function {comp.id}() {{ return {json.dumps(comp.acceptance_one_liner)}; }}\n"
            )
            return {
                "component_id": comp.id,
                "model_id": model_id,
                "answer": text,
                "files_hint": list(comp.files_hint),
                "ok": True,
                "branch": BranchUsage(
                    model_id=model_id,
                    billable_state="completed",
                    prompt_tokens=0,
                    completion_tokens=20,
                    role=comp.role if comp.role.startswith("doer") else "doer_logic",
                    meta={"component_id": comp.id, "heuristic": True},
                ),
                "live": None,
            }
        msgs = [
            {"role": "system", "content": f"You are {comp.role} in Zeus Pipeline v1. {peer_ban}"},
            {"role": "user", "content": prompt},
        ]
        msgs = adapt_prompt_for_family(msgs, model_family(model_id), role="satellite")
        br = await _run_one_model(
            model_id=model_id,
            messages=msgs,
            role=comp.role if comp.role.startswith("doer") else "doer_logic",
            is_leader=False,
            upstream_call=upstream_call or _default_upstream,
            temperature=0.3,
            max_tokens=_agent_max_tokens(),
            cancel_event=cancel_event,
        )
        br.meta["component_id"] = comp.id
        return {
            "component_id": comp.id,
            "model_id": model_id,
            "answer": (br.text or "").strip(),
            "files_hint": list(comp.files_hint),
            "ok": bool((br.text or "").strip()),
            "branch": live_to_usage(br, role=br.role),
            "live": br,
        }

    # Independent start — gather (FR-13); one fail keeps siblings (FR-12)
    doer_results = await asyncio.gather(
        *[_run_doer(c, m) for c, m in doer_assignments],
        return_exceptions=True,
    )
    artifacts: list[dict[str, Any]] = []
    for r in doer_results:
        if isinstance(r, Exception):
            continue
        if not isinstance(r, dict):
            continue
        br = r.pop("branch", None)
        lv = r.pop("live", None)
        if br is not None:
            branches.append(br)
            llm_calls += 1
        if lv is not None:
            live.append(lv)
        artifacts.append(r)

    # --- One RED→FIX cycle (does NOT consume escalate budget) ---
    red_ids: list[str] = []
    for art in artifacts:
        comp = next((c for c in brief.components if c.id == art["component_id"]), None)
        if not comp:
            continue
        ok, reason = local_contract_check(
            answer=str(art.get("answer") or ""),
            acceptance=comp.acceptance_one_liner,
            checks=tests_by_c.get(comp.id),
        )
        art["test_ok"] = ok
        art["test_reason"] = reason
        if not ok:
            red_ids.append(comp.id)

    test_fix_ran = False
    if red_ids and test_author:
        test_fix_ran = True
        fix_targets = [a for a in artifacts if a.get("component_id") in red_ids]

        async def _fix_one(art: dict[str, Any]) -> dict[str, Any]:
            comp = next(c for c in brief.components if c.id == art["component_id"])
            if _heuristic_v1():
                art = dict(art)
                art["answer"] = (
                    str(art.get("answer") or "")
                    + f"\n// fixed for: {comp.acceptance_one_liner}\n"
                )
                art["test_ok"] = True
                art["test_reason"] = "fixed"
                art["_fix_branch"] = BranchUsage(
                    model_id=test_author,
                    billable_state="completed",
                    prompt_tokens=0,
                    completion_tokens=10,
                    role="test_author",
                    meta={"component_id": comp.id, "fix_cycle": 1, "heuristic": True},
                )
                return art
            msgs = [
                {
                    "role": "system",
                    "content": "Fix ONLY this RED component. One rewrite. Keep files_hint.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Acceptance: {comp.acceptance_one_liner}\n"
                        f"Checks: {tests_by_c.get(comp.id)}\n"
                        f"Previous:\n{(art.get('answer') or '')[:4000]}"
                    ),
                },
            ]
            br = await _run_one_model(
                model_id=str(art.get("model_id") or test_author),
                messages=msgs,
                role="doer_logic",
                is_leader=False,
                upstream_call=upstream_call or _default_upstream,
                temperature=0.2,
                max_tokens=_agent_max_tokens(),
                cancel_event=cancel_event,
            )
            art = dict(art)
            art["answer"] = (br.text or art.get("answer") or "").strip()
            ok2, reason2 = local_contract_check(
                answer=art["answer"],
                acceptance=comp.acceptance_one_liner,
                checks=tests_by_c.get(comp.id),
            )
            art["test_ok"] = ok2
            art["test_reason"] = reason2
            art["_fix_live"] = br
            art["_fix_branch"] = live_to_usage(br, role="doer_logic")
            return art

        fixed = await asyncio.gather(
            *[_fix_one(a) for a in fix_targets],
            return_exceptions=True,
        )
        by_id: dict[str, dict[str, Any]] = {}
        for item in fixed:
            if isinstance(item, Exception) or not isinstance(item, dict):
                continue
            fb = item.pop("_fix_branch", None)
            fl = item.pop("_fix_live", None)
            if fb is not None:
                branches.append(fb)
                llm_calls += 1
            if fl is not None:
                live.append(fl)
            by_id[str(item["component_id"])] = item
        artifacts = [by_id.get(str(a["component_id"]), a) for a in artifacts]

    # --- File-aware merge (AD-26) ---
    merge_result = await merge_artifacts_async(
        artifacts,
        brief=brief.as_dict(),
        strong_model=architect,
        curator_model=curator,
        upstream_call=None if _heuristic_v1() else (upstream_call or _default_upstream),
        cancel_event=cancel_event,
    )
    if merge_result.get("conflict_call"):
        llm_calls += 1
        if merge_result.get("conflict_branch"):
            branches.append(merge_result["conflict_branch"])

    answer = str(merge_result.get("answer") or "").strip()
    if not answer:
        # Assemble survivors
        answer = "\n\n".join(
            str(a.get("answer") or "") for a in artifacts if a.get("ok") or a.get("answer")
        ).strip()

    extras = bool(merge_result.get("conflict") or test_fix_ran)
    happy = llm_calls <= V1_HAPPY_PATH_MAX_CALLS or extras
    # FR-18.9: hard defect if default happy-path (no conflict/fix) exceeds 9
    call_budget_defect = (not extras) and llm_calls > V1_HAPPY_PATH_MAX_CALLS
    return ExecuteOutcome(
        path="FULL",
        policy_path="FULL",
        routed_by="pipeline_v1",
        answer=answer,
        leader=curator or architect,
        branches=branches,
        live=live,
        complexity=cx,  # type: ignore[arg-type]
        phase=ph,
        early_exit=None,
        meta={
            "pipeline": "v1",
            "brief": brief.as_dict(),
            "llm_calls": llm_calls,
            "test_fix_ran": test_fix_ran,
            "red_components": red_ids,
            "merge": {
                "strategy": merge_result.get("strategy"),
                "conflict": bool(merge_result.get("conflict")),
            },
            "call_budget_ok": happy,
            "call_budget_defect": call_budget_defect,
            "latency_s": round(time.perf_counter() - t0, 3),
            "degrade_to_fallback": False,
            "max_doer_llms": len(brief.components),
            "mid_parallel": True,
        },
    )
