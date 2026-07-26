# Adversarial Review — Zeus Fusion PRD (re-validate #3)

## Overall attack

Post-re-VP closed the previous show-stoppers on paper: FULL-before-RACE ordering, MoR as post-pass 0|1 step, interactive boolean + I-fixtures, CASCADE escalate map, `simple` Path clamp, single-Path fixtures, Eval pass oracle, §6.4 canary exit. That work is real — do not re-open those as absences.

What remains is a different class of freeze-blockers: **internal contradictions and undefined terminals inside the now-claimed-deterministic router**. Effort=`high` is specified two incompatible ways (FR-4 floor vs FR-5 +1). Sticky Phase vs classify Phase as FR-28 input is undefined, so review/plan can stick on CASCADE. MoR tip formula is closed while `s_*` score generation is not — fixtures stub tip, production invents MoR. `routed_by` collides between FR-28 forced rows and FR-37 legacy aliases. RACE has no both-fail contract. Status stays `final` / launch stakes while these Path-brain holes remain — Architecture cannot freeze without inventing product policy.

## Findings

- **[critical]** Effort=`high` band transform contradicts itself (FR-4 vs FR-5) — Note. FR-4 signal: Effort=`high` → complexity «не ниже `med`» (floor). FR-5 / pipeline / Assumptions: Effort=`high` → band **+1** (cap `heavy`). For `med` input these diverge: floor keeps `med`; +1 yields `heavy` → FR-28 row 4 `FULL`. *Attack:* Same request, Effort=high, Phase=implement, classify=med → Arch A ships CASCADE/RACE, Arch B ships FULL; Eval fixtures that omit post-Effort band cannot pin Path; SM-1/SM-V gamed by Effort interpretation. *Fix:* One transform only (prefer +1 as in FR-5/Assumptions); rewrite FR-4 signal to match; add fixture E-high: Given classify=med → post-Effort=heavy → FULL.

- **[critical]** Sticky Phase vs classify Phase as FR-28 input undefined (FR-2 pipeline, FR-16, FR-28) — Note. Pipeline has «sticky hint» before FR-28; FR-16 holds Leader/Phase until «substantial» change (needs conf≥0.70 ∨ strong signal). Policy table predicates use `Phase` without saying whether that is classify Phase, sticky Phase, or sticky-unless-substantial. *Attack:* User sends review/plan while sticky=implement and classify conf=0.65 → sticky wins → misses row 4 FULL → CASCADE; hard work never Panels; F5/F12 pass in Eval (fresh session) while production sticky sessions regress quality. *Fix:* Explicit rule: `policy_phase = substantial_change ? classify_phase : sticky_phase` (or always classify for Path, sticky only for Leader); define substantial before Path match; fixture sticky=implement + new review conf=0.65 → expected Path.

- **[high]** `routed_by` collision: FR-28 forced vs FR-37 legacy (§4.3 rows 2–3 vs FR-37) — Note. FR-28 maps legacy fast/full aliases to `forced_fast` / `forced_full`. FR-37 maps same aliases to `legacy_fast_alias` / `legacy_full_alias`. PRD also says closed enum «полный список — Architecture» while already assigning conflicting codes. *Attack:* Two compliant implementations; Onestack histograms / canary dashboards incomparable; Shadow diffs disagree on baseline labels. *Fix:* One code per surface (e.g. legacy alias ≠ forced `zeus.mode`); publish closed `routed_by` enum in PRD (not «Arch invents list»).

- **[high]** MoR `s_cost/s_quality/s_latency` generation undefined (FR-28 MoR, Glossary MoR blend, A17) — Note. Tip rule is closed (`dominant=quality ∧ s_quality≥0.60` → +1 step), but **how scores are produced** (inputs, weights, local vs LLM, dependence on Phase/complexity/confidence) is absent. Fixtures F14 stub `tip_escalate=1` as Given — they never test score→tip. TZ A17 «голосуют / простые веса» is not met by a tip threshold alone. *Attack:* Ops hard-codes tip≈0 forever (MoR checkbox) or tip≈1 on every med request (RACE/FULL storm); both «meet PRD»; canary Path distribution unexplained. *Fix:* Product-level score contract (even if simple): e.g. functions of `{complexity, confidence, Phase, Effort, path_cost_hint}` with fixed weights published; ≥2 fixtures where tip derives from scores, not stubbed.

- **[high]** RACE both-fail / neither-годный terminal undefined (FR-9, FR-29) — Note. FR-9 defines win («Mini-Verifier pass или degrade→first-complete strong») and cancel billing; silent on **both branches fail verifier**, both error, or timeout with no годный. No escalate-to-FULL, no Soft-Stop pick, no structured error. *Attack:* Empty/partial garbage returned; or eng invents silent FULL after RACE (cost + latency surprise); disaster path never triggered consistently. *Fix:* Closed terminal map: both-fail → {return best partial by FR-14 order | escalate FULL if mode allows | structured error}; fixture R-fail.

- **[high]** Architecture/plan lexicon gates RACE only — not FULL (FR-28 interactive vs row 4, F5) — Note. Lexicon (`спроектируй|…`) forces `interactive=false` but does **not** force row 4. F5 Expected FULL assumes classify yields plan/heavy; if classify returns `implement`+`med`, policy → default CASCADE. *Attack:* System-design prompts systematically under-Path'd; F5 is an Eval theater row that production classify will miss; Vision «coding compound brain» fails the plan job. *Fix:* Either lexicon∩design verbs ⇒ treat as plan/heavy for policy (or dedicated predicate → FULL), or F5 Given must pin `Phase=plan`/`complexity=heavy` as classify outputs and add negative: implement+med+lexicon → documented Path.

- **[medium]** CASCADE escalate mid-request vs Onestack/`routed_by` (FR-8, FR-20) — Note. Escalate map can change CASCADE→FULL (or stronger_leader) after serving Path was CASCADE. Unclear whether Onestack `path` is initial policy Path, final execution Path, or both; whether `routed_by` stays `policy_*` or becomes escalate_*. *Attack:* Billing/Path metrics disagree; SM-1 counts CASCADE while user paid FULL. *Fix:* `path` = final execution; initial `policy_path` + `escalate_from` fields; enum codes for cascade escalate.

- **[medium]** Near-duplicate early-exit vs Aspect must-fail precedence (FR-10, FR-12, FR-31) — Note. Near-duplicate may stop without full Judge; Aspect must-fail ⇒ no early-exit / escalate-safe. Order when both apply undefined. *Attack:* Clone-detect exits before Aspect runs → ships incomplete consensus; or Aspect always blocks near-duplicate → τ useless. *Fix:* Aspects before near-duplicate early-exit; fail ⇒ continue/escalate, never exit.

- **[medium]** Eval oracle «≥3/5 on correctness+completeness» aggregation undefined (FR-25) — Note. Unclear: both dimensions ≥3, average ≥3, sum ≥6, or min. Judge model id still Open Q3 (selection rule only in SM-V). *Attack:* Soft aggregation at canary time; SM-V «won» on generous reading. *Fix:* `min(correctness,completeness) ≥ 3` (or both ≥3); freeze judge id in `eval_baseline.json` before CA or mark SM-V non-blocking for freeze.

- **[medium]** Interactive lexicon still Arch-extensible (FR-28 interactive; residual of prior high) — Note. Formula is closed structurally, but lexicon is «минимум … Arch публикует полный список ⊇». Product Path still moves when Arch grows the list. *Attack:* Quiet Path distribution shift without PRD change. *Fix:* Versioned lexicon id in router `baseline_id` / Eval snapshot; PRD owns v1 list or explicitly accepts Arch-owned versioned artifact as freeze input.

- **[medium]** SM-1 metric gaming via RACE (§7 SM-1, FR-28) — Note. SM-1 maximizes FAST+CASCADE share (non-FULL) stratified by Phase. RACE is neither FAST/CASCADE nor FULL — can absorb borderline traffic without helping SM-1 or counting as Panel. *Attack:* Tune interactive/MoR to dump load into RACE; SM-1 «improves» or stays flat while $/1k and p95 degrade (SM-C2 spirit). *Fix:* Report RACE share as first-class; SM-1 denominator/numerator rules include RACE explicitly (e.g. success = FAST+CASCADE only if RACE≤cap).

- **[medium]** Phase-4 ops IDs still fuzzy outside §6.4 (E5, D6, E12; TZ Phase 4) — Note. §6.4 covers E6/E15/E18/Eval; E5 metrics+`trace_id`, D6 log retention policy, E12 API contract freeze appear in §8/§10/FR-21 but not as MVP Done vs canary accounting. *Attack:* MVP Done claimed without trace cardinality / log TTL / contract freeze owner. *Fix:* One line each in §6.2 or §6.4 (presence vs exit).

- **[medium]** Judge path when only one successful Panel branch (FR-13, FR-10) — Note. Judge required at ≥2 different successful branches; single success / single custom-2 failure path unspoken. *Attack:* Unnecessary Judge cost on 1 branch, or empty synthesis. *Fix:* 1 success ⇒ that branch is final (no Judge); 0 ⇒ FR-14 / disaster.

- **[medium]** Status `final` + Open Q3 under launch stakes (frontmatter, §12) — Note. Concrete judge + power Leader ids still open while router contract has criticals above. *Attack:* CA starts from «final» PRD and freezes invented Path semantics. *Fix:* `draft` until criticals close, or Decision Log with owners; Q3 must not block if SM-V demoted — but Path criticals must.

- **[low]** F9 vs FR-4 classify fallback set (FR-4, F9) — Note. FR-4 allows fallback Path ∈ {FAST, CASCADE}; F9 expects CASCADE only. *Attack:* FAST fallback «compliant» breaks F9. *Fix:* FR-4 = CASCADE (or FAST only for chat lexicon); align F9.

- **[low]** TZ A2 «escalate в full» vs light CASCADE stop (TZ A2, FR-8) — Note. Product narrowed light escalate to stronger_leader→stop (never FULL). Honest if intentional; silent TZ drift. *Fix:* One sentence in addendum: A2 MVP subset ≠ always-FULL.

- **[low]** `zeus.thinking` exposed, undefined (§10) — Note. Public optional field with no FR semantics (passthrough? force thinking? ignore?). *Attack:* Clients set it; behavior differs by eng. *Fix:* Map to Effort/upstream reasoning or «ignored in MVP».

- **[low]** Aspect-Verifier «опционально на CASCADE escalate» (FR-31) — Note. When required vs skipped is flag-soup. *Attack:* Aspect MVP only on FULL in practice; CASCADE escalate quality hole. *Fix:* Required on CASCADE→FULL escalate path; optional elsewhere via flag.

## Severity count

| Severity | Count |
|---|---|
| critical | 2 |
| high | 4 |
| medium | 8 |
| low | 4 |

## Prior disposition

| Prior claim (re-validate #2) | Disposition after #3 |
|---|---|
| Path-policy absence | **Stays closed** |
| RACE steals `heavy` / ordering | **Stays closed** (FULL before RACE; row 7 excludes heavy; F13) — residual: lexicon≠FULL (new high) |
| MoR vs first-match control flow | **Stays closed as flow** — **residual high:** `s_*` generation undefined |
| Interactive hint open | **Mostly closed** — residual medium: Arch-extensible lexicon |
| CASCADE escalate circular | **Stays closed as map** — residual medium: Onestack/`routed_by` on escalate |
| Product Mode Path clamp | **Stays closed** (FR-3, F15) |
| Dual-accepted fixtures | **Stays closed** — residual via sticky/Effort/classify ambiguity (new criticals) |
| Eval pass oracle / SM-V rule | **Mostly closed** — residual medium: 3/5 aggregation + Q3 ids |
| §6.4 canary exit / E6 | **Stays closed** — residual medium: E5/D6/E12 accounting |
| MVP honesty / DUAL/Tradeoff out | **Stays closed** |
| Billing states / Soft-Stop / FR-29 presence | **Stays closed** |

**Verdict for VP:** still **not Architecture-freeze ready**. Prefer PRD Update on the two criticals + MoR scores + `routed_by` + RACE terminal before CA. Grade hint if scored now: **Fair** (strong structure, residual Path-brain holes).
