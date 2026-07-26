# Coherence review: Pipeline v1 (FR-18) vs addendum M/N/J/K/L/C2 vs FR-5/9/12

**Scope:** `prd.md` + `addendum.md` (normative pair).  
**Date:** 2026-07-25  
**Question:** Are FR-18, merge/cost/gate companions, and glossary/C2 aligned enough to implement one pipeline?

---

## Executive verdict

**Mostly aligned** on the locked owner decisions: Brief **≤3** components, `TEST_AUTHOR_MIN=950`, concat merge with top only on conflict, custom never auto-adds models, DeepSeek log-only JSON, Path lattice without UX, SM-6/SM-9 cost guards.

**Blockers for story split:** (1) no-≥950 on **large+2nd** — FR-18 §8 offers two outcomes without a decision rule; (2) **Planner/Decompose** legacy strings vs **Architect / Pipeline v1**; (3) **addendum M** trigger omits **mode ∉ simple** that FR-18 hard-requires.

Non-normative `.memlog.md` still records **≤4 parallel** Decompose — contradicts FR-18/addendum M **≤3**; do not use memlog as canon.

---

## Findings by severity

### Critical

| ID | Finding | Evidence | Fix hint |
|----|---------|----------|----------|
| C-1 | **No-≥950 + large+2nd: two pipelines, no chooser** | FR-18 §8: «fallback single strongest + verify (как FR-12) **или** mid-only без Layer B». Addendum M § limits: only «skip B/architect LLM». M step 1 still assumes Architect Brief; without ≥950 there is no `components[]` schema entry. FR-9 skips Layer B but does not set `pipeline` Onestack value for this branch. | One row in addendum E + FR-18 §8: e.g. «нет ≥950 → `pipeline=fallback_single` (strongest + Mini + Log по FR-5); Pipeline v1 **не** стартует» **или** document explicit «Brief-less mid parallel» with `pipeline=v1_degraded` — pick one. |
| C-2 | **Planner/Decompose vs Pipeline v1 / Architect** | Glossary + FR-18 + M use **Architect**, **Pipeline v1**, `components[]`. FR-12 title «Planner / Pipeline»; FR-12 `decompose=fallback_single`; FR-1/§14 «Decompose»; addendum E «Architect/Planner fail»; FR-130 «verify/planner по триггеру». No `planner` role in glossary or C2. | Global replace in normative docs: **Planner/Decompose → Architect fail / Pipeline v1 fallback**; keep `fallback_single` as Onestack enum only. |

### High

| ID | Finding | Evidence | Fix hint |
|----|---------|----------|----------|
| H-1 | **Addendum M trigger weaker than FR-18** | FR-18 §1: `mode ∈ {power, custom}`. M «Триггер»: only `size=large` + 2nd — **simple not excluded**. FR-4 says simple без Pipeline v1. Reader of M alone could allow simple+large+2nd. | M trigger line: mirror FR-18 §1 verbatim (include mode gate + NFR-8). |
| H-2 | **Conflict merge vs `judge_fix` score gate** | FR-18 §6 + addendum L: conflict → «Architect/**Judge** ≥950». Glossary: conflict-merge gated by `TEST_AUTHOR_MIN`. C2 `judge_fix`: **max power_score(stack)**, «prefer ≥950» — not required. Custom 3× mid models: judge could be &lt;950. | L + FR-18: «conflict merge: first model in stack ≥ TEST_AUTHOR_MIN; else escalate concat + RED стык» OR elevate judge_fix to ≥950 when used for merge. |
| H-3 | **Path lattice gap: large label without 2nd signal** | FR-1: low confidence → `size=large` but Pipeline v1 only with 2nd; else single-Doer. K table has no row for `power/custom + large + **no** 2nd`. SM-6 requires 0% `pipeline=v1` without 2nd on eval — good — but serving Path (CASCADE vs FAST) unstated. | K: add row «large, no 2nd → CASCADE (or FAST), `pipeline=small`, Pipeline v1 OFF». |

### Medium

| ID | Finding | Evidence | Fix hint |
|----|---------|----------|----------|
| M-1 | **DeepSeek trigger drift (FR-5/N vs M vs UJ-2)** | FR-5 + N: traceback / Exception / error tail / RED+runtime suspicion; else skip. M step 7: «только если **есть ошибка**». UJ-2: «DeepSeek только если **всплыли ошибки**» (broader). FR-18 §7 points to FR-5 — OK — but M/UJ weaken normative precision. | M step 7 + UJ-2: «по FR-5 / §N»; drop vague «есть ошибка». |
| M-2 | **FR-12 vs FR-18 happy-path merge** | FR-12 is аварийный контракт but also names Planner; FR-18 §6 is canonical merge. Addendum L duplicates FR-18 — aligned — but FR-12 doesn’t cross-ref L/M. | FR-12 intro: «аварии и fallback; happy-path merge = FR-18 §6 / addendum L». |
| M-3 | **Test check step role (M §4)** | M step 4 «Test check \| ≥950» — not a glossary Role; FR-18 §5 «Test Author check». Implies second ≥950 call; cost budget ~6–8 may double-count Test Author. | Clarify: «повторный вызов role=test_author» or «script + mini»; update budget table. |
| M-4 | **Custom mode: C2 vs FR-5 log model** | C2 custom rule: selected models only; skip architect/test_author if none ≥950. No row for `log_analyst` / `mini_verifier` / `router` under custom — FR-2 defers to table. Implementers must infer mapping from selected set. | C2 footnote: custom resolution order (e.g. best fit per role from ≤3, unhealthy → skip role). |
| M-5 | **Legacy «Decompose» in metrics/decisions** | §14 decided + FR-1 still say Decompose alongside Pipeline v1; SM-6 text updated to Pipeline v1 — good — but FR-1 bullet still «Pipeline v1 / Decompose». | Single term: **Pipeline v1** in FR-1/§14. |

### Low

| ID | Finding | Evidence | Fix hint |
|----|---------|----------|----------|
| L-1 | **Doer mid band numeric drift** | FR-18 §4: «mid **800–920**». Addendum C3: doers «**850–949**». Same intent (not ≥950), different bounds. | Point FR-18 §4 at C3 or use «mid per C3, never ≥ TEST_AUTHOR_MIN». |
| L-2 | **Glossary Role list vs C2** | Glossary Role enum includes `router`, …, `judge_fix`, ellipsis; **test_executor** only under separate term. C2 includes `test_executor`. Minor extractability gap for stories. | Add `test_executor` to Role bullet or «see Test Executor». |
| L-3 | **SM-9 vs FR-18 §9 (small only)** | SM-9: small p95 LLM ≤4. FR-18 §9: small **2–4** orientir. Consistent (p95 cap at top of range). Large budget ~6–8 has no SM — only FR-18 §9 + defect 8–12. | Optional SM-10 for large p95 ≤9 — backlog. |
| L-4 | **Stale ≤4 component artifact (non-normative)** | `.memlog.md` VP3: «Decompose practical **<=4 parallel**». Normative docs: **≤3** everywhere (FR-18, glossary Brief, M, K, SM-6). | Archive memlog line or annotate superseded by Pipeline v1 ≤3. |

---

## Checklist (requested axes)

| Axis | Status | Notes |
|------|--------|-------|
| **components ≤3 vs leftover ≤4** | **PASS** (prd + addendum) | No ≤4 in `prd.md` / `addendum.md`. Stale ≤4 only in `.memlog.md` (L-4). |
| **TEST_AUTHOR_MIN** | **PASS** | Default 950: glossary, FR-2, FR-9, FR-18, C3, J, M; Architect + Test Author + conflict-merge named consistently. |
| **Merge rules** | **PASS** with H-2 | concat default; top only on file/API conflict — FR-18 §6, L, UJ-2, §14. Judge vs ≥950 on conflict needs lock (H-2). |
| **DeepSeek trigger** | **PASS** (FR-5/N) / **WARN** (M, UJ-2) | FR-5 ↔ N aligned. M step 7 + UJ-2 wording softer (M-1). |
| **Custom skip** | **PASS** with C-1 | FR-2, FR-9, FR-18 §8, C2, E, J: no auto-add; skip ≥950 roles. Branch when large+2nd still fires without ≥950 undefined (C-1). |
| **Path lattice (K)** | **WARN** | Matches FR-4 kill-switch, simple, small/large+2nd. Missing large-without-2nd row (H-3). M mode gate missing (H-1). |
| **SM-6 / SM-9** | **PASS** | SM-6 ↔ FR-18 (Brief≤3, no v1 without 2nd). SM-9 ↔ FR-18 §9 small 2–4 band. |
| **Glossary roles vs C2** | **PASS** with L-2, C-2 | Same role ids except planner legacy (C-2). test_executor naming (L-2). custom column absent by design (M-4). |

---

## Cross-FR sanity (FR-5 / FR-9 / FR-12 vs FR-18)

| Pair | Alignment |
|------|-----------|
| **FR-5 ↔ FR-18 §7** | FR-18 defers Log Analyst to FR-5; pipeline order merge → Log (M steps 6→7) matches Vision §1. |
| **FR-9 ↔ FR-18** | Layer B only Pipeline v1 + ≥950; matches M steps 2–4. Skipped Layer B when no ≥950 matches custom rules; combined behavior with FR-18 §8 still ambiguous (C-1). |
| **FR-12 ↔ FR-18** | Shared `fallback_single`, escalate≤2, Soft-Stop. FR-12 «0 components» consistent with Brief ≤3 failure. Terminology split Planner vs Architect (C-2). Happy-path parallel doers: FR-13 + FR-18 §4 — aligned. |

---

## Recommended edit order (minimal)

1. **C-1 + C-2** — unblock epics (one fallback policy; rename Planner/Decompose).  
2. **H-1, H-3** — addendum M trigger + K row.  
3. **H-2, M-1** — merge gate + DeepSeek wording in M/UJ-2.  
4. **L-1, L-4** — numeric band + memlog hygiene.

---

## References

- Normative: `prd.md` §3, FR-5, FR-9, FR-12, FR-18, SM-6, SM-9; `addendum.md` C2, J, K, L, M, N.
- Non-normative stale: `.memlog.md` (≤4 parallel, 4–6 roles).
