# Reconcile: Owner Decisions × PRD × TZ

**Date:** 2026-07-24  
**Artifacts:** `prd.md` (final) + `addendum.md` vs owner decisions + `docs/TZ_ZEUS_ROLE_ROUTING_VERIFY.md`  
**Verdict:** All **9/9** locked owner decisions are incorporated in the finalized PRD/addendum. Residual gaps are mostly TZ lag and a few internal wording tensions.

---

## Decisions coverage

| # | Owner decision | Verdict | Where it appears |
|---|----------------|---------|------------------|
| 1 | Decompose in MVP / first ship | **PASS** | PRD §4.4, §6.1, §14 Decided; Addendum C (`Large (MVP, power/custom)`) |
| 2 | Cap = Doers only ≤2; `log_analyst` + `mini_verifier` outside | **PASS** | FR-3; §14 Decided; Glossary Soft-Stop/roles; Addendum C |
| 3 | Hot Gate = logs + mini; tests N/A if skipped; manual QA all onboarding clients | **PASS** | FR-6 (N/A if skipped), FR-8, FR-16, SM-6; §14 Decided; Addendum D |
| 4 | `simple` Path ceiling FAST\|CASCADE | **PASS** | FR-4; §14 Decided; Addendum C Path lattice; Risk table |
| 5 | Soft-Stop = partial answer + `gate=RED` | **PASS** | Glossary Soft-Stop; FR-7 (`soft_stop=true`, partial, `gate=RED`); Addendum D |
| 6.1 | `lint` not critical | **PASS** | FR-6, FR-9; §6.2 Out of Scope; §14 Decided; Addendum D |
| 6.2 | TG = prefs only; coding on IDE Client surfaces | **PASS** | Glossary Prefs/Client; UJ-3; §4.5, FR-14; §14 Decided; Addendum C |
| 6.3 | UI: power = `gemini-3.1-pro` primary / Claude fallback; simple = haiku primary, not Gemini-pro | **PASS** | FR-2; §14 Decided; Addendum B (`doer_ui` rows) |
| 7 | FR-16 = **ALL** onboarding clients (not top-N) | **PASS** | FR-16 full list + consequences; SM-6; §6.1; Addendum C |

**Pass count: 9 / 9**

---

## Remaining gaps

High residual gaps (product/contract clarity — not missing owner decisions):

1. **TZ §3.3 still stale on `ui (simple)`** — TZ primary=`gemini-3-pro` / fallback=haiku; locked owner + PRD/Addendum invert this (haiku primary). TZ not revised after decisions → implementers reading TZ alone will ship the wrong simple UI mapping.

2. **Decompose “first ship” vs phase ordering** — PRD locks FR-12/13 in MVP first ship, but TZ Stage 5 / sprint S3 and Addendum F still list Planner/Decompose as phase **5** after Test Executor. Ambiguous whether that is within-MVP sequencing or residual P1 deferral language.

3. **Small LLM-budget semantics diverge from TZ DoD** — TZ DoD §9 / risk §8 imply “1 doer + mini” or “≤2 + verifier”; PRD FR-3 allows ≤2 Doers **plus** `log_analyst` + `mini` outside the cap (and Router). Eval/DoD acceptance criteria for “how many LLM calls on small” are not restated in PRD against the new cap.

4. **Soft-Stop honesty on clients that ignore Onestack** — FR-7 requires HTTP 200 + partial + `gate=RED`/`soft_stop=true`, but no required user-visible failure surface when the IDE client only shows assistant text. Risk of silent “looks successful” Soft-Stop.

5. **`build_failed` producer undefined** — Gate matrix (FR-6 / Addendum D / TZ §3.5) lists `build_failed` as critical when applicable, but no FR defines when/where a build probe runs (vs Test Executor), especially on hot path.

Additional (lower):
- FR-16 list is authoritative in PRD, but no pointer to the live Mini App onboarding source of truth; drift risk if the screen changes.
- Addendum G line “Gemini primary на UI” oversimplifies (true for power only); FR-2/B are correct — G is slightly loose.
- NFR id collision with TZ (PRD NFR-4 = scrub vs TZ NFR-4 = `cancelled_no_tokens`) — numbering only; billing rule still in FR-15.

---

## Contradictions

| Severity | Conflict | Resolution implied by finalized PRD |
|----------|----------|-------------------------------------|
| **Hard (TZ lag)** | TZ §3.3 `ui (simple)` = `gemini-3-pro` primary vs owner 6.3 / FR-2 / Addendum B = `claude-haiku-4-5` primary | **PRD wins**; TZ should be patched |
| **Hard (TZ lag)** | TZ Path map §4.3: large → RACE\|FULL with no mode ceiling vs FR-4 simple ∈ {FAST,CASCADE} | **PRD wins** |
| **Medium** | TZ Stage 5 = Decompose P1 / S3 later vs PRD §4.4/§6.1/§14 = Decompose in first ship | **PRD wins** on scope; Addendum F phase list needs “all 1–5 in first ship” clarification |
| **Medium** | Addendum C Large flow: “Mini-Verifier (hot)” only vs FR-6: Mini-Verifier fail is critical on **hot + Studio** | Prefer **FR-6**; clarify whether Studio large always runs Mini or only when executor skipped |
| **Soft** | TZ DoD “малая: 1 doer + mini_verifier” vs FR-3 ≤2 Doers + log/mini outside cap | **PRD/owner win**; update TZ DoD wording |
| **Soft** | Addendum G “Gemini primary на UI” vs simple-haiku rule | Cosmetic; FR-2 is normative |

No owner-decision vs finalized-PRD contradictions found. Remaining conflicts are **TZ (and one Addendum C/G wording) vs locked PRD**.

---

## Summary

- **Decisions: 9/9 PASS**
- **Blockers for “decisions incorporated?”: none**
- **Before impl from TZ alone:** patch TZ §3.3 ui(simple), Path×mode lattice, DoD small-cap, and Stage-5 “first ship” language to match PRD.
