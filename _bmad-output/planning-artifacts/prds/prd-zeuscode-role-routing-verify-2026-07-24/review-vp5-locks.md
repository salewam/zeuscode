# VP5 locks — coherence review (prd.md + addendum.md)

**Scope:** `prd.md`, `addendum.md` only  
**Date:** 2026-07-25  
**Locks under test:**

| ID | Decision |
|----|----------|
| **1B** | Power preset: `doer_logic` primary may be top (opus); cost rule «top only arch/tests» does **not** apply to power preset doers |
| **2A** | Curator `fallback_single`: one **full answer**, **no** separate Brief / Architect step |
| **3A** | One Test Author RED→fix→recheck cycle, **then** Escalate ≤2 **global**; test-fix **does not** consume escalate budget |
| **4B** | Merge = **file-aware** (paths/patches), not prose-concat; conflict → strong model (≥950 if present, else curator) |
| **5B** | Log Analyst **skip** if no DeepSeek (or log-capable id) in **user-selected** stack; no auto-substitution |

---

## Lock verdicts (Y/N)

| Lock | Consistent Y/N | Rationale |
|------|----------------|-----------|
| **1B** | **Y** | §0 inv.6, FR-2 (explicit 1Б + carve-out for Pipeline v1 mid preference), §9 Cost, §14 Decided, addendum §C2 row `doer_logic` power. No remaining normative text forbids opus as power doer after 1Б. |
| **2A** | **Y** | §0 inv.6, FR-18.8 (A+2А), §14, addendum §E row «Нет модели ≥950». Architect-fail path (FR-12 → `fallback_single`) aligns with curator-led path without re-opening Brief. |
| **3A** | **Y** | FR-7 ordering, FR-18.5 (single test cycle + pointer to FR-7), §14, addendum §L.4, §M limits («один RED→fix→recheck; затем Escalate≤2»). No second test-manager round; no text assigns test-fix to escalate budget. |
| **4B** | **N** | Normative: FR-18.6, §5 Non-Goals, §14, addendum §L, §M step 6. **Contradiction:** UJ-2 (Marina landing) still says «merge **concat** (architect только при конфликте файлов)» — stale pre-4Б wording. |
| **5B** | **Y** | FR-5 (stack gate + 5Б), FR-18.7, §5 Non-Goals, §14, addendum §E, §M step 7, §N «Когда НЕ». Custom without DeepSeek → skip, Gate without `log_report` (N/A). |

**Summary:** **4/5 Y**, **1/5 N** (4B blocked by UJ-2).

---

## Cross-lock matrix (prd ↔ addendum)

| Lock | prd.md anchors | addendum.md anchors | prd ↔ addendum |
|------|----------------|---------------------|----------------|
| 1B | §0.6, FR-2, §9, §14 | §C2 `doer_logic` power | Aligned |
| 2A | FR-18.8, §14, FR-12 | §E A+2А | Aligned |
| 3A | FR-7, FR-18.5, §14 | §L.4, §M | Aligned |
| 4B | FR-18.6, §5 | §L, §M.6 | Aligned; prd **internal** UJ-2 breaks 4B |
| 5B | FR-5, FR-18.7, §5 | §N, §M.7, §J Layer C | Aligned (§J table is trigger-only; §N carries 5Б) |

---

## Remaining gaps (severity)

| Sev | Gap | Locks touched | Suggested fix |
|-----|-----|---------------|---------------|
| **High** | UJ-2 Pipeline v1 bullet: «merge concat» vs file-aware (4Б) | **4B** | Replace with: file-aware merge per FR-18.6 / addendum §L; architect/≥950 only on file/API conflict. |
| **Medium** | §3 Glossary **Doer** = «mid score» only — no power/opus exception (1Б) | **1B** | Extend Doer gloss: «mid by default; power preset `doer_logic` may be top per FR-2 / 1Б; Pipeline v1 parallel chunks prefer mid per FR-18.4». |
| **Medium** | FR-18.4 «mid 800–920» vs addendum §C3 band «850–949» for doers | 1B (routing only) | Single band reference (e.g. FR-18.4 → «mid per addendum §C3, never ≥ TEST_AUTHOR_MIN for Pipeline v1 doer slots»). |
| **Low** | §1 Vision / §56 hot-path Gate bullets mention Log Analyst without stack gate (5Б) | **5B** | Add «если log-модель в стеке (FR-5)» to Vision small/large bullets. |
| **Low** | FR-12 architect fail → `fallback_single` does not cross-cite «без Brief» (2А) | **2A** | One phrase: «curator full answer per FR-18.8 / 2А». |
| **Low** | UJ-2 «DeepSeek только если всплыли ошибки» vs FR-5 trigger (traceback/error/RED+runtime) | **5B** | Align journey wording with FR-5 + stack gate. |
| **Info** | `review-rubric.md` still describes pre-1Б opus/doer conflict | — | Out of scope for this pair; refresh rubric separately if still used. |

No gap found that reverses **3A** or **5B** decisions. **2A** is normatively solid; only narrative cross-refs are thin.

---

## Recommended edit order (minimal)

1. **UJ-2** — merge line (unblocks **4B → Y** on re-run).  
2. **§3 Doer** glossary — clears **1B** narrative contradiction.  
3. Optional: Vision Log bullets + FR-12 cross-ref for **5B** / **2A** polish.

---

## Re-run checklist

After UJ-2 fix, expect **5/5 Y** if glossary left as medium (non-blocking) or **5/5 Y + zero medium** if glossary band unified.

**Artifact path:** `_bmad-output/planning-artifacts/prds/prd-zeuscode-role-routing-verify-2026-07-24/review-vp5-locks.md`
