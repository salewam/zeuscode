# Coherence audit: Owner Decision A (куратор / no ≥950)

**Scope:** normative pair `prd.md` + `addendum.md`  
**Date:** 2026-07-25  
**Locked rules (Decision A):**

| # | Rule |
|---|------|
| R1 | No model ≥ `TEST_AUTHOR_MIN` (950) in user stack → **full Pipeline v1 does NOT start** |
| R2 | Curator = **max** `power_score` among user-selected stack → `pipeline=fallback_single` |
| R3 | **Mid-parallel without curator forbidden** |
| R4 | **Never auto-add** models (custom / Набор) |

**Question:** Is Decision A single-path and consistent across §0, FR-2, FR-4, FR-12, FR-14, FR-18.8, addendum §E / §M / §K / §C2 — with no leftover «или mid-only» fork?

---

## Executive verdict

**Resolved (normative):** Decision A is locked consistently in `prd.md` and `addendum.md`. The prior fork («fallback single … **или** mid-only без Layer B») is **absent** from both normative files (grep: no `mid-only`, no «без Layer B» as alternate large path).

**Remaining gaps:** Non-blocking wording and observability clarifications; **stale** sibling reviews still describe the old fork and should not be read as canon.

| Metric | Count |
|--------|------:|
| **Critical** (Decision A still ambiguous in normative docs) | **0** |
| **High** (normative cross-ref would mis-implement A) | **1** |
| **Medium** | **3** |
| **Low** | **2** |

**Path:** `_bmad-output/planning-artifacts/prds/prd-zeuscode-role-routing-verify-2026-07-24/review-decision-a.md`

---

## Rule checklist (normative only)

| Rule | §0 | FR-2 | FR-4 | FR-9 | FR-12 | FR-14 + FR-18.8/10 | §E | §M | §K | §C2 |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| R1 no ≥950 → v1 off | ✓ | ✓ | ✓* | ✓† | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| R2 curator → `fallback_single` | ✓ | ✓ | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| R3 no mid-parallel w/o curator | ✓ | — | — | — | — | ✓ | ✓ | ✓ | — | — |
| R4 no auto-add | ✓ | ✓ | ✓ | — | — | ✓ | ✓ | ✓ | — | ✓ |

\* FR-4: simple never enters Pipeline v1 (orthogonal to A on power/custom large paths).  
† FR-9 names «custom» only for Layer B skip; behavior matches A but scope wording is narrow (see H-1).

---

## Section notes

### §0 invariants (prd §0, item 5)

Aligns with Decision A: curator = max score; no ≥950 → v1 off → `fallback_single`. Vision §1 bullets mirror the same (large + ≥950 vs large без ≥950). Non-Goals §5 explicitly forbid mid-parallel on large without curator / ≥950 «вместо решения A».

### FR-18.8 / FR-18.10

Item 8 is single-outcome: v1 off, curator, `fallback_single`, Mini + Log on trigger + Escalate≤2, mid-parallel forbidden, no auto-add. **No «или mid-only».**  
Item 10: `pipeline` enum + `curator_model` — see M-1 for when curator is required on non-`fallback_single` paths.

### FR-2

Custom block states curator, no v1 LLM steps without ≥950, `pipeline=fallback_single` (FR-18.8). Score gates and `pipeline` enum include `fallback_single`. Curator also referenced «в пресете simple/power» under the Custom bullet — structurally odd but semantically covers presets.

### FR-4

Power/custom: Pipeline v1 only large+2nd; custom hands-off; kill-switch excludes v1. Does not restate A explicitly — delegated to FR-18 / addendum §E (acceptable).

### FR-12

Architect fail → `fallback_single` with curator (max score) — consistent with §E row 1. Title still says «Planner / Pipeline» (terminology drift only).

### FR-14 `curator_model`

Field listed additively with `pipeline`. Normative text does not require `curator_model` on every request (e.g. `pipeline=small`) — see M-1.

### Addendum §E

Row «Нет модели ≥950» matches Decision A verbatim (v1 off, curator from user choice, `fallback_single`, no mid-parallel, no auto-add). Footnote: curator never «подсунутый» opus.

### Addendum §M

Trigger for **full** v1 requires ≥950; otherwise §E A. Closing «Нет ≥950» pointer matches. **No mid-only branch.** Step list applies only to «large + есть ≥950».

### Addendum §K

Row `power/custom + large + 2nd + нет ≥950` → FAST-ish / `fallback_single`, curator = max score (§E A). Complements FR-18 trigger.

### Addendum §C2

Custom footnote: curator = max(selected); v1 architect/test_author only if someone ≥950; else §E A; no auto-add. Table rows «skip» for architect/test_author when none ≥950 — consistent with R1.

---

## Findings (remaining)

### High

| ID | Finding | Evidence | Fix hint |
|----|---------|----------|----------|
| H-1 | **FR-9 scopes Layer B skip to «custom» only** | FR-9: «Нет ≥950 in custom → Layer B skipped». §E / FR-18.8 / §0 apply to **any** stack without ≥950 (including hypothetically score-shifted **power** preset). | Change to «нет ≥950 в стеке режима» (mirror §E). |

### Medium

| ID | Finding | Evidence | Fix hint |
|----|---------|----------|----------|
| M-1 | **`curator_model` emission scope unclear** | FR-18.10 lists field for all `pipeline` values; FR-14 silent on required vs optional. Implementers may omit curator on `pipeline=v1` or mis-set on `small`. | One line: `curator_model` **required** when `pipeline=fallback_single`; optional elsewhere (or always = max score in stack for audit). |
| M-2 | **`mode=simple + large + 2nd` not tied to Decision A naming** | §K: simple → FAST/CASCADE, v1 off. No row for large+2nd on simple; §E A text mentions simple/power stacks but K never says whether `fallback_single` / curator applies vs ordinary single-Doer CASCADE. | K footnote: simple large paths stay CASCADE/single-Doer; **Decision A / `fallback_single` applies only when FR-18 mode gate ∈ {power, custom}** and large path would have attempted v1 but for ≥950. |
| M-3 | **Stale reviews still claim mid-only fork** | `validation-report.md`, `review-rubric.md`, `review-pipeline-v1.md` (C-1), `review-adversarial-general.md` quote old FR-18.8 «или mid-only». Normative docs updated 2026-07-25 (`decisions_amended_fallback_curator`). | Mark reviews superseded or regenerate; point readers to §14 + this audit. |

### Low

| ID | Finding | Evidence | Fix hint |
|----|---------|----------|----------|
| L-1 | **FR-12 «Planner» legacy label** | Title / cross-refs vs Architect + curator language elsewhere. | Rename to «Architect / Pipeline avарии» (cosmetic). |
| L-2 | **C2 phrasing «куратор (или кто-то в наборе) ≥950»** | Redundant with curator = max score; not a second branch. | Optional tighten to «если в стеке есть модель ≥950». |

---

## «или mid-only» sweep

| Location | `mid-only` / old fork |
|----------|------------------------|
| `prd.md` | **None** |
| `addendum.md` | **None** |
| Non-normative reviews / validation | **Present (stale)** — see M-3 |

---

## Summary for implementers

**Use:** `prd.md` §0, FR-2/4/9/12/14/18, §14 Decided, `addendum.md` §C2, §E, §K, §M.

**Decision A canonical behavior** for `mode ∈ {power, custom}`, `size=large`, second signal, **no** model ≥950:

1. Do **not** start Pipeline v1 (no Architect Brief / Test Author / mid doer parallel path).
2. Set `pipeline=fallback_single`.
3. Set curator = max `power_score` among user stack; emit `curator_model`.
4. Run curator-led single path + Mini-Verifier + Log Analyst per FR-5 + Escalate≤2 from same stack.
5. Do **not** expand custom Набор.

**Resolved?** **Yes** for PRD + addendum. **Remaining:** H-1, M-1–M-3 (plus low cleanup); refresh stale review artifacts to avoid dual canon.
