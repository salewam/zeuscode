---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-zeuscode-fusion-2026-07-22/prd.md
  - _bmad-output/planning-artifacts/prds/prd-zeuscode-fusion-2026-07-22/addendum.md
  - _bmad-output/planning-artifacts/architecture/architecture-ZeusCode-2026-07-22/ARCHITECTURE.md
  - _bmad-output/planning-artifacts/architecture/architecture-ZeusCode-2026-07-22/ARCHITECTURE-SPINE.md
project_name: ZeusCode (Zeus Fusion)
status: ready-for-dev
created: 2026-07-22
updated: 2026-07-22
validation:
  mvp_frs_mapped: true
  deferred_frs: [FR6, FR11, FR27]
  epic_count: 4
  story_count: 23
  starter_template: none-brownfield
  notes: "IR gaps patched 2026-07-22: S2.5 fixtures; S2.3 failover; split S3.4/3.5; split S4.5→4.5..4.9."
ir_patch: "2026-07-22 closes NFR3/NFR7/oversized stories"
---

# ZeusCode (Zeus Fusion) - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Zeus Fusion, decomposing the requirements from the PRD and Architecture into implementable stories. UX design contract: N/A (OpenAI-compatible API + existing prefs surfaces; no new UX spine).

## Requirements Inventory

### Functional Requirements

FR1: Stable public model id `zeus/fusion`; breaking rename without versioned alias forbidden; legacy `zeus/fusion-fast` / `zeus/fusion-full` continue (FR-1, FR-37).
FR2: Request precedence: per-request `zeus.*` > account prefs > default; pipeline scrub→classify→Effort+1→Path→MoR→mode clamp; sticky = Leader/stack only (FR-2).
FR3: Product Modes `simple|power|custom` with Path clamps (`simple` ∈ {FAST,CASCADE} unless forced/legacy full) (FR-3).
FR4: Classify assigns `classify_phase`, `complexity_band`, `confidence`; fallback Path=CASCADE on classify fail (FR-4).
FR5: Effort `low|med|high`; high → complexity +1 only (no floor) (FR-5).
FR6: Tradeoff/Presets — **out of MVP / v1.x** (FR-6).
FR7: Path FAST — single Leader, thinking visible, failover (FR-7).
FR8: Path CASCADE — cheap→Mini-Verifier→deterministic escalate map (FR-8).
FR9: Path RACE — parallel cheap+strong; both-fail terminal map (FR-9).
FR10: Path FULL — Panel ≤3, Brief, diversity, Aspects before τ, rank-then-fuse top-K (FR-10).
FR11: DUAL Architect→Editor — **out of MVP / v1.x** (FR-11).
FR12: Early-exit only Mini-Verifier / Aspect / near-duplicate; no Leader self-score; Aspects before τ (FR-12).
FR13: Structured Judge with consensus/contradictions/unique/blind spots; anti-bias token-overlap oracle (FR-13).
FR14: Soft-Stop and cancel on disconnect/zero balance; Soft-Stop pick order; billable states (FR-14).
FR15: Leader health + ordered failover; empty answer forbidden if ready fallback exists (FR-15).
FR16: Sticky session by `session_id`; Path uses classify Phase not sticky meta (FR-16).
FR17: Control-plane degrade table (classify/Mini/Aspect/MoR) ≠ user 500 (FR-17).
FR18: Shadow→Canary→rollback; `baseline_id` hash semantics (FR-18).
FR19: Honest branch billing with billable states enum; drift tolerance (FR-19).
FR20: Onestack transparency: final `path`, `policy_path`, `escalate_from?`, `routed_by`, usage breakdown (FR-20).
FR21: Secret/PII scrub MVP minimum before upstream (FR-21).
FR22: Anti-bloat — satellites Brief only; no full Cursor dump to Panel (FR-22).
FR23: Prefs surfaces: Product Mode, Effort, Kill-Switch, custom models — TG + кабинет (FR-23).
FR24: Feedback 👍/👎/regen log-only in MVP (Elo writeback v1.x) (FR-24).
FR25: Eval Suite gate with pass oracle + fixtures F1–F17/I1–I3/R1–R2 before canary 100% (FR-25).
FR26: HTML publish continuity + regression gate on prompt/Judge/Brief/sanitize/adapt (FR-26).
FR27: Agent/tools TOOL-FULL — **out of MVP / v2** (FR-27).
FR28: Path selection policy control flow + interactive formula + MoR local scores + design_lexicon→FULL + closed `routed_by` + fixtures (FR-28).
FR29: Runtime mechanism presence: timeout, concurrency, retry, disaster, keepalive, rate, overflow/long-context (FR-29).
FR31: Aspect-Verifiers v1 correctness+completeness; required on FULL and CASCADE→FULL (FR-31).
FR32: Prompt adaptation v1 per model family; publish regression applies (FR-32).
FR34: Custom-panel rules for 1/2/3 selected models (FR-34).
FR37: Legacy compatibility matrix; `legacy_*` ≠ `forced_*`; unknown `zeus.mode` ignored; `zeus.thinking` passthrough/ignore (FR-37).

### NonFunctional Requirements

NFR1: Reliability — control-plane degrade ≠ HTTP 500; disaster = structured non-empty error.
NFR2: Performance — global timeout; Panel/RACE concurrency caps; stream thinking + keepalive.
NFR3: Observability — `trace_id`; path rates by Phase; escalate%; verifier always-OK; dead models; `routed_by` histogram.
NFR4: Security — scrub MVP minimum; log TTL / opt-out for raw prompts.
NFR5: API stability — `zeus/fusion` stable; Onestack additive only in MVP.
NFR6: Rollout — Shadow → Canary 10/50/100 → rollback on Eval/SM-C1/C3/billing drift.
NFR7: Ops — load test + incident runbook before wide Path rollout (canary exit §6.4).
NFR8: Billing integrity — token ledger exact; ₽ drift ≤ 1 minor unit.
NFR9: Deploy envelope — existing ZeusCode uvicorn single-node; sticky on SQLite; Redis deferred (AD-18).

### Additional Requirements

- Brownfield: extend `chat.py → fusion → upstream`; no greenfield rewrite (AD-1, Arch §2).
- Split monolith into `backend/app/fusion/{policy,panel,verify,judge,session,metrics}` with facade (AD-6).
- `fusion/*` must not import `routers.*`; publish only post-answer (AD-10).
- Canonical internal Path enum only; `fast|full` only at Edge/Shadow adapter (AD-15).
- Execute→Bill handoff via frozen `FusionResult` fields (AD-14).
- Single Leader mutator; sticky write at request end with actual Leader (AD-16).
- Scrub once at Edge→Policy boundary (AD-17).
- Sticky store table: session_id, user_id, leader, stack_json, phase_meta, expires_at (Arch §5.1).
- Flags: shadow / canary_pct / kill; `baseline_id` includes lexicon_v1 (AD-9, AD-13).
- MoR scores local heuristics in policy.py; no LLM MoR in MVP (AD-3 / Arch).
- Soft-Stop selection in Execute before Bill (AD-8).
- After Policy serving Path, Execute may only append escalate `routed_by` codes (AD-9).
- No starter/greenfield template — brownfield migration stories first.
- Eval/CI: fixture suite + `eval_baseline.json` (frontier + judge ids) before canary 100%.
- FR-24 feedback storage shape deferred to CE story detail; must not affect Path.
- Numeric timeout/concurrency budgets — ops-owned; presence required (AD-12).

### UX Design Requirements

_N/A — no bmad-ux DESIGN.md/EXPERIENCE.md for this API feature. Prefs reuse existing TG Mini App + кабинет surfaces (FR-23); no new visual system in MVP._

### FR Coverage Map

FR1: Epic 1 — stable id + aliases  
FR2: Epic 1 (pipeline shell) + Epic 2 (full policy) + Epic 4 (sticky rule)  
FR3: Epic 2 — mode clamps  
FR4: Epic 2 — classify  
FR5: Epic 2 — Effort  
FR6: Deferred v1.x — not in MVP epics  
FR7: Epic 2 — FAST  
FR8: Epic 2 — CASCADE  
FR9: Epic 3 — RACE  
FR10: Epic 3 — FULL Panel  
FR11: Deferred v1.x — not in MVP epics  
FR12: Epic 2 (Mini) + Epic 3 (Aspect/τ)  
FR13: Epic 3 — Judge  
FR14: Epic 3 — Soft-Stop/cancel  
FR15: Epic 2 — ordered Leader failover (S2.3)  
FR16: Epic 4 — sticky session  
FR17: Epic 2 — degrade table  
FR18: Epic 4 — Shadow/Canary  
FR19: Epic 1 — billable states  
FR20: Epic 1 — Onestack FusionResult  
FR21: Epic 1 — scrub  
FR22: Epic 1 — anti-bloat / Brief contract  
FR23: Epic 4 — prefs surfaces  
FR24: Epic 4 — feedback ingest + log (S4.6)  
FR25: Epic 4 — Eval suite N≥50 + fixtures (S4.4)  
FR26: Epic 4 — publish regression (S4.7)  
FR27: Deferred v2 — not in MVP epics  
FR28: Epic 2 — Path policy + MoR + lexicon; fixtures owned across S2.2/S2.5/S3.1/S4.1/S4.4  
FR29: Epic 4 — runtime budgets presence (S4.5)  
FR31: Epic 3 — Aspect-Verifiers  
FR32: Epic 3 — prompt adaptation (S3.5)  
FR34: Epic 2 — custom panel rules  
FR37: Epic 1 — legacy matrix / routed_by split  
NFR3: Epic 4 — S4.8 observability  
NFR7: Epic 4 — S4.9 canary exit ops  

## Epic List

### Epic 1: Honest Fusion Gateway
Разработчик вызывает `zeus/fusion` и получает рабочий ответ с честным Onestack/биллингом, scrub и legacy aliases — без сюрпризов по деньгам. Закладывает `fusion/` package + `FusionResult`.
**FRs covered:** FR1, FR19, FR20, FR21, FR22, FR37 (+ Arch AD-6/10/14/15/17; NFR4/5/8/9)

### Epic 2: Smart Cheap Path
На лёгких задачах система сама идёт FAST/CASCADE, проверяет Mini-Verifier, уважает Effort/Kill-Switch/simple clamp — пользователь не выбирает модель вручную. Fixture harness ловит Path-регрессии.
**FRs covered:** FR2, FR3, FR4, FR5, FR7, FR8, FR12 (Mini), FR15, FR17, FR28, FR34 (+ NFR1 partial)

### Epic 3: Strong Multi-Model Path
На тяжёлых/borderline задачах пользователь получает RACE/FULL с Brief, Aspects, Judge, Soft-Stop — сильнее single model без ×3 контекста.
**FRs covered:** FR9, FR10, FR12 (Aspect/τ), FR13, FR14, FR31, FR32 (+ NFR2 partial)

### Epic 4: Sticky Prefs & Safe Ship
Диалог липкий по Leader; prefs в TG/кабинете; ops катит Shadow→Canary через Eval, observability, runtime budgets, feedback ingest, publish guard и canary-exit ops.
**FRs covered:** FR16, FR18, FR23, FR24, FR25, FR26, FR29 (+ NFR3/6/7)

### Deferred (not MVP epics)
FR6, FR11, FR27 — v1.x / v2 per PRD.

---

## Epic 1: Honest Fusion Gateway

Разработчик получает стабильный `zeus/fusion` с прозрачным чеком и безопасным scrub; команда получает миграционный каркас `fusion/` без ломки aliases.

### Story 1.1: Fusion package facade without behavior break

As a Zeus engineer,
I want `backend/app/fusion/` with a facade re-exporting `iter_fusion` / `run_fusion`,
So that we can migrate Path logic without breaking Cursor/TG callers.

**Acceptance Criteria:**

**Given** existing `chat.py` and TG call `run_fusion` / `iter_fusion`  
**When** the facade package is introduced and old `fusion.py` becomes a thin re-export or is moved behind the facade  
**Then** all existing fusion smoke/import tests pass and `/v1/chat/completions` with `zeus/fusion` still returns a non-empty answer  
**And** `fusion/*` does not import `routers.*` (AD-6, AD-10)

### Story 1.2: FusionResult handoff and billable states

As a budget-conscious API user,
I want every fusion branch billed by explicit billable state,
So that I am never charged for cancelled-no-tokens work and Onestack matches the ledger.

**Acceptance Criteria:**

**Given** a fusion completion with multiple agent calls  
**When** Bill consumes `FusionResult` (path, policy_path, routed_by, branches[].billable_state, usages)  
**Then** states `completed|partial_stream|cancelled_no_tokens|cancelled_with_usage` are recorded and `cancelled_no_tokens` = ₽0  
**And** chat no longer invents Path from token heuristics alone (FR19, FR20, AD-14; NFR8)

### Story 1.3: Onestack Path fields + legacy routed_by split

As a developer debugging Zeus in Cursor,
I want Onestack to show final Path and honest `routed_by`,
So that I understand why a request was routed.

**Acceptance Criteria:**

**Given** requests via `zeus/fusion`, `zeus/fusion-fast`, `zeus.mode=full`  
**When** responses are returned  
**Then** Onestack includes `path` (final), `policy_path`, optional `escalate_from`, and `routed_by` from the closed set  
**And** legacy aliases use `legacy_*` while `zeus.mode` uses `forced_*` (never conflated) (FR1, FR20, FR37; AD-15)

### Story 1.4: Scrub once + anti-bloat Brief contract

As a developer pasting secrets/code into chat,
I want secrets scrubbed once before upstream and Panel satellites to never see full Cursor dumps,
So that leaks and ×3 context waste are prevented.

**Acceptance Criteria:**

**Given** a message containing API key / bearer / private-key / email-like secret  
**When** fusion runs  
**Then** scrub runs once at Edge→Policy and upstream payloads are masked  
**And** Brief for any satellite path contains only last_assistant + errors + goal (even if FULL not yet live — contract helper ready) (FR21, FR22; AD-17; NFR4)

---

## Epic 2: Smart Cheap Path

Пользователь перестаёт выбирать модель на мелочах: classify + FAST/CASCADE + Mini-Verifier + prefs clamps.

### Story 2.1: Classify phase, complexity, confidence + Effort +1

As a developer,
I want each request classified with phase/complexity/confidence and Effort=high bumping complexity by +1,
So that Path policy has stable inputs.

**Acceptance Criteria:**

**Given** chitchat, UI tweak, and traceback prompts  
**When** classify runs (flash with regex fallback)  
**Then** outputs include `classify_phase`, `complexity_band∈{light,med,heavy}`, `confidence`  
**And** Effort=high applies complexity +1 (cap heavy) with no separate floor; classify fail → CASCADE + `classify_fallback_cascade` (FR4, FR5, FR17)

### Story 2.2: Path policy engine (table + MoR + clamps)

As a developer on Product Mode simple or power,
I want deterministic Path selection for light/cheap work,
So that I get FAST/CASCADE without accidental FULL spend on simple.

**Acceptance Criteria:**

**Given** classify + post-Effort complexity inputs  
**When** policy runs (classify→Effort→first-match table→MoR local scores 0|1 step→mode clamp)  
**Then** Path Phase = classify; `design_lexicon` forces FULL row; MoR uses PRD local formulas (`s_quality/s_cost/s_latency`); tip never demotes  
**And** `simple` clamps RACE/FULL→CASCADE unless forced/legacy full; Kill-Switch→FAST; closed `routed_by` codes emitted (FR2, FR3, FR7, FR28)

### Story 2.3: CASCADE Mini-Verifier + escalate + Leader failover

As a developer sending medium coding asks,
I want cheap-first CASCADE that escalates only when Mini-Verifier fails, with ordered Leader failover,
So that I save money without empty answers when a Leader is down.

**Acceptance Criteria:**

**Given** CASCADE serving Path and Mini-Verifier JSON `{good_enough, confidence, reason}`  
**When** verifier passes at threshold (≥0.8 default)  
**Then** request stops on cheap model without Panel; Leader self-score never gates stop  
**When** verifier fails  
**Then** escalate map from PRD FR-8 applies (Kill-Switch/simple never FULL; med/heavy rules)  
**And** if Leader upstream fails with ready fallback list non-empty → next model serves non-empty answer; empty list → structured disaster error (FR8, FR12, FR15)

### Story 2.4: Custom panel rules + unknown mode ignore

As a custom-mode user,
I want 1/2/3 selected models to resolve predictably,
So that Auto never invents a weird Panel-of-2 on simple/power.

**Acceptance Criteria:**

**Given** Product Mode custom with 1, 2, or 3 ready models  
**When** policy resolves panel  
**Then** 1→FAST-equivalent; 2→A+B no C; 3→A/B/C; dead models excluded  
**And** unknown `zeus.mode` is ignored with `mode_ignored`; `zeus.thinking` passthrough/ignore per FR37 (FR34, FR37)

### Story 2.5: Policy fixture harness (cheap-path set)

As ops/QA,
I want automated Path fixtures for cheap-path policy,
So that FR-28 regressions fail CI before canary.

**Acceptance Criteria:**

**Given** fixture cases F1, F2, F5, F7, F8a, F8b, F9, F10, F14, F15, F16 and interactive gates I1–I3  
**When** the policy fixture harness runs  
**Then** each case asserts expected Path and `routed_by` family  
**And** F5/`design_lexicon` → FULL (power); F7 Kill-Switch → FAST; F8a=`forced_full`; F8b=`legacy_full_alias` (FR28)

---

## Epic 3: Strong Multi-Model Path

На hard/borderline задачах — RACE/FULL с verify/Judge и честным Soft-Stop.

### Story 3.1: RACE path + both-fail terminal

As a developer in an interactive follow-up,
I want speculative RACE (cheap+strong) with a defined failure terminal,
So that borderline turns stay snappy without hanging or empty answers.

**Acceptance Criteria:**

**Given** fixtures F11, F13 (never RACE on heavy), R1, R2  
**When** RACE executes  
**Then** first годный (Mini-Verifier pass or degrade→first-complete strong) wins; loser cancelled with correct billable state  
**And** both-fail → FULL if mode/complexity allow else Soft-Stop/disaster per FR-9; F13 assert Path=FULL never RACE (FR9, FR14, FR28)

### Story 3.2: FULL Panel Brief, diversity, Aspects, near-duplicate

As a developer asking for architecture/review,
I want a diverse Panel with Aspects before clone-exit,
So that FULL is stronger than a single model without shipping near-clones unchecked.

**Acceptance Criteria:**

**Given** FULL Path with ≤3 models (fixtures F4, F12)  
**When** panel runs  
**Then** Leader gets full sanitized context; satellites get Brief only; three same `model_family` forbidden without ops exception  
**And** Aspects correctness+completeness run before τ early-exit; Aspect must-fail blocks τ exit (FR10, FR12, FR22, FR31)

### Story 3.3: Rank-then-fuse + Structured Judge

As a developer receiving a FULL answer,
I want a structured Judge that is not a clone of the strongest branch,
So that contradictions are resolved into one usable final.

**Acceptance Criteria:**

**Given** ≥2 successful distinct branches  
**When** rank-then-fuse + Judge run  
**Then** top-K rule applies (K=2 if Δ≥0.15 else top-3); Judge emits consensus/contradictions/unique/blind spots  
**And** 1 success ⇒ that branch is final (no Judge); anti-bias overlap test fails PR if contradictions + overlap≥0.95 (FR10, FR13)

### Story 3.4: Soft-Stop and cancel mid-flight

As a user who disconnects or hits zero balance mid-Panel,
I want in-flight work cancelled and the best partial returned/billed fairly,
So that I do not burn money after I left.

**Acceptance Criteria:**

**Given** disconnect or Soft-Stop trigger during Panel/RACE  
**When** Execute stops unfinished branches  
**Then** Soft-Stop pick order is verifier confidence → first-complete → Leader-partial  
**And** Bill uses FusionResult billable states only; no unpaid completed branches; no charge for `cancelled_no_tokens` (FR14, FR19)

### Story 3.5: Prompt adaptation v1

As a developer on FULL/CASCADE,
I want short family-specific prompt adaptation,
So that models get usable hints without changing my intent.

**Acceptance Criteria:**

**Given** serving Leader/Satellite family  
**When** prompt adaptation runs  
**Then** rewrite is limited to system/hint layer; user-visible requirements are not added/removed  
**And** changes are covered by publish regression gate (FR32, FR26)

---

## Epic 4: Sticky Prefs & Safe Ship

Липкий Leader, prefs, Shadow/Canary, Eval, runtime, feedback ingest, publish guard, observability, canary-exit ops.

### Story 4.1: Sticky session store (Leader/stack only)

As a developer in a multi-turn Cursor chat,
I want the same Leader retained across turns without sticky Phase stealing Path,
So that dialogue stays stable while new review/plan turns can still escalate to FULL.

**Acceptance Criteria:**

**Given** `X-Zeus-Session-Id` / `zeus.session_id`  
**When** consecutive requests share a session  
**Then** sticky stores leader/stack/phase_meta/expiry in SQLite; Path uses classify Phase (fixtures F3, F17)  
**And** sticky is written at request end with the Leader that actually answered (FR16; AD-7, AD-16; NFR9)

### Story 4.2: Prefs surfaces — Effort + Kill-Switch

As a user configuring Zeus in TG Mini App or кабинет,
I want Effort and Kill-Switch saved on my account,
So that all clients with my key behave the same.

**Acceptance Criteria:**

**Given** authenticated prefs update for Effort and Kill-Switch (plus existing Product Mode/custom)  
**When** a subsequent fusion request omits overrides  
**Then** prefs apply; Kill-Switch forces FAST; Effort feeds FR-5  
**And** precedence remains zeus.* > prefs > default (FR23, FR2, FR3, FR5)

### Story 4.3: Shadow mode + baseline_id + canary flags

As ops,
I want Shadow logging and canary cohort flags,
So that new Path policy can be compared before users see it.

**Acceptance Criteria:**

**Given** shadow flag enabled for a cohort  
**When** requests are served  
**Then** candidate Path is logged vs `baseline_id` while serving path stays baseline decision  
**And** first canary baselines legacy 1↔3; flags support canary_pct + kill (FR18; AD-9; NFR6)

### Story 4.4: Eval suite fixtures + pass oracle harness

As ops,
I want an Eval harness with PRD fixtures, N≥50 suite, and pass oracle,
So that canary→100% is blocked on Path/quality regress.

**Acceptance Criteria:**

**Given** fixture set F1–F17, I1–I3, R1–R2 plus bucket prompts totaling N≥50 and `eval_baseline.json` (frontier + judge ids)  
**When** Eval runs  
**Then** pass oracle checks Path match / non-empty / code fence / `min(correctness,completeness)≥3` / billing OK  
**And** per-bucket bar ≥ baseline−2pp and SM-C1 (+2pp 👎 ceiling on hard) are enforced/documented as canary blockers (FR25; NFR6)

### Story 4.5: Runtime budgets presence

As ops,
I want timeout/concurrency/retry/disaster/keepalive/rate/overflow mechanisms present,
So that Path shipping cannot create silent empties under failure.

**Acceptance Criteria:**

**Given** fusion requests under timeout/upstream failure/overflow  
**When** runtime mechanisms are exercised  
**Then** global timeout, Panel/RACE concurrency caps, retry/backoff, structured disaster error, thinking keepalive, rate limits, and long-context/overflow Leader selection exist  
**And** numeric values live in Settings/ops config; missing mechanism fails Done (FR29; NFR1, NFR2; AD-12)

### Story 4.6: Feedback ingest + routing log (no Elo)

As a developer who thumbs-down a weak answer,
I want 👍/👎/regen recorded with routing context,
So that we can learn later without Elo writeback in MVP.

**Acceptance Criteria:**

**Given** an authenticated client (cabinet and/or TG) after a fusion response with `trace_id`  
**When** user submits 👍, 👎, or regen  
**Then** an ingest API (or existing feedback endpoint extended) persists event with Path, Phase, Leader, `routed_by`, model ids (ops), timestamp  
**And** no Elo writeback affects Leader pick in MVP (FR24)

### Story 4.7: Publish regression gate

As ops,
I want publish continuity checked on prompt-touching releases,
So that HTML `zeuscode.ru/go/…` does not silently break.

**Acceptance Criteria:**

**Given** a release touching Judge, system prompts, Brief, sanitize, or prompt adaptation  
**When** publish regression check runs  
**Then** a full HTML landing still publishes with Zeus badge  
**And** failing check blocks release (FR26)

### Story 4.8: Observability baseline (trace_id, metrics, alerts)

As ops,
I want every fusion request traced and Path metrics/alerts live,
So that canary regressions and dead models are visible.

**Acceptance Criteria:**

**Given** fusion traffic  
**When** requests complete (success or disaster)  
**Then** each request has `trace_id` in logs/Onestack; Path rates by Phase, escalate%, and `routed_by` histogram are emitted  
**And** min alerts exist: verifier always-OK, billing drift, dead models (NFR3; ties FR18 canary rollback signals)

### Story 4.9: Canary exit ops — load test + incident runbook

As ops,
I want a signed load test and incident runbook before 100% Path rollout,
So that wide canary is not a leap of faith.

**Acceptance Criteria:**

**Given** Path policy candidate ready for 100%  
**When** canary exit checklist is evaluated  
**Then** load test results for FAST/CASCADE/RACE/FULL concurrency profiles are recorded  
**And** incident runbook covers rollback, verifier always-OK, billing drift, dead Leader (NFR7; PRD §6.4)

---

## Notes for CE → Dev

- Implement Epic 1 → 2 → 3 → 4 in order; stories within an epic are sequential and do not depend on later stories.
- MVP excludes FR6/FR11/FR27.
- Fixture ownership: S2.5 (cheap), S3.1/S3.2 (RACE/FULL), S4.1 (F3/F17), S4.4 (full suite N≥50).
- Numeric budgets and concrete judge/frontier model ids are ops freeze items before canary 100%, not blockers to start Epic 1.
- IR 2026-07-22 gaps closed: NFR3→S4.8, NFR7→S4.9, oversized S4.5 split, FR15/24/25/28 strengthened.
