---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-zeuscode-role-routing-verify-2026-07-24/prd.md
  - _bmad-output/planning-artifacts/prds/prd-zeuscode-role-routing-verify-2026-07-24/addendum.md
  - _bmad-output/planning-artifacts/architecture/architecture-ZeusCode-2026-07-25/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/architecture/architecture-ZeusCode-2026-07-25/ARCHITECTURE.md
  - docs/CLIENT_API_CONNECT_RESEARCH.md
excludedDocuments:
  - _bmad-output/planning-artifacts/epics.md
  - _bmad-output/planning-artifacts/prds/prd-zeuscode-fusion-2026-07-22/prd.md
  - _bmad-output/planning-artifacts/architecture/architecture-ZeusCode-2026-07-22/
project_name: ZeusCode (Role Routing + Pipeline v1)
status: ready-for-dev
created: 2026-07-25
updated: 2026-07-26
validation:
  mvp_frs_mapped: true
  deferred_frs: [FR16]
  epic_count: 5
  story_count: 22
  starter_template: none-brownfield
  notes: "Patched 2026-07-25 after IR gap: CE completed. Fusion epics.md untouched. IR G1–G5 ACs tightened same day."
  ir_patch: "2026-07-25 G1 call-budget S4.1; G2 context_chars S1.2; G3 unhealthy fallback S1.3; G4 mid-band S4.4; G5 scrub S1.1"
epic1_status: done
epic1_completed: 2026-07-25
epic1_stories_done: [1.1, 1.2, 1.3, 1.4, 1.5, 1.6]
epic2_status: done
epic2_completed: 2026-07-26
epic3_status: done
epic3_completed: 2026-07-26
epic4_status: done
epic4_completed: 2026-07-26
epic4_stories_done: [4.1, 4.2, 4.3, 4.4, 4.5, 4.6]
epic5_status: done
epic5_completed: 2026-07-26
epic5_stories_done: [5.1, 5.2, 5.3]
---

# ZeusCode (Role Routing + Pipeline v1) - Epic Breakdown

## Overview

Epic/story breakdown for Role Routing + Pipeline v1 over brownfield Fusion. UX spine: N/A (API + TG prefs only; no new Path buttons). Parent Fusion `epics.md` remains historical.

## Requirements Inventory

### Functional Requirements

FR1: Classify each request into `size`, `stack`, `task_kind`, `confidence`, `roles[]`; `confidence < 0.6` may label `size=large` but Pipeline v1 needs a second_signal; router fail → in-mode fallback not 500 (FR-1).
FR2: Two-step Role→Model table (`task_kind→role`, then `role×mode→model` from user stack) + score gates; curator = max `power_score`; custom never auto-adds models; Onestack exposes `role_table`, `models_by_role`, `pipeline` (FR-2).
FR3: On `pipeline=small`, Doer-LLM ≤ 2; `log_analyst` + `mini_verifier` outside cap; no Planner/Pipeline v1 on trivia (FR-3 / AD-31).
FR4: Product modes only TG `simple|power|custom`; public id `zeuscode`; no Path/cascade/race buttons; no `zeuscode-simple|power|custom` in client pickers; kill → FAST no Pipeline v1 (FR-4 / AD-19/30).
FR5: Log Analyst = DeepSeek JSON `{critical,summary,fix_hint,confidence}` only if log model in stack AND error trigger; custom without DeepSeek → skip (`log_report=N/A`); bad JSON → RED; branch `role=log_analyst` (FR-5 / AD-27).
FR6: Unified Gate — critical signals include traceback / log.critical / Mini fail / parse degrade; tests/build N/A when skipped; lint not critical; Doer self-score never forces GREEN (FR-6 / AD-5).
FR7: Escalate ≤2 global after one test-fix cycle (3А); Soft-Stop HTTP 200 + max power_score post-merge body + human RED line; `soft_stop=true`, `gate=RED` (FR-7 / AD-25).
FR8: Mini-Verifier on hot path; GREEN requires Mini passed when executor absent; Mini degrade → RED (FR-8).
FR9: Test Layer A = allowlist existing tests; Layer B Test Author only on Pipeline v1 with ≥950; skip Layer B otherwise (FR-9).
FR10: Test Executor = allowlisted script only; exit≠0 → `tests_failed` when run; hot without workspace → skipped (FR-10 / NFR-6).
FR11: Studio Gate — failing Studio pytest → RED → Escalate if budget remains (FR-11).
FR12: Architect/pipeline failure → degrade to `fallback_single` (curator full answer); one failed doer keeps ok siblings; all RED after escalate → Soft-Stop; simple never Pipeline v1 (FR-12 / AD-23).
FR13: Independent Brief components run parallel doers without waiting on peers; concurrency per AD-12 (FR-13 / AD-24).
FR14: Onestack fields: `task_kind`, `size`, `role_table`, `roles[]`, `models_by_role`, `gate`, `escalate_count`, `gate_reasons`, `soft_stop`, `pipeline`, `curator_model` (+ path final) (FR-14 / AD-28).
FR15: Honest billing — every LLM role = FusionResult branch; `cancelled_no_tokens` not billed; Onestack `path` = final serving Path (FR-15 / AD-14/8).
FR16: Multi-client live e2e matrix — **DEFERRED / non-goal for this MVP** (FR-16).
FR17: TG connect docs match research canon (Base/key/`zeuscode`/mode-in-TG + client exceptions); no mode-suffixed model ids (FR-17 / AD-30).
FR18: Pipeline v1 canon — trigger large∧second_signal∧power|custom∧≥950; Brief≤3; Test Author; isolated mid doers; one RED→FIX; file-aware merge; Log per FR-5; else `fallback_single`; call-budget soft ceilings; Onestack `pipeline`+`curator_model` (FR-18 / AD-20..26).

### NonFunctional Requirements

NFR1: Router classification ≤ 2.5s (NFR-1).
NFR2: Log Analyst ≤ ~400 tokens out; brief-sized input (NFR-2).
NFR3: small path p95 latency ≤ FAST baseline +30% (NFR-3).
NFR4: Secret/PII scrub once at Edge→Policy (NFR-4 / AD-17).
NFR5: Kill-switch → FAST and never Pipeline v1 (NFR-5 / AD-9).
NFR6: Test Executor allowlist only (NFR-6).
NFR7: All LLM calls recorded on FusionResult branches (NFR-7 / AD-28).
NFR8: Pipeline v1 hard-gated on large+second_signal (NFR-8 / AD-22).
NFR9: No new UI Path/mode controls beyond TG three modes (NFR-9).

### Additional Requirements

- Brownfield: extend `backend/app/fusion/`; routers wire-only (AD-6/10/29).
- Target modules: `roles.py`, `pipeline.py` (sole final `pipeline` writer), `merge.py`, `log_analyst.py`.
- `TEST_AUTHOR_MIN` default 950 in `model_power.py` (no UX).
- Curator ≡ Leader / sticky (AD-32).
- `second_signal` closed set (AD-22).
- Eval fixtures SM-1/2/3/6/9; FR-16 out.
- FR-17 TG guides vs `docs/CLIENT_API_CONNECT_RESEARCH.md`.

### UX Design Requirements

UX-DR: N/A — constraints in FR4/NFR9/AD-30 only.

### FR Coverage Map

FR1: Epic 1 — classify size/task_kind/second_signal  
FR2: Epic 1 — Role→Model table + curator  
FR3: Epic 1 — small doer cap  
FR4: Epic 1 — TG modes / zeuscode surface  
FR5: Epic 2 — Log Analyst  
FR6: Epic 2 — unified Gate  
FR7: Epic 2 — Escalate ≤2 + Soft-Stop  
FR8: Epic 1 (Mini shell) + Epic 2 (Gate coupling)  
FR9: Epic 4 (Layer B) + Epic 5 (Layer A)  
FR10: Epic 5 — Test Executor allowlist  
FR11: Epic 5 — Studio Gate  
FR12: Epic 3 (fallback) + Epic 4 (v1 degrade)  
FR13: Epic 4 — parallel doers  
FR14: Epic 1 — Onestack Role Routing fields  
FR15: Epic 1 — honest billing branches  
FR16: Deferred — not in MVP epics  
FR17: Epic 1 — connect docs regression  
FR18: Epic 3 (fallback_single) + Epic 4 (Pipeline v1)  
NFR1: Epic 1 — S1.2  
NFR2: Epic 2 — S2.1  
NFR3: Epic 5 — S5.3  
NFR4: Epic 1 — S1.1 scrub regression AC  
NFR5: Epic 2 — S2.4 + Epic 5 kill fixture  
NFR6: Epic 5 — S5.1  
NFR7: Epic 1 — S1.1/S1.5  
NFR8: Epic 4 — S4.1  
NFR9: Epic 1 — S1.6  

## Epic List

### Epic 1: Cheap Smart Coding ✅ DONE (2026-07-25)
Артём чинит мелочь через один `zeuscode`: система классифицирует small, ставит роли из его TG-стека, не жжёт Pipeline v1, отдаёт честный Onestack/биллинг и гайды без фейковых mode-id.
**FRs covered:** FR1, FR2, FR3, FR4, FR8 (Mini present), FR14, FR15, FR17 (+ NFR1, NFR4, NFR7, NFR9; ARCH contracts)
**Implemented:** `roles.py`, `pipeline.py`, `merge.py`/`log_analyst.py` stubs, `TEST_AUTHOR_MIN`, classify size/second_signal, curator≡Leader, small clamps, Onestack FR-14 fields, Gate GREEN/RED shell on small, branch role→`doer_*`, TG guides OK. Tests: `test_fusion_role_routing_epic1.py`.

**Audit 2026-07-26 #3:** Fixed holes — (1) `pipeline=small|fallback_single` + `zeus.path`/`clf_meta.path=FULL` no longer serves FULL (demote→CASCADE after override); (2) kill wins over `zeus.path` (AD-9); (3) empty custom no longer silent-fills power stack (400 + RR uses caller `models[]`); (4) clf_meta path synced after RR clamps.
- Residuals closed by later epics: v1 executor (E4), fallback_single contract (E3), TV Gate (E2).
- RR broad `except` fail-open (salvage in E3); NFR-1 ≤2.5s not CI-gated.

### Epic 2: Trusted Verify Loop ✅ DONE (2026-07-26)
При traceback/RED пользователь получает Log Analyst → Gate → Escalate≤2 → Soft-Stop с явным «проверка не пройдена», без бесконечного цикла и без подстановки DeepSeek в custom.
**FRs covered:** FR5, FR6, FR7, FR8 (+ NFR2, NFR5)
**Implemented:** `log_analyst.py` DeepSeek JSON + skip=`N/A`; `verify.compute_unified_gate` + `run_trusted_verify_loop` (escalate≤2 / Soft-Stop power_score + RED line); wired in `_monolith` after Path + FAST; kill never `pipeline=v1`. Tests: `test_fusion_role_routing_epic2.py`.

**Audit 2026-07-26 #1+#2 (vs AD-25/27/5/9):** Fixed B1–B6; pass #2 closed panel Mini stack leak, log re-arm/degrade, exception escalate_count, near-dup power pick. AC adversarial probe ALL PASS. Tests: `test_fusion_role_routing_epic2.py`.
- Residuals: kill `max_escalate=0` (AD-9 cheap); Aspect/τ not in TV loop; Layer A/Studio = Epic 5.

### Epic 3: Curator When No Strong Model ✅ DONE (2026-07-26)
На large+2nd без модели ≥950 куратор (max score стека) сразу пишет полный ответ (`fallback_single`) — без mid-параллели и без автодобавления моделей.
**FRs covered:** FR12 (fallback path), FR18.8 (+ AD-23/32)
**Implemented:** `panel.execute_fallback_single` (one curator LLM, no Brief); monolith intercept before CASCADE/FULL; panel≤1; Onestack `pipeline=fallback_single` + `curator_model≡leader`; TV loop (Mini→Log→Escalate) still applies. Tests: `test_fusion_role_routing_epic3.py`.
**Audit 2026-07-26:** Fixed — (B1) `has_strong` ignores unhealthy ≥950; (B2) empty curator → Soft-Stop via TV not 502; (B3) RR fail-open salvage re-picks pipeline (incl. `fallback_single`); classify_local authoritative for size/2nd (no stale clf_meta suppress). Composition E1→E3→E2 probe ALL PASS.

### Epic 4: Pipeline v1 Large Quality ✅ DONE (2026-07-26)
На large+second_signal+power/custom с ≥950 Марина получает Brief≤3 → контрактные тесты → изолированные doers → один RED→FIX → file-aware merge → Gate.
**FRs covered:** FR9 (Layer B), FR12 (v1 degrade), FR13, FR18 (+ NFR8; AD-20..26)
**Implemented:** `pipeline_v1.execute_pipeline_v1` (Architect Brief≤3 → Test Author → mid-band parallel doers → one RED→FIX → `merge.merge_artifacts_async`); invalid Brief / no strong → degrade `fallback_single`; monolith intercept on `pipeline=v1` before brownfield FULL; call-budget soft ceiling ≤9 happy path. Tests: `test_fusion_role_routing_epic4.py`.
**Audit 2026-07-26 (vs FR-18 / AD-20..26/29):** Fixed — (B1) `unhealthy` forwarded into v1 picks; (B2) Brief requires non-empty `api_contract`+`files_contract`; (B3) doers get full Brief plan metadata (not peer outputs); (B4) architect timeout/empty → degrade reasons; (B5) `pipeline.write_pipeline` sole-writer helper for v1/degrade; (B6) re-export `execute_pipeline_v1` from `pipeline.py` (AD-29).
**Composition E1→E4 probe 2026-07-26:** 32/32 PASS (trigger matrix, clamps, curator≡leader, E4→E3 degrade+billing, E4→E2 TV escalate≤2 / kill max_escalate=0, unhealthy→fallback). Fixed composition gap: v1→fallback also syncs `clf_meta.path/policy_path=CASCADE` (and v1-ok → FULL). Residuals → Epic 5: Layer A / Studio / eval; brownfield kill/small still direct-stamp some `clf_meta.pipeline`; `stamp_role_routing_onestack` unused on hot path.

**Full-system audit 2026-07-26 (PRD+AD E1–E5):** Contract probe **45/45 PASS**. Security: no critical/high. Fixed billing blockers — (B1) TV branches/tokens no longer double-counted on Epic3 path; (B2) FAST path now merges TV branches+usage into FusionResult; conflict-merge role=`architect`; `call_budget_defect` meta surfaced. Remaining residuals: NFR-1/3 latency not CI-gated; SM JSON expect not harness-driven; `stamp_role_routing_onestack` unused on hot path; FR-16 deferred.

### Epic 5: Studio Tests & Ship Gates ✅ DONE (2026-07-26)
Studio/workspace гоняет allowlist executor; eval-фикстуры ловят cost/trigger/log regressions; kill не пускает Pipeline v1.
**FRs covered:** FR9 (Layer A), FR10, FR11 (+ NFR3, NFR5, NFR6; SM-1/2/3/6/9)
**Implemented:** `fusion/test_executor.py` allowlist pytest runner (reject shell/meta/escape; hot without workspace/`studio_test` → skip N/A); monolith Layer A before TV; `verify.run_trusted_verify_loop(tests_failed=)` sticky RED → Escalate≤2 → Soft-Stop (FR-11); eval fixtures `tests/eval/fixtures/SM{1,2,3,6,9}.json` + `test_fusion_role_routing_epic5.py`. FR-16 remains deferred.
**Audit 2026-07-26:** Fixed — (B1) `asyncio.to_thread` around executor (no event-loop block); (B2) bare `python -m pytest` forces default allowlisted target; (B3) reject Studio non-allowlisted → `tests_failed=True` via `executor_signal_for_gate` (was wiped when skipped); (M1) flag allowlist + reject `--rootdir`/absolute binary paths; (M2) `returncode=None` → fail; path prefix sibling escape closed. Residuals: live Studio e2e (ops); SM JSON `expect` not yet loaded by harness (pytest asserts intent); NFR-3 optional; FR-16 deferred.

### Deferred (not MVP epics)
FR16 — multi-client live e2e (SM-7).

---

## Epic 1: Cheap Smart Coding

Артём кодит в IDE на `zeuscode`; мелочь остаётся дешёвой; роли и Onestack честные; режимы только в TG.

### Story 1.1: Role Routing contracts skeleton

As a Zeus engineer,
I want `TEST_AUTHOR_MIN`, extended FusionResult/Onestack fields, and target module stubs,
So that later stories share one contract surface (AD-28/29).

**Acceptance Criteria:**

**Given** brownfield `fusion/types.py` and `model_power.py`  
**When** this story lands  
**Then** `TEST_AUTHOR_MIN` defaults to 950; `FusionResult`/Onestack can carry `pipeline`, `curator_model`, `role_table`, `roles`, `models_by_role`, `gate`, `gate_reasons`, `escalate_count`, `soft_stop`, `task_kind`, `size`  
**And** stubs exist for `roles.py`, `pipeline.py`, `merge.py`, `log_analyst.py` without changing public behavior yet  
**And** `fusion/*` still does not import `routers.*` (FR14, FR15, NFR7; AD-28/29)  
**And** existing Edge→Policy scrub still runs once on a fixture message containing an API-key-like secret (masked before upstream) — no double-scrub regression (NFR4; AD-17)

### Story 1.2: Classify size, task_kind, second_signal

As a developer sending light vs heavy prompts,
I want the router to emit `size`, `task_kind`, `confidence`, and `second_signal`,
So that expensive Pipeline v1 cannot start on trivia or low-conf alone.

**Acceptance Criteria:**

**Given** chitchat / «поменяй цвет» without errors  
**When** classify runs  
**Then** `size=small`, `second_signal=false`, and router completes ≤2.5s (NFR1)  
**And** `confidence < 0.6` may set `size=large` but `second_signal` stays false unless lexicon/multi-file/landing/explicit-heavy hits (FR1; AD-22)  
**And** a working request with `context_chars > 4000` is treated as large-eligible heuristic input (may contribute to `size=large`) without alone forcing `pipeline=v1` (FR1)  
**And** classify failure falls back inside mode (no 500)

### Story 1.3: Role→Model table + curator≡Leader

As a user with TG mode simple/power/custom,
I want roles mapped only from my chosen stack with curator = max `power_score`,
So that custom never gets models I did not pick and Leader/sticky match curator.

**Acceptance Criteria:**

**Given** mode=power or a custom ≤3 stack  
**When** roles resolve  
**Then** two-step table applies; power `doer_logic` primary may be opus (1Б); UI power prefers gemini-strong; simple prefers haiku  
**And** `curator_model = argmax power_score(stack)` equals `FusionResult.leader` / sticky Leader (FR2; AD-21/32)  
**And** custom never auto-adds models  
**And** if the primary model for a role is unhealthy/unavailable, assignment uses the table fallback within the same user-chosen stack (never invents an out-of-stack model) (FR2)

### Story 1.4: pipeline=small orchestration + doer cap

As a cost-sensitive coder,
I want small requests to run ≤2 Doer LLMs plus Mini,
So that light work stays cheap (SM-9).

**Acceptance Criteria:**

**Given** `pipeline` intent is small (not large+second_signal+eligible)  
**When** `pipeline.py` executes (sole final writer)  
**Then** Onestack `pipeline=small`, Doer-LLM calls ≤2, no Architect/Test Author/mid-decompose (FR3; AD-20/31)  
**And** Mini-Verifier runs; GREEN on hot path requires Mini passed when executor skipped (FR8)

### Story 1.5: Onestack + honest role billing

As a developer reading Zeus telemetry,
I want Role Routing fields and every LLM role as a billed branch,
So that money and routing are auditable.

**Acceptance Criteria:**

**Given** a small completion with doer + mini  
**When** Bill consumes FusionResult  
**Then** Onestack includes FR14 fields; `path` is final Path; each LLM role has `branches[].role`  
**And** `cancelled_no_tokens` is ₽0 (FR14, FR15; AD-8/14/28)

### Story 1.6: zeuscode surface + FR-17 connect docs

As Денис setting up a client from TG,
I want guides that teach Base/key/`zeuscode`/mode-in-TG only,
So that pickers never show fake Zeus mode model ids and no new Path buttons appear.

**Acceptance Criteria:**

**Given** TG platform guides / generators (`tg-platforms.js` etc.)  
**When** docs are rendered for ZC_PLATFORM_ORDER clients  
**Then** canon matches `CLIENT_API_CONNECT_RESEARCH.md` (incl. Claude/Aider/OpenCode/Cursor caveats)  
**And** no `zeuscode-simple|power|custom` and no Path/cascade/race/усилить controls (FR4, FR17; NFR9; AD-19/30)

---

## Epic 2: Trusted Verify Loop

Ошибки и RED видны; усиление ограничено; Soft-Stop честный.

### Story 2.1: Log Analyst DeepSeek JSON (5Б)

As a developer pasting a traceback,
I want DeepSeek Log Analyst JSON only when my stack has a log model,
So that Gate sees `critical` without injecting models into custom.

**Acceptance Criteria:**

**Given** traceback/Exception/error-tail and stack contains DeepSeek/log-capable id  
**When** Log Analyst runs  
**Then** output validates `{critical,summary,fix_hint,confidence}`; bad/missing `critical` → RED; branch `role=log_analyst`; input is brief-sized (NFR2)  
**And** custom without DeepSeek → skip with `log_report=N/A` (not RED) (FR5; AD-27)

### Story 2.2: Unified Gate signals

As a user who fears silent wrong GREEN,
I want Gate to ignore Doer self-score and aggregate applicable criticals,
So that GREEN means checks actually passed.

**Acceptance Criteria:**

**Given** Mini fail or `log_report.critical` or parse degrade  
**When** Gate aggregates  
**Then** result is RED; `tests_failed`/`build_failed` are N/A when not run; lint alone is not critical  
**And** Doer self-score cannot force GREEN (FR6, FR8; AD-5)

### Story 2.3: Escalate ≤2 then Soft-Stop (3А)

As a user on a stubborn RED,
I want at most two escalations then a non-empty Soft-Stop answer,
So that the request never loops forever.

**Acceptance Criteria:**

**Given** Gate RED after verify (and after any single test-fix cycle if present)  
**When** escalate/`judge_fix` runs  
**Then** `escalate_count ≤ 2` global; `fix_hint` used if Log ran  
**And** Soft-Stop returns HTTP 200, non-empty max-`power_score` post-merge body, human RED line, `soft_stop=true`, `gate=RED` (FR7; AD-25)

### Story 2.4: Kill-switch blocks Pipeline v1

As ops enabling kill,
I want serving clamped to FAST with no Pipeline v1,
So that incidents stay cheap and predictable.

**Acceptance Criteria:**

**Given** kill-switch on  
**When** any request arrives (incl. large+second_signal)  
**Then** Path is FAST-class and `pipeline` is never `v1` (NFR5; AD-9/22)

---

## Epic 3: Curator When No Strong Model

Large задача без ≥950 не ломается и не докидывает модели.

### Story 3.1: fallback_single curator full answer

As a custom-stack user without a ≥950 model,
I want my strongest chosen model to answer fully in one shot,
So that large+2nd still works without Pipeline v1 or mid-parallel.

**Acceptance Criteria:**

**Given** large ∧ second_signal ∧ mode∈{power,custom} ∧ no stack model ≥ `TEST_AUTHOR_MIN`  
**When** pipeline selects mode  
**Then** `pipeline=fallback_single`; curator writes full answer with **no** Architect Brief step; mid-parallel forbidden; no models auto-added  
**And** Mini → Log?(FR5) → Escalate≤2 → Soft-Stop path still apply (FR12, FR18.8; AD-23)

### Story 3.2: Onestack curator_model on fallback

As a developer debugging cost,
I want Onestack to show `pipeline=fallback_single` and `curator_model`,
So that fallback is visible in telemetry.

**Acceptance Criteria:**

**Given** Story 3.1 path  
**When** response returns  
**Then** Onestack has `pipeline=fallback_single` and `curator_model` equal to Leader (FR14, FR18.10; AD-32)

---

## Epic 4: Pipeline v1 Large Quality

Редкий large+2nd с сильной моделью идёт test-first без 8–12 default вызовов.

### Story 4.1: Hard Pipeline v1 trigger

As a product owner guarding margin,
I want `pipeline=v1` only on large∧second_signal∧power|custom∧≥950,
So that SM-6/NFR8 hold (0 v1 without second_signal).

**Acceptance Criteria:**

**Given** large without second_signal, or mode=simple, or kill  
**When** pipeline is chosen  
**Then** `pipeline` ≠ `v1`  
**And** eligible case sets intent `v1` with `pipeline.py` as sole final writer (FR18.1; NFR8; AD-20/22)  
**And** call-budget soft ceiling is respected as orientir: Pipeline v1 ~6–8 LLM calls typical, hard defect if a default happy-path v1 exceeds 9 without conflict/log extras; small/fallback stay ~2–4 (FR18.9)

### Story 4.2: Architect Brief ≤3 validated

As Марина on a landing task,
I want an Architect Brief with ≤3 components and API/file contract,
So that doers share one plan without peer code.

**Acceptance Criteria:**

**Given** eligible Pipeline v1  
**When** Architect (≥950) returns Brief  
**Then** `components[]` length ≤3 with `{id,role,goal,acceptance_one_liner,files_hint?}` and shared API/files contract  
**And** invalid/empty/timeout → degrade to `fallback_single` (FR18.2, FR12; AD-24)

### Story 4.3: Test Author contract tests per chunk

As a quality-sensitive user,
I want short contract tests per Brief component from Test Author ≥950,
So that Layer B exists only when strong models are present.

**Acceptance Criteria:**

**Given** valid Brief on Pipeline v1  
**When** Test Author runs  
**Then** each component gets short contract tests (not a giant suite); role billed  
**And** without ≥950 Layer B is skipped (FR9 Layer B, FR18.3)

### Story 4.4: Isolated parallel mid doers

As a user waiting on a multi-part feature,
I want doers to run in parallel on their own chunk only,
So that work overlaps without leaking peer implementations.

**Acceptance Criteria:**

**Given** Brief + per-chunk tests  
**When** doers execute  
**Then** each sees Brief + own component + own tests only; peer code invisible until merge  
**And** independent chunks start without waiting; one failed doer does not discard successful siblings (FR13, FR12, FR18.4; AD-24)  
**And** parallel Pipeline v1 doers prefer mid-band models (`power_score` roughly 800–920) from the user stack when available; Architect/Test Author/conflict-merge remain ≥ `TEST_AUTHOR_MIN` (FR18.4; Decision 1Б power-preset primary may still be opus outside parallel chunks)

### Story 4.5: One RED→FIX cycle then escalate budget

As a user on almost-right chunks,
I want exactly one Test Author fix cycle before Escalate≤2,
So that test-fix does not consume escalate budget (3А).

**Acceptance Criteria:**

**Given** test-check RED on some components  
**When** fix+recheck runs once  
**Then** only RED components are rewritten; no second test-manager loop  
**And** subsequent Gate RED uses Escalate≤2 only (FR18.5, FR7; AD-25)

### Story 4.6: File-aware merge + conflict strong

As a user receiving a single answer,
I want file-aware merge by Brief paths with one strong conflict call,
So that prose-concat is not the canon.

**Acceptance Criteria:**

**Given** doer artifacts after test-fix  
**When** merge runs  
**Then** assembly is file/path/patch aware; no conflict → no extra top merge  
**And** file conflict / broken API seam → one strong call (≥950 else curator) (FR18.6; AD-26)

---

## Epic 5: Studio Tests & Ship Gates

Скриптовые тесты и eval не пускают регрессии в прод.

### Story 5.1: Allowlist Test Executor (Layer A)

As a Studio/workspace user,
I want only allowlisted scripts to run as Test Executor,
So that arbitrary shell cannot execute (NFR6).

**Acceptance Criteria:**

**Given** Studio/workspace with allowlisted pytest target  
**When** executor runs  
**Then** exit≠0 sets `tests_failed` critical when applicable  
**And** non-allowlisted commands are rejected; hot path without workspace skips executor (FR9 Layer A, FR10)

### Story 5.2: Studio Gate on pytest fail

As a Studio publisher,
I want failing pytest to RED and escalate if budget remains,
So that broken publishes do not look GREEN.

**Acceptance Criteria:**

**Given** Studio pytest failure  
**When** Gate runs  
**Then** `gate=RED` and Escalate is attempted while `escalate_count < 2`, else Soft-Stop (FR11, FR7)

### Story 5.3: Eval fixtures SM-1/2/3/6/9

As ops before canary,
I want fixtures proving small stays cheap, log affects Gate, no infinite escalate, v1 needs second_signal, and Soft-Stop non-empty,
So that we can ship without FR-16 client marathon.

**Acceptance Criteria:**

**Given** eval suite in repo/CI  
**When** fixtures for SM-1, SM-2, SM-3, SM-6, SM-9 run  
**Then** assertions match PRD metrics intent (incl. 0× `pipeline=v1` without second_signal)  
**And** FR-16 remains explicitly out of this suite (Epic 5; NFR3 presence check optional/benchmark)

---

## Validation Notes (Step 4)

- All MVP FRs mapped except **FR16 deferred**.
- No starter template (brownfield) — Epic 1 Story 1 = contracts skeleton ✓
- Stories sequenced without forward deps within epic.
- Architecture modules/AD-19…32 cited in ACs.
- Ready for `bmad-create-story` / sprint planning.
