# PRD Quality Review - Zeus Role Routing + Verify/Escalate

## Overall verdict
This PRD is **Good** for a launch-increment. The prior product forks are resolved: VP5 locks are represented consistently across the invariant block, FR-2, FR-5, FR-7, FR-18, addendum C/E/L/M/N, and the decided section. Remaining gaps are implementation-readiness details around internal handoff schemas, source precedence, and deferred QA ownership rather than unresolved product direction.

## Decision-readiness - strong
The PRD is decision-ready. Section 0 front-loads the owner invariants: no new buttons, public model id `zeuscode`, expensive multi-role pipeline not default, custom stack hands-off, curator by max `power_score`, and the full VP5 lock set. Section 14 repeats the locked decisions in language an implementer can cite directly.

The previously disputed forks are no longer real holes. Power opus as a doer is explicitly allowed in FR-2 and addendum C2. Curator fallback is explicitly a single full answer with no separate Brief step in FR-18.8 and addendum E/M. RED handling is one test-fix cycle, then Escalate<=2 global in FR-7 and FR-18.5. Merge is file-aware in FR-18.6 and addendum L. Custom without DeepSeek skips Log Analyst in FR-5, FR-18.7, and addendum N.

### Findings
- **low** FR-16 has no owner or re-entry trigger (FR-16; Open Questions; addendum G) - The PRD correctly marks FR-16 as deferred and non-gating, but it does not say who owns the later client matrix or what event reopens it. *Fix:* Add a `[NOTE FOR PM]` with owner, trigger, and expected artifact for the deferred multi-client e2e sprint.

## Substance over theater - strong
The content is earned rather than decorative. The Vision is specific to ZeusCode: one key, one `zeuscode` id, TG modes only, role routing by `power_score`, verification, cost containment, and no Combo/Path UX. The UJs do real work: Artem proves small+logs behavior, Marina proves large+second-signal Pipeline v1, and Denis proves TG prefs versus client setup.

The NFRs and non-goals are product-specific. Router <=2.5s, Log Analyst <=~400 output tokens, small p95 bounds, allowlisted executor, kill-switch behavior, no new Path buttons, no auto-added custom models, and no default 8-12-call flow are not template filler.

### Findings
- *(none material)*

## Strategic coherence - strong
The strategic thesis is coherent: ZeusCode should stay simple externally while becoming role-aware, cost-aware, and verification-aware internally. The feature set follows that arc: Role->Model routing, Gate, DeepSeek Log Analyst, Escalate/Soft-Stop, Test layers, Pipeline v1, Onestack transparency, and FR-17 connect docs all reinforce the same product move.

The metrics validate the thesis at the right level for this increment. SM-1, SM-2, SM-3, SM-6, SM-8, and SM-9 directly check low-cost small behavior, log-gate correctness, escalation termination, Pipeline v1 discipline, connect-doc correctness, and call-count discipline. Counter-metrics correctly prevent the system from optimizing for role count or false GREENs.

### Findings
- *(none material)*

## Done-ness clarity - adequate
Most FRs are testable. FR-1 defines Router outputs and low-confidence behavior; FR-2 defines role-table resolution and score gates; FR-5 defines DeepSeek's JSON contract; FR-6 defines Gate logic; FR-7 defines global escalation and Soft-Stop; FR-9 to FR-11 separate test layers from executor behavior; and FR-18 gives a concrete Pipeline v1 sequence, including the owner-locked fallback behavior.

The remaining done-ness issues are local but relevant for story creation. The PRD names the main artifacts and flow, but a couple of internal handoffs need exact schemas or observable outputs so the same requirements do not fragment across Router, Pipeline v1, executor, and Mini-Verifier stories.

### Findings
- **medium** Brief/component validation is not fully pinned (FR-18.2; addendum M) - The PRD requires `components[]` <=3 with `{id, role, goal, acceptance_one_liner, files_hint?}`, but does not specify uniqueness, allowed `role` values, required ordering, or output-on-invalid behavior. *Fix:* Add a compact validation rule for Brief components: unique ids, allowed roles, required fields, max count, and invalid-Brief fallback.
- **medium** Test-check output shape is unclear (FR-18.5; addendum M step 4) - The PRD says "Test Author check -> RED->fix -> recheck", while addendum M labels "Test check" as score >=950. It is clear enough directionally, but not yet story-ready for RED attribution. *Fix:* Name the process/role that performs check and recheck, and define the minimal output shape such as `{component_id, status, failing_tests, fix_target}`.
- **low** Kill-switch observability is underspecified (FR-4; NFR-5; Decided) - The behavior "kill-switch -> FAST, no Pipeline v1" is clear, but Onestack does not require a visible reason field for debugging and billing review. *Fix:* Add `pipeline_disabled_reason=kill_switch` or equivalent to FR-14/NFR-5.

## Scope honesty - strong
The MVP boundary is explicit and credible. Non-Goals rule out marketplace, Combo Studio UI, human approval per completion, new Path/cascade/race/boost controls, default full test-first pipeline, auto-adding strong models to custom, mid-parallel without curator/no >=950, prose-concat merge, DeepSeek substitution in custom, RACE-first large, Log Analyst as process manager, FR-16 as an MVP gate, and unrelated platform work. MVP Scope mirrors the in-scope/out-of-scope split clearly.

Assumptions are visible rather than hidden. The Vision and Assumptions mark the x4 hypothesis, Assumptions marks `TEST_AUTHOR_MIN=950`, and SM-4's baseline is named as an assumption. The Open Questions section saying "No blockers" is defensible after the owner locks because the prior unresolved forks have been closed.

### Findings
- **low** Inline assumption roundtrip is slightly loose (Vision; Assumptions) - The Vision says "x4 hypothesis - `[ASSUMPTION]`", while the Assumptions section lists "`[ASSUMPTION]` x4 - hypothesis"; this is understandable but not a precise index roundtrip. *Fix:* Use identical assumption text inline and in the assumptions index.

## Downstream usability - adequate
The PRD is broadly usable for UX, architecture, and story creation. The glossary is useful; FR IDs are unique; UJs have named protagonists; addendum C through N gives source-extractable tables for role mapping, soft-stop, fallback behavior, Gate signals, Path lattice, merge, Pipeline v1, and DeepSeek.

The main downstream issue is source-of-truth coordination. The PRD points to parent Fusion/Spine, PRD invariants, addendum J-N, addendum M, FR-17 research, and implementation files. That is normal for a brownfield increment, but story authors need a crisp precedence rule when these sources overlap.

### Findings
- **medium** Normative-source precedence is spread across documents (Document Purpose; Dependencies; addendum I/M) - Frontmatter says `pipeline_canon: addendum.md §M`, Document Purpose says addendum J-N is canon, Dependencies rely on Fusion/Spine, and addendum I says conflicts with AD go to Spine. This is workable but easy for story authors to misapply. *Fix:* Add a short precedence note, for example: Spine invariants > this PRD's owner invariants/FRs > addendum normative sections > source/research docs.
- **medium** FR-17 needs a per-client acceptance map (FR-17; addendum G2) - FR-17 lists canonical base/key/model and exceptions, but it does not require each generated guide/client config to map back to a research row and confidence level. *Fix:* Add an acceptance checklist: `platform_id -> base exception -> model string -> source confidence -> guide file`.

## Shape fit - strong
The shape fits a brownfield launch increment. It is neither over-formalized consumer persona work nor a raw engineering backlog. It uses a small number of user journeys to protect UX and client surfaces, keeps implementation tables in the addendum, and makes the main PRD focus on product-visible contracts and testable consequences.

The chain-top fit is good. UX can protect the no-new-buttons invariant; architecture can extract Role Table, Gate, Pipeline v1, fallback_single, and NFR constraints; story creation has stable FRs and concrete consequences. The remaining issues are precision gaps, not a mismatch between format and product.

### Findings
- *(none material)*

## Mechanical notes
- Severity counts: critical 0, high 0, medium 4, low 4.
- Glossary is strong and mostly consistent. Watch minor drift between "Pipeline v1", "FULL / Pipeline v1", `pipeline=small`, and internal Path terms.
- FR IDs are unique but ordered non-linearly around FR-16/FR-17 and FR-12-FR-15; this is acceptable because IDs are stable and resolvable.
- UJ protagonists are named and contextual: Artem, Marina, Denis.
- Assumptions mostly roundtrip; the x4 assumption wording should be identical inline and in the assumptions index.
- Prior product forks are resolved, including VP5: 1B power opus doer OK; 2A curator full answer with no Brief; 3A test-fix then Escalate<=2; 4B file-aware merge; 5B no DeepSeek in stack means skip Log Analyst.
