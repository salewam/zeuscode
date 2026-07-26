# PRD Quality Review — Zeus Fusion (re-validate #3)

## Overall verdict

This PRD is Architecture-freeze ready on the product Path brain: FR-28 (policy → MoR post-pass → mode clamp), closed interactive formula, single-Path fixtures, CASCADE escalate map, Eval pass oracle, and honest MVP≠canary split are load-bearing and specific. Residual risk is peripheral Done-ness (failover/degrade ladders) and canary-gate ops freezes (baseline model ids), not thesis or scope theater. Prior adversarial criticals/highs on RACE-steals-heavy, MoR table contradiction, dual fixtures, and Mode clamps appear aimed at pre-patch text and do not hold against this revision.

## Decision-readiness — adequate

A PM/owner can greenlight CA on the router contract. Trade-offs are stated as decisions: Kill-Switch beats forced Path (FR-2); `simple` clamps RACE/FULL→CASCADE (FR-3); MoR may escalate one step never down (FR-28); Elo/Tradeoff/DUAL parked with Non-Goals + §6.3; MVP Done ≠ Canary 100% (§6.1 / §6.4). Open Questions (§12) are correctly narrowed to Arch/ops numbers, not rhetorical Path holes.

What keeps this from **strong**: status=`final` + stakes=`launch` while SM-V / Eval still need concrete frontier + judge model ids frozen in `eval_baseline.json` before canary (§12 Q3, SM-V assumption). That is an honest deferral for Architecture start, but a decision-maker reading only frontmatter could over-read “final” as canary-ready. MoR tip rule is closed; score provenance (`s_cost/s_quality/s_latency`) remains Arch-owned without a product intent sentence (acceptable, slightly soft).

### Findings

- **medium** Status `final` vs canary-blocking Open Q3 (§0 frontmatter; §12 Q3; §7 SM-V) — Launch-stakes PRD still leaves baseline/judge model ids open. Path product decisions are closed; canary exit is not. *Fix:* Keep status `final` for product freeze, but add one Decision Log line: “SM-V / judge ids owner=Money; freeze before first 10% canary — not a CA blocker.” Or demote Q3 into Assumptions with “TBD id, rule fixed.”
- **low** MoR score functions unspecified (§4.3 FR-28 MoR post-pass) — Tip predicate is testable; how scores are computed is not. *Fix:* One product sentence: “scores are local/heuristic unless separate LLM; bill per FR-19; Arch owns formulas + unit tests.”

## Substance over theater — strong

Vision (§1) is swap-resistant: coding compound brain, OpenAI-compatible client, Path/verify/billing honesty — not generic “AI platform.” Success is tied to Eval + $/1k vs named frontier baseline (SM-V), not anecdote. Four UJs each drive FR clusters (Path, prefs/publish, billing/feedback, ops rollout); none are decorative. NFRs (§8) mostly point at FR-29 / FR-18 / FR-21 with “numbers in Architecture; presence = Done” — presence theater avoided for runtime. Differentiation (§11) cites brownfield 1↔3 / classify / Brief — earned. No persona pile-up, no innovation-for-template section.

### Findings

_(none)_

## Strategic coherence — strong

Thesis holds: win on stratified cheap Paths + quality on hard work + honest bill, not marketplace breadth. FR-28 priority (heavy/plan/review/debug FULL before light FAST/CASCADE before borderline RACE) and Product Mode clamps serve that thesis. SM-1 (FAST+CASCADE share stratified by Phase) + SM-V (pass-rate ∧ $/1k) validate it; SM-C1/C2/C3 are real counter-metrics, not activity vanity. MVP kind is coherent problem-solving/platform (Phases 0–1 + Phase 2 include), not a shuffled backlog. §6.2 include list (B5/B7/B10/A17 tip/Aspect v1) matches the thesis of “strong panel without Phase-3 costume.”

### Findings

- **low** SM-4 lacks magnitude (§7 SM-4) — “p95 latency FAST ↓ vs baseline” has no bar (pp or ms). Secondary only; does not break thesis. *Fix:* Add assumption e.g. “non-regress vs baseline p95 + optional −X% stretch” or mark observational.

## Done-ness clarity — adequate

Core Path Done is unusually sharp for a PRD: FR-28 table + interactive boolean + MoR escalate_one + F1–F15 / I1–I3; FR-8 escalate matrix; FR-19 state×billing; FR-25 pass oracle (a–e); FR-14 Soft-Stop selection order; FR-3 mode clamps with `routed_by`. An engineer can fail a PR on fixtures and billing language.

Peripheral FRs are thinner: FR-15 failover has no ordered ladder (only “ready fallback ⇒ no empty”); FR-17 says “fallback rules” without enumerating them; FR-32 “не меняет user intent” is adjective-level; FR-4 allows classify fallback ∈ {FAST, CASCADE} while F9 pins CASCADE only. Rubric asks to be unforgiving here — hence **adequate**, not strong.

### Findings

- **medium** FR-15 failover ladder missing (§4.4 FR-15) — Consequences ban empty answers and dead Panel members but do not define ordered fallback / when FAST-equivalent vs error. *Fix:* Product rule: ops-ordered ready list per Product Mode; try next; if none → structured disaster error (FR-29); fixture “Leader 500 → next ready → non-empty.”
- **medium** FR-17 degrade fallbacks underspecified (§4.4 FR-17) — “fallback rules” without per-component mapping (classify already in FR-4; Mini-Verifier degrade partially in FR-9; Aspect in FR-31; MoR tip=0 implied). *Fix:* Mini table: component → degrade behavior → `routed_by` / alert; cross-ref existing FR rows.
- **low** F9 vs FR-4 classify-fallback Path (§4.3 F9; §4.2 FR-4) — FR-4 allows FAST|CASCADE; F9 expects CASCADE only. *Fix:* Pin product default (CASCADE) in FR-4 consequences; keep FAST only if Kill-Switch.
- **low** FR-32 “не меняет user intent” (§4.3 FR-32) — Untestable adjective. *Fix:* Consequence: adaptation must not add/remove user-visible requirements; publish regression (FR-26) remains the blocker gate (already partly true).

## Scope honesty — strong

Non-Goals (§5) do real work (marketplace, RAG, semantic cache, Leader self-score exit, BYOK, DUAL/Tradeoff/Presets, TOOL-FULL enum, Elo writeback). §6.1 explicitly splits Product MVP Done from Canary 100%; §6.2/§6.3 tables name TZ IDs with include/exclude rationale; A13/E11/E7 called out. `[ASSUMPTION]` tags + §13 index; `[NOTE]`-class tensions surfaced as deferred v1.x / Arch numbers. Open-items density is low relative to launch stakes — remaining opens are numeric freezes, not silent scope. No evidence of silent de-scope of prior VP criticals; frontmatter update_reason matches body.

### Findings

- **low** E6 “subset” still soft in §6.2 (§6.2 Min alerts; §6.4) — Listed as “verifier always-OK, billing drift, dead models” for canary — enough for honesty; “subset” wording could let eng park alerts under MVP Done. *Fix:* Sentence: “E6 min three alerts required for §6.4; not required to mark §6.2 code-complete.”

## Downstream usability — adequate

Chain-top shape (CA → CE) is served: Glossary (§3), contiguous-enough FR narrative, UJs with named protagonists (Артём/Марина/Серёжа/Ops), Onestack/API surface (§10), brownfield delta (§15), addendum TZ→FR map. Sections largely extractable; fixtures are story-gold.

Gaps: FR IDs skip 30/33/35/36 (unique but non-contiguous — CE traceability friction); full `routed_by` enum deferred to Architecture while policy rows define a partial closed set; addendum is the only TZ roundtrip (fine if always shipped with PRD).

### Findings

- **medium** FR ID gaps (§4 Features) — Missing FR-30, FR-33, FR-35, FR-36. *Fix:* Reserve/renumber in Mechanical pass or add “intentionally unused” note so CE does not invent IDs.
- **low** `routed_by` enum split (§4.3 FR-28; §10) — Policy codes listed; “полный список — Architecture.” *Fix:* PRD owns closed product enum union (policy_* / mor_* / mode_* / legacy_* / classify_fallback_* / mode_ignored); Arch may only add ops diagnostics behind a prefix.

## Shape fit — strong

Product is multi-client coding assistant with prefs UX, billing transparency, and ops rollout — UJs are load-bearing, not overhead. Brownfield vs new table (§15) matches reality. Capability density (Path/Panel/billing) fits a technical platform PRD feeding Architecture; not forced consumer-marketing fluff, not under-formalized. Stakes=`launch` + chain-top justify fixture/oracle rigor. Single-operator ops journey (UJ-4) correctly lighter than end-user UJs.

### Findings

_(none)_

## Mechanical notes

- **Glossary:** Mini-Verifier / Aspect / near-duplicate aligned with FR-12 after prior drift fix; Path enum and v1.x/v2 reservations consistent with FR-11/FR-27/FR-6.
- **ID continuity:** FR-1…FR-37 with gaps at 30/33/35/36; UJ-1…4 contiguous; SM-1…6 + SM-V + SM-C1…C3 unique; fixtures F1–F15, I1–I3 contiguous.
- **Cross-refs:** FR-2↔FR-3↔FR-28↔FR-37 resolve; FR-6 v1.x slot in FR-2 #4 present; FR-25↔§6.4↔SM-2 resolve; addendum TZ map covers A/B/C/D/E IDs cited in §6.
- **Assumptions Index roundtrip:** Inline tags (BYOK, Effort→reasoning, threshold 0.8, τ, K/Δ, anti-bias 0.95, sticky TTL/transport, UI A/B/C, Eval N/bars, SM-V frontier, SM-C1 +2pp) appear in §13; §13 also carries narrative product assumptions (MVP definition, log-only feedback) consistent with body.
- **UJ protagonists:** All four named with inline context.
- **Adversarial parallel note:** `review-adversarial-general.md` (if present as read) attacks FR-28 row ordering, MoR-in-table, dual-accepted fixtures, missing mode clamps, open interactive detector — those issues are **closed in current `prd.md`**. Do not re-open them as rubric criticals on this pass; re-litigate only if a future diff reintroduces them.

---

**Grade hint (for VP synthesis):** Excellent — all dimensions strong/adequate; no critical/high findings on current text.
