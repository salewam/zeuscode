---
reviewer: rubric-walker + version-reality
target: ARCHITECTURE-SPINE.md
companion_skim: ARCHITECTURE.md
lint_spine: ok (0 findings)
grade_hint: adequate
created: 2026-07-22
---

# Rubric Walker — Zeus Fusion Spine

**Grade hint:** adequate  
**Verdict:** Core Path/brain invariants are real divergence fixes with enforceable Rules; stack floors match `requirements.txt`. Spine under-binds ops envelope and several MVP seams that the companion doc already narrates — CE can still diverge there.

## Checklist scorecard

| Check | Result | Notes |
| --- | --- | --- |
| Fixes real divergence points for level below | **Pass (mostly)** | AD-1…5, 8, 10–11 hit Path/verify/billing/deps forks CE would invent incompatibly |
| Every AD Rule enforceable & prevents stated divergence | **Partial** | Soft-Stop (FR-14) hung under billing AD-8; scrub omitted from AD-3 order; AD-9 flag persistence unspecified |
| Deferred doesn’t hide must-decide at this altitude | **Pass (mostly)** | Redis/tools/Elo/DUAL correctly deferred; flag store + Soft-Stop owner should not stay implicit |
| Ratifies brownfield rather than contradicting | **Pass** | chat→fusion facade→upstream; package split as migration; legacy aliases; `upstream/catalog/cost/publish` exist |
| Covers PRD MVP capabilities (fusion Path brain) | **Partial** | Path/verify/Judge/sticky/billing/flags/eval mapped; scrub/adapt/custom-panel/feedback thin or missing |
| Operational envelope decided/deferred/open | **Fail (spine)** | Companion §10 decides same-VPS/SQLite/Settings; spine silent on deploy/env/CI/provider |
| No whole silent dimension | **Fail (ops)** | Domain Path layer thick; ops/env dimension absent from spine Deferred/Open |
| Named tech verified vs requirements | **Pass (+1 guess)** | Package floors match; Python 3.11+ is unpinned ASSUMPTION |

## Finding counts

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 3 |
| Medium | 5 |
| Low | 3 |
| **Total** | **11** |

Version-reality subcounts: **0 mismatch** against `requirements.txt` floors; **1 training-data / unverified guess** (Python 3.11+).

---

## High

### H1 — Operational envelope silent on spine
**Checklist:** operational envelope; no silent dimension  
**Evidence:** Spine has AD-12 (mechanism presence) + Deferred numerics/Redis/streaming, but no decide/defer/open for deploy topology, environments, CI/eval harness ownership, or provider strategy. Companion `ARCHITECTURE.md` §10 already states same VPS/uvicorn, SQLite sticky OK, budgets in Settings, eval in repo CI/nightly — those calls never landed as spine AD / Deferred / Open.  
**Risk:** Two epics invent different multi-node sticky, canary ops, or eval gating.  
**Disposition:** discuss — promote companion §10 bullets into spine Deferred/Open (or thin ADOPTED “same process as ZeusCode API”).

### H2 — Scrub + Soft-Stop ownership under-bound
**Checklist:** AD enforceability; divergence for level below  
**Evidence:** PRD FR-2 order is `scrub → classify → …`; AD-3 starts at classify (scrub absent). FR-21 never appears in Capability map. FR-14 is bound only via AD-8 billing states; Soft-Stop / cancel / race both-fail pick authority (panel vs chat vs policy) is not a Rule. Companion §3/§7 narrates both.  
**Risk:** Edge vs policy scrub drift; incompatible Soft-Stop behavior across Path implementers.  
**Disposition:** autofix candidates — extend AD-3 with scrub-before-classify; add AD or fold Soft-Stop decision into panel Rule with Binds FR-14.

### H3 — MVP capability gaps vs PRD / companion
**Checklist:** covers PRD MVP; companion skim  
**Evidence:** Spine Capability map strong on FR-1/3–5/7–13/16/18–19/25–29/31/37. Missing or only loosely held vs companion FR checklist:
- **FR-21** scrub — companion §9; spine silent  
- **FR-32** prompt adaptation — companion Phase 2 / publish regression; spine silent  
- **FR-34** custom-panel rules — companion Path notes; spine silent (AD-11 mentions custom only via mode clamp)  
- **FR-24** feedback log-only — PRD MVP; neither spine map nor companion module table  
- **FR-15 / FR-17** — AD-12 binds presence; no capability row / owner module beyond “policy+panel+Settings”  
**Disposition:** discuss — add Capability rows + governing AD (or explicit Deferred with revisit) for FR-21/24/32/34; tighten FR-15/17 owners.

---

## Medium

### M1 — Python 3.11+ is an unverified ASSUMPTION
**Checklist:** named tech verified-current  
**Evidence:** Stack lists `Python 3.11+ [ASSUMPTION: deploy runtime]`. Not in `requirements.txt`. No Dockerfile/`requires-python` pin found in repo scan. Local interpreter observed `Python 3.10.11`. Likely training-data / tooling default, not brownfield ratification.  
**Disposition:** discuss — pin to verified runtime (or Deferred “runtime = deploy image”) before binding CE.

### M2 — Prefs schema vs brownfield naming
**Checklist:** ratify brownfield  
**Evidence:** AD-11 / Capability cite `users.fusion_*`. Code today: `users.fusion_pref`, `users.fusion_models` (`models.py`). Effort / Kill-Switch columns undecided (new fields vs JSON blob).  
**Risk:** parallel migrations for prefs storage.  
**Disposition:** autofix — name brownfield columns; Deferred or AD for Effort/Kill column shape.

### M3 — Flag / baseline persistence not decided or deferred
**Checklist:** Deferred must-decide; AD-9 enforceability  
**Evidence:** AD-9 requires global+cohort flags and immutable `baseline_id`. Companion §5.2 offers “new or config”. Spine Deferred never names flag store. Two units can pick Settings-only vs DB table incompatibly.  
**Disposition:** defer explicitly (“Settings until canary; DB cohort later”) or AD one store.

### M4 — Soft-Stop / FR-14 miscategorized in Capability map
**Checklist:** AD prevents stated divergence  
**Evidence:** Map row `FR-14/19 billing → AD-8` collapses cancel billing with Soft-Stop selection policy. AD-8 Prevents/Rule are billing/Onestack honesty, not Soft-Stop algorithm ownership.  
**Disposition:** autofix — split map; bind Soft-Stop to panel (+ AD Rule).

### M5 — AD status tags inconsistent
**Checklist:** mechanical clarity (lint passed)  
**Evidence:** AD-1…5, 8, 10–12 marked `[ADOPTED]`; AD-6, AD-7, AD-9, AD-13 unmarked though brownfield-ratifying or PRD-settled.  
**Disposition:** autofix — tag ADOPTED or leave unmarked with intent; avoid mixed signal.

---

## Low

### L1 — `uvicorn[standard]` extras omitted
requirements.txt has `uvicorn[standard]>=0.32.0`; spine lists `Uvicorn ≥0.32.0`. Non-blocking.

### L2 — Non-fusion deps correctly omitted
`passlib`, `bcrypt`, `python-jose`, `playwright`, `python-dotenv`, `pydantic[email]` present in requirements, absent from spine Stack — appropriate for fusion altitude.

### L3 — Sticky “or equivalent durable row” softens AD-7
Allows non-SQLAlchemy stores in MVP; weakens single-choice enforceability. Prefer one MVP store (SQLAlchemy/SQLite table) without “or equivalent”.

---

## Version reality check (`requirements.txt`)

| Spine Stack | requirements.txt | Verdict |
| --- | --- | --- |
| FastAPI ≥0.115.0 | `fastapi>=0.115.0` | Match |
| Uvicorn ≥0.32.0 | `uvicorn[standard]>=0.32.0` | Match (extras omitted) |
| httpx ≥0.27.0 | `httpx>=0.27.0` | Match |
| SQLAlchemy (async) ≥2.0.36 | `sqlalchemy[asyncio]>=2.0.36` | Match |
| aiosqlite ≥0.20.0 | `aiosqlite>=0.20.0` | Match |
| pydantic-settings ≥2.0.0 | `pydantic-settings>=2.0.0` | Match |
| aiogram ≥3.13.0 | `aiogram>=3.13.0` | Match |
| Python 3.11+ | *(not pinned)* | **Guess / unverified ASSUMPTION** |

No invented package floors above requirements. No stale major-version fabrications detected for listed libs.

---

## What works (credit)

- Named paradigm + layer diagram fixes studio/TG second-stack divergence (AD-1).  
- Path enum, control-flow order, Brief ownership, early-exit authority, billing honesty, dep direction, prefs precedence, eval gate — genuine CE divergence points with Prevents/Rule.  
- Structural seed matches intended split of existing monolith `fusion.py`; brownfield modules cited exist.  
- Deferred list correctly parks Redis, true streaming, Elo, DUAL/Tradeoff, TOOL-FULL, numeric budgets.  
- Companion covers Path execution, billing, security, ops that CE humans need — gap is spine contract completeness, not total planning vacuum.

## Companion skim — capability coverage vs spine

| Companion topic | In spine? |
| --- | --- |
| Path runtime sketch FAST/CASCADE/RACE/FULL | Yes (AD + seed) |
| Sticky schema / TTL | Partial (AD-7 fields; TTL only in companion) |
| Flags / baseline_id | Partial (AD-9; store open) |
| Billing / Onestack fields | Yes (AD-8) |
| Observability / rollout stages | Partial (AD-9/13; alerts/stages companion-only) |
| Security scrub / retention | Companion only → **gap** |
| Deploy / ops envelope | Companion only → **gap** |
| FR-32 / FR-34 / FR-24 | Companion thin / PRD only → **gap** |

## Top 3 gaps

1. **Ops/deploy/env envelope** decided in companion, silent on spine (decide/defer/open).  
2. **Scrub (FR-21) + Soft-Stop (FR-14) + FR-32/34/24** under-mapped; AD-3/AD-8 don’t fully prevent stated forks.  
3. **Python 3.11+** unverified vs repo/`requirements.txt` (training-data risk); prefs column shape vs `fusion_pref` brownfield.

## Disposition summary

| ID | Action |
| --- | --- |
| H1 | discuss → spine Deferred/Open or thin AD |
| H2 | autofix / discuss AD-3 + Soft-Stop Rule |
| H3 | discuss Capability rows |
| M1 | discuss runtime pin |
| M2 | autofix brownfield names |
| M3 | defer flag store explicitly |
| M4 | autofix Capability map |
| M5 | autofix ADOPTED tags |
| L1–L3 | ignore or minor polish |
