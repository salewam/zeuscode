# Validation Report — Zeus Fusion — Coding Compound Brain (re-validate #3)

- **PRD:** `_bmad-output/planning-artifacts/prds/prd-zeuscode-fusion-2026-07-22/prd.md`
- **Rubric:** `.agents/skills/bmad-prd/assets/prd-validation-checklist.md`
- **Run at:** 2026-07-22T12:25:00+03:00
- **Grade:** Poor

## Overall verdict

Структура Path-brain после post-re-VP **сильная**: FULL-before-RACE, MoR post-pass, interactive formula, mode clamps, fixtures, Eval oracle, §6.4 — прошлые show-stoppers закрыты.

Но появились **внутренние противоречия** в уже «закрытом» роутере: Effort=`high` задан двумя несовместимыми правилами (FR-4 floor vs FR-5 +1); Phase для FR-28 (sticky vs classify) не определён. Adversarial: 2 critical / 4 high. Rubric walker был слишком мягким (Excellent / 0 critical) и **пропустил** эти freeze-blockers — parent принимает adversarial на critical/high Path-brain.

**Architecture freeze — нет**, пока не закрыты 2 critical + минимум RACE terminal / `routed_by` / MoR `s_*`.

## Dimension verdicts

(Parent override vs rubric walker where adversarial criticals apply)

- Decision-readiness — **thin** (was adequate in rubric; critical Path contradictions)
- Substance over theater — strong
- Strategic coherence — strong
- Done-ness clarity — **thin** (sticky/Effort/RACE terminals)
- Scope honesty — strong
- Downstream usability — adequate
- Shape fit — strong

## Findings by severity

### Critical (2)

**[Adversarial]** — Effort=`high` band transform contradicts (FR-4 vs FR-5)  
FR-4: floor ≥`med`. FR-5/Assumptions: +1 (cap heavy). classify=`med` + Effort=high → med vs heavy → FULL fork.  
Fix: One transform only (+1); align FR-4; fixture E-high → FULL.

**[Adversarial]** — Sticky vs classify Phase as FR-28 input undefined (FR-2/16/28)  
Policy uses `Phase` without saying sticky vs classify; sticky implement + new review conf=0.65 can miss FULL.  
Fix: `policy_phase = substantial ? classify : sticky` (or always classify for Path); fixture sticky+review.

### High (4)

1. `routed_by` collision FR-28 forced vs FR-37 legacy aliases — one code per surface + closed enum in PRD.  
2. MoR `s_*` score generation undefined — product score contract + fixtures from scores not stubs.  
3. RACE both-fail terminal undefined — closed map + fixture.  
4. Architecture lexicon gates interactive only, not FULL — lexicon⇒plan/heavy for policy or pin F5 Given.

### Medium (selected)

CASCADE escalate vs Onestack `path`; near-duplicate vs Aspect order; Eval 3/5 aggregation; lexicon versioning; SM-1 ignores RACE; E5/D6/E12 accounting; Judge on 1 branch; status final vs residual; FR-15/17 ladders (rubric).

### Low

F9 vs FR-4 fallback; TZ A2 drift note; `zeus.thinking` undefined; Aspect on CASCADE escalate.

## Prior disposition (#2 → #3)

| Prior | Status |
|---|---|
| RACE steals heavy / MoR flow / interactive / escalate map / mode clamp / dual fixtures / Eval oracle / §6.4 | **Stay closed** |
| Residual | New criticals (Effort, sticky Phase); highs above |

## Mechanical notes

- Rubric vs adversarial disagreement resolved in favor of adversarial on Path-brain criticals.
- FR IDs non-contiguous (30/33/35/36 skipped) — CE friction only.

## Reviewer files

- `review-rubric.md` (walker: over-optimistic Excellent)
- `review-adversarial-general.md` (authoritative for freeze gate this pass)

## Recommended next

1. ~~**Update PRD**~~ — **done 2026-07-22 (post-VP#3)**.  
2. Optional re-VP → **CA**.

## Update disposition (post-VP#3)

| Finding | Disposition |
|---|---|
| Critical Effort floor vs +1 | **Fixed** — +1 only; F14/F16 |
| Critical sticky vs classify Phase | **Fixed** — Path=classify; sticky=Leader; F3/F17 |
| High routed_by collision | **Fixed** — legacy_* ≠ forced_*; closed enum; F8a/F8b |
| High MoR s_* | **Fixed** — local score formulas + tip from scores |
| High RACE both-fail | **Fixed** — FR-9 map; R1/R2 |
| High lexicon≠FULL | **Fixed** — design_lexicon→FULL; lexicon_v1 |
| Mediums (Onestack path, Aspect order, Eval min, SM-1 RACE, FR-15/17, Judge 1-branch) | **Fixed** |
