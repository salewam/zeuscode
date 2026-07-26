---
reviewer: tech-versions / reality-check
target: ARCHITECTURE-SPINE.md
scope: Stack table + Structural Seed + named brownfield modules
evidence:
  - requirements.txt
  - backend/app/fusion/*
  - local interpreters + .venv installed floors
created: 2026-07-25
verdict: pass-with-findings
---

# Tech / Version Reality Check — ZeusCode Role Routing Spine

**Verdict:** **PASS WITH FINDINGS** — every committed Stack package floor matches `requirements.txt` (brownfield ratification, not greenfield invent). Python 3.10+ is locally/CI-grounded. Structural Seed and layer “Lives in” paths overstate presence of Role Routing modules that do not exist yet; one named constant (`TEST_AUTHOR_MIN`) is not in code.

## Method

1. Diffed spine **Stack** rows against repo-root `requirements.txt`.
2. Observed local Python: `3.10.11` (default), `3.12.5` available; CI workflow uses `3.12`.
3. Observed `.venv` installed versions (floors satisfied).
4. Listed `backend/app/fusion/` and checked every path cited in Design Paradigm / Structural Seed / Capability map.
5. Confirmed Edge/deps modules: `routers/chat.py`, `catalog.py`, `cost.py`, `upstream.py`, `frontend/tg-*.js`.

No new starter frameworks, ORMs, queues, or cloud runtimes appear in Stack. This is brownfield ratification of the existing FastAPI/SQLite/aiogram surface.

---

## Stack ↔ requirements.txt

| Spine Stack | requirements.txt | Installed (.venv) | Verdict |
| --- | --- | --- | --- |
| Python 3.10+ `[ADOPTED: local 3.10.11 / 3.12 available]` | *(not pinned; no `requires-python`)* | Local 3.10.11 + 3.12.5; CI `python-version: "3.12"` | **Ratified** (improved vs parent’s old 3.11+ guess) |
| FastAPI ≥0.115.0 | `fastapi>=0.115.0` | 0.139.0 | **Match** |
| Uvicorn ≥0.32.0 | `uvicorn[standard]>=0.32.0` | 0.51.0 | **Match** (extras omitted — Low) |
| httpx ≥0.27.0 | `httpx>=0.27.0` | 0.28.1 | **Match** |
| SQLAlchemy (async) ≥2.0.36 | `sqlalchemy[asyncio]>=2.0.36` | 2.0.51 | **Match** |
| aiosqlite ≥0.20.0 | `aiosqlite>=0.20.0` | 0.22.1 | **Match** |
| pydantic-settings ≥2.0.0 | `pydantic-settings>=2.0.0` | 2.14.2 | **Match** |
| aiogram ≥3.13.0 | `aiogram>=3.13.0` | 3.29.1 | **Match** |

**Invented floors:** none.  
**Stale major-version fabrications:** none for listed libs.  
**Training-data drift on package floors:** none detected.

### Correctly omitted (not Role Routing stack)

Present in `requirements.txt`, absent from spine Stack — appropriate at this altitude:

- `python-dotenv`, `pydantic[email]`, `passlib[bcrypt]`, `bcrypt`, `python-jose[cryptography]`, `playwright`

---

## Module presence (brownfield vs seed)

### Present (ratified)

| Claimed path | Status |
| --- | --- |
| `backend/app/routers/chat.py` | Exists |
| `backend/app/fusion/__init__.py` | Exists (facade; still re-exports `_monolith`) |
| `fusion/policy.py` | Exists |
| `fusion/panel.py` | Exists |
| `fusion/verify.py` | Exists |
| `fusion/brief.py` | Exists |
| `fusion/model_power.py` | Exists |
| `fusion/judge.py` | Exists |
| `fusion/session.py` | Exists |
| `fusion/metrics.py` | Exists |
| `fusion/types.py` | Exists |
| `catalog.py` / `cost.py` / `upstream.py` | Exist |
| `frontend/tg-platforms.js` / `tg-miniapp.js` | Exist |
| Public id `zeuscode` + legacy aliases | Present in `catalog.py` / `chat.py` |

### Claimed in Structural Seed / layer table — **not present** (planned Role Routing)

| Claimed path | Status | Risk |
| --- | --- | --- |
| `fusion/roles.py` | **Missing** | Layer table says Roles “Lives in” here |
| `fusion/pipeline.py` | **Missing** | Execute / FR-18 owner |
| `fusion/merge.py` | **Missing** | Merge layer / AD-26 |
| `fusion/log_analyst.py` | **Missing** | Verify layer / AD-27 |

These are legitimate **target** modules for Role Routing, but the spine presents them in the same “Lives in / Structural Seed” voice as existing brownfield files. Without an explicit `TO-BUILD` / migration note, CE can treat them as already split.

### Present brownfield omitted from Structural Seed

| Path | Note |
| --- | --- |
| `fusion/_monolith.py` | **Active** implementation host; `__init__.py` states callers keep facade while `_monolith` holds logic “until Path modules take over” |
| `fusion/ui_crew.py` | Existing |
| `fusion/web_tools.py` | Existing |
| `fusion/browser_client.py` | Existing |
| `fusion/publish_gate.py` | Existing |

Omitting `_monolith.py` is the material gap: brownfield reality is facade + monolith + partial extract, not a clean `roles/pipeline/merge/log_analyst` package yet.

### Named constant not in code

| Spine claim | Code |
| --- | --- |
| `TEST_AUTHOR_MIN` (default **950**) in `model_power.py` | **Not found** in `backend/app/fusion/` (no symbol match). `power_score` / tables exist; threshold constant does not. |

Not a fake package — but an **unverified product constant** presented as if already owned by that module.

---

## Findings

### High

#### H1 — Structural Seed / “Lives in” mixes existing modules with invented paths
**Evidence:** Seed and paradigm table cite `roles.py`, `pipeline.py`, `merge.py`, `log_analyst.py` as ownership homes. None exist under `backend/app/fusion/` today. Facade still routes through `_monolith.py`.  
**Risk:** Implementers assume greenfield module layout already landed; skip migration from monolith; invent parallel entrypoints.  
**Disposition:** Label seed rows `exists` vs `to-build`; add `_monolith.py` as current host; keep target modules, but do not imply presence.

### Medium

#### M1 — `TEST_AUTHOR_MIN` default 950 not reality-checked in code
**Evidence:** Consistency Conventions + AD-21/22/26 bind `TEST_AUTHOR_MIN` in `model_power.py`. Grep across `fusion/` finds no constant.  
**Risk:** Stories invent different thresholds or bury magic numbers outside the named owner.  
**Disposition:** Mark `[TO-ADD]` / story-owned, or land the constant before spine final; do not claim as brownfield fact.

#### M2 — Python note softer than parent deploy pin
**Evidence:** This spine: `3.10+ [ADOPTED: local 3.10.11 / 3.12 available]`. Parent: `pin deploy ≥3.10`. No Dockerfile/`requires-python` in repo. CI uses 3.12. Local default is 3.10.11.  
**Risk:** Low — not invented — but “3.12 available” is environment observation, not a deploy contract.  
**Disposition:** Prefer parent wording: ADOPTED floor ≥3.10; note CI 3.12 as observed, not a second pin.

### Low

#### L1 — `uvicorn[standard]` extras omitted
requirements pin includes `[standard]`; spine lists bare Uvicorn ≥0.32.0. Non-blocking; same as parent review.

#### L2 — Stack floors are lower bounds only
Installed (.venv) is well above floors (e.g. FastAPI 0.139, aiogram 3.29). Spine correctly uses `requirements.txt` floors, not frozen installs — good brownfield practice. No action required.

#### L3 — Non-Stack product names (DeepSeek Log Analyst, opus doer_logic)
AD-27/AD-30 name models for role assignment. Out of version-floor scope; not invented packages. Do not treat as Stack pins.

---

## What is solid

- **Zero package-floor mismatches** vs `requirements.txt`.
- **No greenfield starter invent** (no new framework, Redis-as-required, Postgres swap, etc.). Redis correctly Deferred.
- **Python 3.10+** fixes the parent review’s training-data `3.11+` ASSUMPTION; local 3.10.11 + 3.12 availability confirmed.
- Core brownfield surfaces cited for Edge/Policy/Panel/Verify/Brief/metrics/session/types/upstream/catalog/cost/TG prefs **exist**.
- Public model id `zeuscode` is already in catalog/chat — AD-19 is code-backed, not aspirational naming.

---

## Scorecard

| Check | Result |
| --- | --- |
| Every Stack row matches requirements / observed runtime | **Pass** |
| No invented / outdated package majors | **Pass** |
| Brownfield modules cited as present actually exist | **Partial** — 4 Role Routing modules absent; `_monolith` under-documented |
| Named code constants claimed as current | **Fail (`TEST_AUTHOR_MIN`)** |
| Ratifies existing stack (no greenfield replace) | **Pass** |

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 1 |
| Medium | 2 |
| Low | 3 |

---

## Disposition summary

| ID | Action |
| --- | --- |
| H1 | Autofix seed: mark `roles`/`pipeline`/`merge`/`log_analyst` as to-build; list `_monolith.py` |
| M1 | Mark `TEST_AUTHOR_MIN` to-add or land constant in `model_power.py` |
| M2 | Tighten Python ADOPTED note to deploy ≥3.10; CI 3.12 observational |
| L1 | Optional: `uvicorn[standard]≥0.32.0` |

**Finalize gate for versions:** Stack table can stay as-is for package floors. Do not finalize Structural Seed language that implies Role Routing modules already exist without H1/M1 clarification.
