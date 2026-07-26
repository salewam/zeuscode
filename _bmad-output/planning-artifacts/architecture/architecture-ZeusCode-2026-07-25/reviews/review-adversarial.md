---
title: Adversarial Review — Architecture Spine (ZeusCode Role Routing)
target: ARCHITECTURE-SPINE.md
date: 2026-07-25
method: AD-compliant incompatible dual-builds (one layer down)
status: complete
focus:
  - pipeline enum ownership
  - Brief schema
  - FusionResult fields
  - merge vs Soft-Stop
  - Log Analyst skip vs Gate
  - curator vs Leader (AD-16)
  - Path vs pipeline
---

# Adversarial Review — Architecture Spine (Role Routing)

## Overall verdict

**CONDITIONAL FAIL — not CE-safe as written.**

Paradigm, layer table, and AD-19…AD-30 point the right product shape, but several ownership and contract holes remain. Two modules one layer under the spine can each obey every AD literally and still ship incompatible shared-data shapes, dual owners of `pipeline` / curator / Leader, and conflicting merge↔Gate↔Soft-Stop mutation paths.

Ship blockers for finalize: (1) single owner + mutation rules for `pipeline` vs Path, (2) curator≠Leader sticky/FusionResult contract under inherited AD-16, (3) Soft-Stop candidate set vs merged answer, (4) Log-skip vs Gate `log_report` semantics, (5) frozen Brief + FusionResult field-level handoff beyond name lists.

---

## Method note

For each hole: construct **Unit A** and **Unit B** one level below the spine layers. Both satisfy every AD as written. Their joint system is still incompatible. Each such pair = a hole the spine must close with a **new or tightened AD**.

Focus attacks: pipeline enum ownership · Brief schema · FusionResult fields · merge vs Soft-Stop · Log Analyst skip vs Gate · curator vs Leader (AD-16) · Path vs pipeline.

---

## Incompatible dual-builds (holes)

### Hole H1 — Pipeline enum ownership (who stamps final `pipeline`)

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/roles.py` | `fusion/pipeline.py` |
| Obeys | AD-21/22 (role table + hard v1 iff); sequence diagram “Roles → pipeline pick”; AD-28 field `pipeline` | AD-29 “`pipeline.py` owns v1/fallback/small orchestration”; AD-20 every request has a pipeline mode; AD-23 fallback_single behavior |
| Builds | Computes `pipeline` once from size × 2nd signal × mode × ≥950; stamps immutable `FusionResult.pipeline`; Execute must follow | Owns runtime: Architect Brief invalid / no ≥950 mid-flight → **rewrites** serving mode to `fallback_single` (or `small`) and stamps **final** `pipeline` as what actually ran |

**Clash:** Spine never names the **sole writer** of `FusionResult.pipeline` nor whether the field is *policy intent* or *final execution mode*. Onestack histograms and SM-6/SM-9 oracles disagree across builds while both stay AD-legal.

**Severity:** critical

**Close with:** Tighten AD-20/22/29 (or new AD-31): Policy/Roles compute `pipeline_intent` once; only `pipeline.py` may degrade per a closed degrade table; Onestack `pipeline` = **final** execution mode; optional `pipeline_intent` additive field required when intent ≠ final.

---

### Hole H2 — Path vs pipeline (two control planes, one Onestack `path`)

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/policy.py` | `fusion/pipeline.py` + `panel.py` |
| Obeys | Inherited AD-3/15 Path lattice; AD-11 mode clamps Path + pipeline eligibility; AD-20 Path still ∈ {FAST…FULL}; Role Routing must not choose RACE as large v1 target | AD-20 pipeline ∈ {small,v1,fallback_single}; AD-29 panel keeps Path executors; AD-28 requires both `pipeline` and (via AD-14) `path` |
| Builds | For large+power+2nd: sets `path=FULL`, `pipeline=v1`; panel Path executor skipped; escalate stays inside Role Routing verify budget (AD-25) — Path never mutates after Policy | Treats multi-role v1 as CASCADE-class control flow: starts `path=CASCADE`, may escalate Path toward FULL on Gate RED; Onestack `path` = final Path per parent AD-8; `pipeline` stays `v1` |

**Clash:** AD-20 forbids RACE-as-large default but never freezes **which Path value** accompanies each pipeline mode, nor whether Role Routing Verify may mutate Path. Parent AD-8 (final Path) + child pipeline orchestration = dual control planes. Kill→FAST+no v1 is clear; happy-path Path for `v1` / `fallback_single` / `small` is not.

**Severity:** critical

**Close with:** New/tightened AD: closed map `pipeline × size × mode → initial Path` (recommend: `v1`→`FULL` or dedicated non-RACE Path; `fallback_single`/`small`→`FAST` or `FULL` per size); Role Routing Verify **must not** change Path; only Soft-Stop/disaster/kill may alter serving Path; Onestack always emits both fields with that rule.

---

### Hole H3 — Curator vs Leader (inherited AD-16 dual mutators)

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/roles.py` (+ sticky write) | `fusion/panel.py` / `session.py` (`pick_leader`) |
| Obeys | AD-21 Curator = `argmax power_score(stack)`; inherited AD-16 “one runtime leader/**curator** pick path; sticky write at end”; AD-28 `curator_model` | Parent AD-16 literal: `pick_leader` (sticky hint → health → overflow); sticky = Leader that produced final answer; Soft-Stop partial persists that Leader |
| Builds | Equates curator ≡ Leader; `FusionResult.leader = curator_model`; sticky stores curator; overflow disabled under Role Routing (roles own pick) | Keeps Path `pick_leader` for sticky/health/overflow; curator is Role Routing-only for Brief/fallback; Soft-Stop artifact may be max-`power_score` doer ≠ curator ≠ Leader; sticky writes Path Leader |

**Clash:** Child spine glosses AD-16 as “leader/curator” without stating identity, pick order, or sticky payload. Two legal mutators of “who answers” / sticky. AD-21’s “prevents two owners of who answers” is violated in the joint system without either unit breaking an AD text.

**Severity:** critical

**Close with:** Tighten AD-16 (local supersession): Under Role Routing requests, **Curator is the runtime Leader**. `pick_leader` = curator resolution (AD-21) then health/overflow may swap only among stack models with same role eligibility; sticky `{leader, stack}` writes the model that produced the **user-visible** answer (including Soft-Stop pick); `FusionResult.leader` MUST equal final answering model; `curator_model` = pre-Soft-Stop curator pick (may differ only when Soft-Stop selects another artifact — and that case must be explicit).

---

### Hole H4 — Soft-Stop candidate set vs file-aware merge

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/merge.py` | `fusion/verify.py` (Soft-Stop, AD-25) |
| Obeys | AD-26 file-aware assemble; conflict → one strong call; no extra top merge when no conflict | AD-25 Soft-Stop: HTTP 200, body = max `power_score` artifact (tie→latest), `gate=RED`, `soft_stop=true` |
| Builds | After merge (or conflict-strong), `answer` = merged artifact; Soft-Stop may only fire if Gate still RED **after** escalate; candidate set = `{merged}` (+ optional strong-merge output) | Soft-Stop candidate set = raw doer/branch artifacts by `power_score`; **ignores** merge output (merge is “assemble,” not an artifact with power_score); can replace a successful merge with a single doer’s patch set |

**Clash:** Merge vs Soft-Stop mutation order and candidate membership undefined. User can receive either a file-assembled tree or a single high-power doer dump — both AD-25/26 legal. Billing/Onestack `soft_stop` + `answer` provenance diverge.

**Severity:** critical

**Close with:** Tighten AD-25 + AD-26: After Merge runs, Soft-Stop candidates = `{post-merge answer}` ∪ `{conflict-strong answer if any}` ∪ (only if merge skipped/failed-open) doer artifacts. Soft-Stop **must not** discard a successful merge in favor of a raw doer. Define merge-failure → Soft-Stop vs structured disaster.

---

### Hole H5 — Log Analyst skip vs Gate (`log_report` N/A)

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/log_analyst.py` | `fusion/verify.py` (Gate aggregate) |
| Obeys | AD-27 call only if (a) log-capable in stack ∧ (b) traceback/…/RED+runtime; skip ⇒ Gate without `log_report` (N/A); missing/`critical` → RED | AD-5/25 Gate authority; AD-28 `gate`, `gate_reasons`; Log never manages doers |
| Builds | Skip ⇒ **omit** `log_report` key; Gate treats absence as N/A and may GREEN if Mini GREEN. “missing/`critical` → RED” applies only when Log **was invoked** and JSON invalid / `critical=true` | Skip when (a) false even if (b) true. When Mini RED or runtime error-tail present, Gate requires `log_report` **or** synthesizes `gate_reasons+=log_unavailable` → RED. Interprets AD-27 “missing → RED” as missing report on error-ish requests |

**Clash:** N/A skip vs “missing means RED” unbound. Custom stacks without DeepSeek get GREEN (A) or sticky RED (B) on the same Mini-RED+traceback fixture. FR-5 / NFR-2 oracles non-portable.

**Severity:** high

**Close with:** Tighten AD-27: Three-valued Log status in FusionResult: `log_status ∈ {ran, skipped_no_model, skipped_no_signal, failed}`. Gate rules: `skipped_*` ⇒ N/A (does not force RED); `failed` or `ran∧critical` ⇒ RED; `ran∧¬critical` contributes reasons only. Forbid Gate from inventing Log RED when skipped_no_model.

---

### Hole H6 — Brief schema under-specified (doer/merge contract)

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/brief.py` | `fusion/pipeline.py` + `merge.py` |
| Obeys | AD-24 components≤3; keys `{id,role,goal,acceptance_one_liner,files_hint?}`; JSON validated before doers; Deferred says field-level polish later | AD-4/24 doer input = Brief + own component; AD-26 merge by Brief file paths/patches |
| Builds | Accepts `files_hint` absent; `role` free string matching requested doer labels; unknown keys stripped; validates length only | Requires `files_hint` non-empty for every component (else cannot file-merge); rejects Brief if `role` ∉ closed Roles set; on missing paths, synthesizes merge keys from doer fence headers |

**Clash:** Deferred “shape locked” contradicts optional `files_hint` vs merge-by-paths. Two Brief validators / two merge key strategies. Peer-isolation holds; **assemble** does not.

**Severity:** high

**Close with:** Tighten AD-24 (do not defer path keys): each component MUST include `files_hint: string[]` (min 1) **or** explicit `patch_only: true` with `target_paths[]`. `role` ∈ closed doer role set for v1. Reject/Soft-Stop policy on Brief validation failure named (no silent peer-path invention in merge).

---

### Hole H7 — FusionResult additive fields vs parent AD-14 shape

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/types.py` + `pipeline.py` | `routers/chat.py` Bill / Onestack builder |
| Obeys | AD-28 additive fields list; AD-14 single handoff; every LLM role call → `branches[]` with `role` | Parent AD-14 minimum fields (`path`, `leader`, `branches[]` with model/role/usage/billable_state, `answer`…); AD-8 Bill reads only FusionResult |
| Builds | Extends `branches[]` with Mini, Log, conflict-strong, Test Author FIX as roles; `models_by_role` map; omits legacy `complexity`/`phase` when Role Routing | Bills only rows with “user-visible content” roles; ignores Mini/Log branch rows for UsageLog grouping; requires parent `phase`/`complexity` or fills defaults; treats missing `soft_stop` as false without requiring key |

**Clash:** AD-28 lists field **names** but not nullability, enums, or whether verify/merge LLM calls are `branches[]`. Edge/Bill and Execute can diverge on charge coverage and Onestack role histograms — the exact failure parent H1 closed — reopened for Role Routing additives.

**Severity:** high

**Close with:** Tighten AD-28: normative FusionResult schema (required vs optional, enums for `pipeline`/`gate`/`size`/`task_kind`, `soft_stop: bool` always present, `roles[]` element shape, `branches[]` MUST include every billed upstream call including Mini/Log/strong-merge/judge). Bill MUST NOT drop `role`-tagged branches.

---

### Hole H8 — Conflict-strong merge vs escalate budget vs Soft-Stop

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/merge.py` | `fusion/verify.py` / `pipeline.py` |
| Obeys | AD-26 one strong-model call on conflict; ≥TEST_AUTHOR_MIN if present else curator | AD-25: Test Author FIX cycle ∉ escalate; Escalate/`judge_fix` ≤2; then Soft-Stop |
| Builds | Conflict-strong is **merge**, not escalate; does not increment `escalate_count`; may run even after escalate budget exhausted if Gate not yet terminal | Conflict-strong is a “strong call” ≈ judge/escalate class; consumes escalate budget; if budget 0 → skip strong merge → Soft-Stop among doers |

**Clash:** Same file conflict under exhausted escalate budget: A still merges strong; B Soft-Stops raw doers. AD-25/26 silent on budget class of merge-strong.

**Severity:** high

**Close with:** Tighten AD-25: closed budget classes `{test_author_fix, escalate_judge, merge_conflict_strong, soft_stop}`. `merge_conflict_strong` budget = **1** per request, independent of escalate ≤2. Soft-Stop only after merge attempt rules complete.

---

### Hole H9 — Second-signal / pipeline pick split across Policy vs Roles

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/policy.py` | `fusion/roles.py` |
| Obeys | FR-1 size/task_kind in Capability map → policy; AD-22 conditions; AD-3 classify | Sequence: Roles do “pipeline pick”; AD-21 stack/score gates; AD-22 ∃ model ≥950 |
| Builds | Owns size, task_kind, **second signal**, kill, mode clamp; emits `pipeline` eligibility flags; Roles only bind models | Owns second signal + AD-22 conjunction + curator; Policy only emits size/task_kind/Path; diverges on what counts as “second signal” (task_kind∈{feature,…} vs confidence vs lexicon hit) |

**Clash:** AD-22 says `second signal` without owner or closed definition. Two CE teams encode different triggers; both claim AD-22. Cost-bomb / under-trigger both “compliant.”

**Severity:** high

**Close with:** Tighten AD-22: name sole owner (recommend Policy emits `size`, `task_kind`, `second_signal: bool` + reason code from closed set); Roles only evaluate stack ≥950 ∧ mode; `pipeline.py` reads the conjunction — no third interpreter.

---

### Hole H10 — Gate without Log vs Soft-Stop body provenance on `fallback_single`

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/pipeline.py` (fallback_single) | `fusion/verify.py` |
| Obeys | AD-23 curator full answer → Mini → Log if AD-27 → Escalate ≤2 on RED | AD-25 Soft-Stop = max power_score **artifact**; AD-27 skip N/A |
| Builds | Single curator artifact only; Soft-Stop body = that artifact (only candidate); escalate re-asks curator | Treats Mini/judge drafts and any exploratory branch as artifacts; Soft-Stop may return judge_fix prose over curator answer by power_score tie-break “latest” |

**Clash:** On single-call fallback, “artifact” multiplicity undefined. Soft-Stop can legally swap in a RED judge narrative as the user body.

**Severity:** medium

**Close with:** Tighten AD-23+25: under `fallback_single` / `small`, Soft-Stop candidates ⊆ answer-producing roles (`curator` / doers), never Mini/Log/judge_fix text unless marked `answer_candidate=true`.

---

### Hole H11 — Sticky / product mode vs pipeline eligibility (AD-7/11/20)

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/session.py` sticky | `fusion/policy.py` mode clamp |
| Obeys | AD-7 sticky = leader/stack; **not** Path; **not** pipeline mode | AD-11 zeus.* > users.fusion_* > default; Product Mode clamps Path + pipeline eligibility; AD-20 pipeline set every request |
| Builds | Restores sticky stack; reuses prior `pipeline` as hint when size flaps around large threshold (sticky “continuity”) | Recomputes pipeline every request from AD-22; sticky must not influence pipeline |

**Clash:** AD-7 says sticky is not pipeline mode but does not forbid sticky **influencing** pipeline pick. Cost mode flaps vs sticky continuity both legal.

**Severity:** medium

**Close with:** Tighten AD-7/20: sticky MUST NOT store or hint `pipeline` / Path; every request recomputes pipeline from AD-22 inputs only.

---

## Attack matrix (focus areas)

| Focus | Hole IDs | Incompatibility class |
| --- | --- | --- |
| Pipeline enum ownership | H1, H9, H11 | Two writers / two triggers of `pipeline` |
| Path vs pipeline | H2, H11 | Dual control planes → Onestack `path` drift |
| Curator vs Leader (AD-16) | H3 | Two owners of one entity + sticky |
| Brief schema | H6 | Shared-data shape (doer ↔ merge) |
| FusionResult fields | H7, H1, H3 | Execute↔Bill DTO drift |
| Merge vs Soft-Stop | H4, H8, H10 | Conflicting state-mutation paths |
| Log skip vs Gate | H5 | Incompatible Gate interpretation |

---

## Recommended AD closures (finalize pack)

| ID | Action | Closes |
| --- | --- | --- |
| AD-20 | Freeze Path←pipeline initial map; Onestack emits both; no sticky hint | H2, H11 |
| AD-22 | Sole owner of `second_signal`; closed reason codes; intent vs final noted | H1, H9 |
| AD-16 (local) | Curator **is** Leader under Role Routing; sticky/FusionResult identity rules | H3 |
| AD-24 | Require path hints / patch_only; closed component.role; validation failure path | H6 |
| AD-25 | Soft-Stop candidate set post-merge; budget classes; answer_candidate roles | H4, H8, H10 |
| AD-26 | Merge-failure vs Soft-Stop; strong-merge budget = 1 independent | H4, H8 |
| AD-27 | `log_status` tri-state; Gate N/A vs RED table | H5 |
| AD-28 | Normative field schema + branches inclusion rules | H7 |
| AD-29/31 | Sole final writer of `pipeline` + closed degrade table | H1 |

---

## Non-holes (held under attack)

| Claim | Why it held |
| --- | --- |
| AD-19 public id `zeuscode` | Edge normalize + no mode-suffixed public ids — dual builds converge |
| AD-21 custom never auto-inject | Both units refuse extra models; no clash found |
| AD-9/22 kill → never v1 | Both refuse v1 under kill; Path FAST consistent |
| AD-6 no `fusion→routers` | Dependency direction intact in both builds |
| AD-30 TG-only modes / connect docs | Surface-level; no Execute dual-build clash |

---

## Finalize recommendation

Do **not** mark spine `status: adopted` until H1–H5 (critical/high ship blockers) are closed in the spine text — not only in companions/stories. H6–H8 should close in the same finalize pass; H9–H11 may ship as tightened sentences inside existing ADs.

**Verdict for parent finalize gate:** CONDITIONAL FAIL until AD closures above land in `ARCHITECTURE-SPINE.md`.
