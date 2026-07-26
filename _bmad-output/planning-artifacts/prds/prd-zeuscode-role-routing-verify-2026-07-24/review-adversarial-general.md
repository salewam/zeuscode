# Adversarial Review — Zeus Role Routing PRD After VP5 Locks

**Scope:** `prd.md` + `addendum.md` after VP5 locks `1B/2A/3A/4B/5B`.

## Verdict

The VP5 locks fixed the biggest prior contradictions. The PRD now says top power doer is allowed, no-`>=950` uses curator-led `fallback_single` without a Brief pre-step, RED->fix and Escalate are ordered, merge is file-aware rather than prose-concat, and custom without DeepSeek skips Log Analyst instead of silently injecting a model.

What remains is less about product direction and more about executable contracts. The current PRD is implementable only if engineering fills in detector rules, score-table behavior, test-check boundaries, and audit fields. Those are real holes, not preference nits.

## Top Findings

1. **[high] Test-check ownership is still ambiguous.**
2. **[high] DeepSeek/log trigger remains prose, not a detector contract.**
3. **[high] `power_score` gates can silently change production behavior.**
4. **[high] Soft-Stop HTTP 200 can be consumed as valid code by clients.**
5. **[medium] Cost ceilings are now directionally better but still lack a hard scheduler.**

## Prior High/Critical Issues

- **[critical] Prior FR-18.8 no-`>=950` fork: RESOLVED.** `prd.md` FR-18.8 and `addendum.md` §E/§K/§M now choose one path: Pipeline v1 off, curator = max `power_score` from the selected stack, `pipeline=fallback_single`, no mid-parallel, no model injection.
- **[critical] Prior `fallback_single` Brief ambiguity: RESOLVED.** VP5 `2A` now states the curator in fallback writes one full answer immediately, without a separate Brief/Architect step.
- **[critical] Prior RED->fix vs Escalate conflict: RESOLVED.** VP5 `3A` now orders the loop: one Test Author RED->fix->recheck cycle first, then Escalate/`judge_fix` up to the global limit of 2.
- **[critical] Prior prose-concat merge contract: RESOLVED.** VP5 `4B` changed merge to file-aware assembly by Brief paths/patches, with a strong model only on file conflict or broken API joint.
- **[high] Prior power doer/top-model contradiction: RESOLVED.** VP5 `1B` explicitly allows power `doer_logic` primary = `opus-4-8`; the cost invariant now applies to full multi-role pipeline defaulting, not to the power preset's ordinary doer choice.
- **[high] Prior custom Log Analyst/model-injection ambiguity: RESOLVED.** VP5 `5B` says custom without DeepSeek/log-capable model skips Log Analyst; no outside DeepSeek is injected.
- **[medium] Prior Path lattice gap for large without second signal: RESOLVED.** `addendum.md` §K now has `power/custom + large + no 2nd -> CASCADE`, `pipeline=small`, Pipeline v1 off.

## Remaining Findings

- **[high] Test-check ownership is still not a clean role/process boundary.** FR-18.5 says "Test Author check -> RED->fix -> recheck"; FR-10 says Test Executor is the script runner; `addendum.md` §M labels "Test check" as `>=950` and gives it tests + results. That could mean a repeat Test Author call, a judge call, script execution plus LLM interpretation, or LLM-only validation. This affects cost, authority, trace shape, and whether tests actually ran.

- **[high] DeepSeek/log trigger remains prose, not a detector contract.** FR-5/§N trigger on traceback, `Exception`, error tail, or RED+runtime. There is no deterministic detector, source precedence, truncation rule, language coverage, false-positive policy, or evidence payload. If "runtime suspicion" is LLM-derived, it is circular; if regex-derived, the regex contract is missing.

- **[high] `power_score` gates can silently change production behavior.** Pipeline eligibility, curator choice, Soft-Stop winner, conflict-merge strength, and `judge_fix` all depend on `power_score`/`TEST_AUTHOR_MIN=950`. The PRD still does not pin score table versioning, alias normalization, missing-model behavior, unhealthy-but-high-score behavior, or rollout policy when a model crosses 950.

- **[high] Soft-Stop HTTP 200 is unsafe for coding clients.** FR-7 returns HTTP 200 with a nonempty body and a short warning while `gate=RED`. Many coding clients treat assistant text as usable output and may ignore hidden metadata. The PRD needs a visible machine-readable failure marker, OpenAI-compatible finish detail, or patch-suppression rule so failed code is not consumed as passed.

- **[high] Onestack remains overloaded and under-specified.** FR-2/7/14/15/18 rely on Onestack for roles, models, routing, gate reasons, pipeline, billing, soft-stop evidence, and curator. Required fields are missing for skipped roles, fallback attempts, parse degrade, unhealthy fallback, cancelled no-token calls, partial failures, detector evidence, and client-visible vs internal metadata.

- **[medium] Cost ceilings are now directionally better but still not executable.** VP5 removed the default 8-12-call threat by making fallback single and limiting RED->fix. But the ordinary large path can still be Router + Architect + Test Author + 2-3 Doers + test check + RED fixes + recheck + Mini + Log + conflict merge + Escalate. The PRD has budget targets, not scheduling rules that force the ceiling.

- **[medium] Doer isolation is still brittle for shared software work.** Doers see Brief + own piece/tests and not sibling code. File-aware merge helps, but shared imports, types, state shape, route names, generated config, migrations, CSS tokens, and fixtures still require coordination that the Brief schema does not yet guarantee.

- **[medium] Second-signal gating is gameable.** The second signal list is prose: architecture lexicon, multi-file, landing from scratch, explicit heavy. No scoring table, precedence, conflict rule, or eval fixture is specified, so implementers can justify both over-triggering and under-triggering Pipeline v1.

- **[medium] Soft-Stop winner selection can choose a stale partial.** `addendum.md` §D chooses max `power_score` among nonempty billable candidates, tie latest. It does not require relevance to the failed role, post-fix status, alignment with final task, or least-bad Gate evidence. A stale high-score partial can beat a more accurate lower-score output.

- **[medium] Success metrics still count failure-shaped success.** SM-6 accepts "GREEN or Soft-Stop nonempty" for large landing eval, so a failed RED body can improve the metric. SM-2 says Log Analyst "influences Gate" without a measurable influence definition. These metrics test process presence more than outcome quality.

- **[medium] Kill-switch semantics are still underspecified.** NFR-5 says kill-switch -> FAST, no Pipeline v1. It does not say whether Mini, Log Analyst, Escalate, Test Executor, Onestack fields, or billing traces remain active. "FAST" is an internal path name, not an operational contract.

- **[medium] Billing still omits unhappy-path accounting.** FR-15 says every LLM-role is a FusionResult branch and cancelled no-token calls are not billed. It does not define billing/audit behavior for invalid Architect JSON, failed Test Author output, parse-degrade retries, discarded doer partials, conflict judge calls, or escalation candidates that lose Soft-Stop.

- **[low] Mode label copy remains confusing.** FR-4 labels `simple` as "Пользовательский" while `custom` is "Набор". For a product hiding complexity behind exactly three modes, the cheap preset should not look like the custom option.

## New Findings Introduced By VP5 Locks

- **[medium] File-aware merge now needs a minimal patch contract.** VP5 `4B` correctly rejects prose-concat, but the replacement says file-aware assembly by Brief paths/patches without defining patch format, allowed operations, collision resolution, deletion semantics, generated-file handling, or atomicity. This is better than concat, but still not enough for implementation parity.

- **[medium] "Log-capable" custom models need a registry rule.** VP5 `5B` allows Log Analyst if DeepSeek "or log-capable" exists in the selected stack. The PRD names DeepSeek ids but does not define how a model is classified as log-capable, who maintains that registry, or whether a non-DeepSeek log-capable model must obey the exact same JSON degradation rules.

## Severity Counts

- Critical: 0
- High: 5
- Medium: 9
- Low: 1
- Total: 15

## Bottom Line

The VP5 locks resolved the prior top contradictions. Remaining risk is concentrated in executable contracts: test-check role, log detection, score gate versioning, Soft-Stop client semantics, and Onestack/audit shape.
