---
name: Rubric Walker — Architecture Spine Finalize Gate
artifact: ARCHITECTURE-SPINE.md
date: 2026-07-25
verdict: Fair
checklist: good-spine
---

# Rubric Review — ZeusCode Role Routing Spine

**Artifact:** `architecture-ZeusCode-2026-07-25/ARCHITECTURE-SPINE.md`  
**Altitude:** feature  
**Driving PRD coverage expected:** FR-1..15, FR-17, FR-18; Pipeline v1; `fallback_single`; Log Analyst; TG modes only; public id `zeuscode`; inherit Fusion AD-1..18  
**Verdict:** **Fair**

Spine is strong as a build substrate: real divergence points are named, inheritance of AD-1..18 is explicit (with AD-2 supersession surfaced), and Role Routing ADs (AD-19..30) generally have enforceable Rules. Finalize is blocked from Pass by a small set of enforceability / completeness gaps—especially opaque “second signal” in AD-22, incomplete hard lock for FR-3 small doer cap, and thin brownfield ratification outside Python.

---

## Checklist Scorecard

| Criterion | Score | Notes |
| --- | --- | --- |
| Fixes real divergence points for level below | **Pass** | Public id, pipeline vs Path UX, curator ownership, v1 trigger, fallback_single, Brief≤3, verify budget, file-merge, Log Analyst inject rules, FusionResult fields, module ownership, TG/connect surface |
| Every AD Rule enforceable and prevents stated divergence | **Fair** | Most Rules are testable; AD-22 “second signal” is not defined in-spine; FR-3 doer-cap only implied in sequence (“1-2 Doers”), not an AD Rule |
| Deferred items won't let two units diverge unsafely | **Pass** | Deferred set is mostly story/ops/non-goal; Brief shape locked in AD-24; budgets presence via AD-12; Redis/streaming correctly out of MVP |
| Named tech verified/ratified brownfield | **Fair** | Python stamped `[ADOPTED: local…]`; FastAPI/Uvicorn/httpx/SQLAlchemy/aiosqlite/aiogram given floors only—no brownfield verify note |
| Covers driving PRD capabilities | **Pass** | Capability map binds FR-1..15, FR-17, FR-18 + Pipeline v1 / fallback / Log / TG / `zeuscode`; FR-16 deferred intentionally |
| Inherited ADs not weakened silently | **Pass** | AD-2→AD-19 conflict surfaced; AD-9/11/15 tightened explicitly for Role Routing; AD-14 extended additively via AD-28; AD-18 retained |
| Every altitude dimension decided/deferred/open (esp ops/deploy) | **Fair** | Ops/deploy via inherited AD-18 + one map row; no OPEN register; numeric budgets deferred without explicit “OPEN vs Deferred” altitude table |

**Aggregate:** Fair (no Fail dimensions; three Fair dimensions that should be closed before finalize stamp).

---

## Dimension-by-Dimension

### 1. Divergence points for the level below

**Pass.** The spine targets implementer fork points that matter at feature altitude:

| Divergence | Locked by |
| --- | --- |
| Client id / mode-suffixed Zeus ids | AD-19, AD-30 |
| Path buttons vs product cost modes | AD-20, AD-30 |
| Who owns “who answers” / custom inject | AD-21 |
| When expensive multi-role runs | AD-22 |
| No ≥950 large path stall | AD-23 |
| Doer peer leakage / Brief sprawl | AD-24 |
| Escalate vs test-fix accounting / Soft-Stop shape | AD-25 |
| Concat merge vs file-aware | AD-26 |
| Log Analyst as process manager / DeepSeek inject | AD-27 |
| Dual bill / missing telemetry | AD-28 |
| god-`panel.py` dual pipelines | AD-29 |

Paradigm table + structural seed + sequence diagram give units a shared placement lattice. This is appropriate feature-altitude work—not restating the whole Fusion Path spine.

### 2. AD Rule enforceability

**Fair.** Pattern is good: each AD states **Binds / Prevents / Rule**. Most Rules are mechanically checkable (enum membership, score thresholds, HTTP 200 Soft-Stop, module import direction, Onestack field presence).

**Gaps:**

1. **AD-22 — “second signal” unnamed**  
   Rule: `pipeline=v1` iff `size=large` ∧ **second signal** ∧ mode ∈ {power,custom} ∧ ∃ model ≥ `TEST_AUTHOR_MIN`.  
   Without naming what “second signal” is (PRD/addendum term? classifier flag? task_kind set?), two stories can implement different predicates and both claim compliance. **Must be named or referenced to a frozen PRD term in the Rule.**

2. **FR-3 small doer cap**  
   Capability map points at AD-20/AD-22, but neither Rule hard-caps doer count for `pipeline=small`. Sequence says “1-2 Doers” only. That is a real divergence point left soft.

3. **AD-27 “log-capable model”**  
   Preset DeepSeek is named; custom “only if user selected it” is clear. Acceptable if catalog marks capability; otherwise units may disagree which models count. Mild—story-level if catalog already encodes it.

4. **AD-21 / AD-24 role closed set**  
   Conventions list roles with `…` ellipsis. Closed-set claim is weakened unless glossary pointer is treated as normative. Mild if PRD glossary is binding via `binds`/`sources`.

Otherwise AD-19..30 Rules prevent their stated divergences.

### 3. Deferred safety

**Pass.** Deferred list does not park decisions that would let two MVP units invent incompatible product behavior:

| Deferred | Why safe |
| --- | --- |
| FR-16 live e2e matrix | Validation program, not serving contract |
| Numeric timeout/concurrency | Presence required by inherited AD-12; values = ops config |
| Redis sticky / multi-node | Parent Deferred; single-node AD-18 holds |
| True upstream token streaming | Separate epic; Soft-Stop still 200 |
| Brief/test JSON field polish | Shape locked AD-24 (≤3 components + required keys) |
| Traceback detector detail | Under AD-27 trigger contract |
| Mid-band 800–920 heuristics | Eval calibration, not serving fork |
| RACE / Elo / Combo Studio / Path buttons | Explicit Non-Goals |

No Deferred item silently replaces a needed AD Rule for v1 serving safety.

### 4. Named tech / brownfield ratification

**Fair.**

- Stack versions are plausible for this repo and inherit “existing uvicorn + SQLite” (AD-18).
- Only Python carries an explicit `[ADOPTED: local 3.10.11 / 3.12 available]` stamp.
- FastAPI, Uvicorn, httpx, SQLAlchemy, aiosqlite, pydantic-settings, aiogram: version floors only—no “verified in tree / requirements pin” ratification.

For a brownfield feature spine this is close enough to ship after a one-line Stack ratification note (or `[ADOPTED: brownfield pin]` on packages already in `requirements`/`pyproject`). Not a structural Fail.

### 5. Driving PRD capability coverage

**Pass** against the gate’s stated FR set.

| Expected | Coverage |
| --- | --- |
| FR-1..15 | Capability map rows; FR-9..11 via pipeline + Studio executor note |
| FR-17 | AD-19, AD-30 + connect exceptions |
| FR-18 / Pipeline v1 | AD-20..AD-26, sequence alt |
| `fallback_single` | AD-23 |
| Log Analyst | AD-27 |
| TG modes only | AD-19, AD-30 |
| Public id `zeuscode` | AD-19 |
| Inherit Fusion AD-1..18 | Inherited Invariants table + AD-2 conflict |

**Nits (not coverage fails):**

- FR-9..11 row mentions “Studio executor” while Deferred/Non-Goals ban Combo Studio / Path buttons. Clarify that “Studio” here means existing test-layer / contract-test path—not Combo Studio product surface—or units may reintroduce banned UX.
- FR-16 correctly deferred (out of stated driving set).

### 6. Inherited ADs not weakened silently

**Pass.** Inheritance handling is exemplary for a finalize gate:

- Parent binding stated; local supersession only when explicit.
- **AD-2** public id conflict **surfaced** and superseded by AD-19 (`zeuscode`)—not quiet rewrite.
- **AD-9** kill path explicitly forbids Pipeline v1 (NFR-5)—tightening, not weakening.
- **AD-11** extended to pipeline eligibility under Product Mode clamp.
- **AD-14** preserved; AD-28 additive fields only.
- **AD-15** RACE non-target for Role Routing large v1 made local and binding.
- **AD-4 / AD-5 / AD-6 / AD-7 / AD-8 / AD-10 / AD-12 / AD-16 / AD-17 / AD-18** restated as still binding with Role Routing placement—no silent drops.

### 7. Altitude dimensions (esp ops/deploy)

**Fair.**

Decided via ADOPTED ADs + conventions: paradigm, public id, pipeline/Path enums, roles/scores, verify/merge/log, module ownership, prefs/connect, auth scheme (existing API key), observe (`trace_id` / Onestack).

Ops/deploy: **inherited AD-18 only** (“existing uvicorn + SQLite; no new cloud” + capability row “existing VPS”). Adequate for feature altitude if parent AD-18 remains normative, but the spine lacks an explicit altitude register:

- Decided / Deferred / Open columns for ops, deploy, scaling, streaming, schema polish.

Nothing critical is left **Open** in prose, yet there is no OPEN section—reviewers cannot confirm intentional emptiness. Numeric budgets are Deferred without stating residual risk acceptance for NFR latency/concurrency. Recommend a one-row Ops envelope: **Decided = AD-18 parent; Deferred = numeric budgets & Redis; Open = none.**

---

## Findings (actionable)

### F1 — AD-22 “second signal” not enforceable from spine alone — **Must fix before Pass**

**Where:** AD-22 Rule  
**Issue:** Predicate term undefined in-spine.  
**Fix:** Name the second signal (e.g. frozen PRD/addendum identifier: `second_signal` / task_kind ∈ {…} / classifier flag) inside the Rule or cite the exact PRD clause as normative.

### F2 — FR-3 small doer cap not hard-locked — **Should fix**

**Where:** Capability map FR-3 vs AD-20/22; sequence “1-2 Doers”  
**Issue:** Units can diverge on small-path parallelism.  
**Fix:** Add explicit clause to AD-20 or AD-22 (or new AD): `pipeline=small` ⇒ doer fan-out ≤ N (PRD N).

### F3 — Stack ratification incomplete — **Should fix**

**Where:** Stack table  
**Issue:** Only Python is `[ADOPTED]` with local verify; other named packages are version floors.  
**Fix:** Mark brownfield packages `[ADOPTED: pin in requirements]` or equivalent after pin check.

### F4 — FR-9..11 “Studio executor” vs Combo Studio Non-Goal — **Should clarify**

**Where:** Capability → Architecture Map FR-9..11; Deferred Non-Goals  
**Issue:** Wording invites reintroduction of banned Combo Studio surface.  
**Fix:** Rename to existing contract-test / layer A/B executor; state Combo Studio remains Non-Goal.

### F5 — Ops/deploy altitude register missing — **Nice / light Should**

**Where:** Deferred + AD-18; no OPEN section  
**Issue:** Finalize checklist asks every altitude dimension decided/deferred/open.  
**Fix:** Add short register: ops/deploy Decided (AD-18); budgets/Redis Deferred; Open: none. Keep `status` from `draft` → ready when gate closes.

---

## What is already strong (do not regress)

- Explicit AD-2 supersession narrative for `zeuscode`.
- Hard v1 trigger shape (size ∧ mode ∧ score floor)—once second signal is named.
- `fallback_single` = curator full answer (no mid-parallel) — clear anti-stall.
- Verify budget order separating test-fix cycle from escalate ≤2 + Soft-Stop wire shape.
- Log Analyst inject/skip contract (no DeepSeek into custom unless selected).
- Module ownership mermaid preventing god-panel dual pipelines.
- FusionResult/Onestack additive field list for telemetry parity.
- TG-only product modes + connect-doc exceptions packed into AD-30.

---

## Gate recommendation

| Outcome | Condition |
| --- | --- |
| **Pass** | Resolve F1 (required); resolve or explicitly accept F2–F4 in spine text; add ops register (F5); flip `status` out of `draft` |
| **Fair (current)** | Usable for story drafting with PRD open beside spine; not finalize-clean |
| **Fail** | Not warranted—inheritance, capability coverage, and most Rules are already gate-quality |

**Rubric walker verdict: Fair**

---

## Compact summary

- **Verdict:** Fair  
- **Top findings:** (1) AD-22 “second signal” undefined; (2) FR-3 small doer cap not AD-locked; (3) stack ADOPTED only for Python; (4) “Studio executor” vs Combo Studio Non-Goal wording; (5) ops/deploy altitude register absent  
- **File:** `_bmad-output/planning-artifacts/architecture/architecture-ZeusCode-2026-07-25/reviews/review-rubric.md`
