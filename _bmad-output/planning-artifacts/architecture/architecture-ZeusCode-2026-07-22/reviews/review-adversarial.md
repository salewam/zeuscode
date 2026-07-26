---
title: Adversarial Review — Architecture Spine (Zeus Fusion)
target: ARCHITECTURE-SPINE.md
date: 2026-07-22
method: AD-compliant incompatible dual-builds + brownfield fact check
status: complete
---

# Adversarial Review — Architecture Spine

## Overall verdict

**CONDITIONAL FAIL — not CE-safe as written.**

The paradigm and most ADs point the right way, but several ownership and contract holes allow two modules one layer down to each obey every AD literally and still ship incompatible shared-data shapes, dual owners of Leader/Path/billing, and conflicting mutation paths. Brownfield facts (`chat.py → fusion → upstream`, no session today, `fast|full` vs Path enum) are acknowledged in the companion doc more than locked in the spine; the spine alone does not freeze the migration contracts CE needs.

Ship blockers: missing Execute→Bill DTO, dual Path/`fast|full` taxonomy, dual Leader mutation (sticky vs overflow), ambiguous post-Policy Path/`routed_by` mutation (esp. Shadow).

---

## Method note

For each hole: construct **Unit A** and **Unit B** one level below the spine layers. Both satisfy every AD as written. Their joint system is still incompatible. Each such pair = a hole the spine must close.

---

## Incompatible dual-builds (holes)

### Hole H1 — Execute→Bill shared-data shape (no frozen FusionResult)

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/panel.py` (Execute) | `routers/chat.py` (Bill / Edge) |
| Obeys | AD-2 Path enum; AD-6 chat wires only; AD-8 billable states on every upstream call; AD-10 `routers → fusion` | AD-6 Bill in chat; AD-8 Onestack `path` = final; AD-10 publish post-answer |
| Builds | Result DTO: `{path, policy_path, escalate_from?, routed_by, usages:[{model,tokens,billable_state,role}], choices}` — uppercase Paths | Keeps brownfield `_charge_amounts`: reads `onestack.agents` + legacy `mode` ∈ {`fast`,`full`,`ultra`}; maps CASCADE/RACE/FULL → `full`, FAST → `fast`; ignores `billable_state` (assumes completed if tokens > 0) |

**Clash:** No AD names fields, nesting, or the single handoff type between Execute and Bill. Both units are AD-legal; Onestack metrics and UsageLog diverge (unpaid `partial_stream` / wrong Path histograms).

**Severity:** critical

---

### Hole H2 — Dual taxonomy: `fast|full` vs `FAST|CASCADE|RACE|FULL`

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/policy.py` + facade | `fusion/panel.py` + catalog normalize |
| Obeys | AD-2 “legacy map per FR-37”; public id `zeus/fusion`; Consistency “uppercase in Onestack” | AD-2 serving Path ∈ {FAST…FULL}; AD-3 Path control flow |
| Builds | Internal `resolve_*` still returns stack `fast|full` and `routed_by` ∈ {`auto`,`forced`} (today’s `fusion.py`); maps to Path only at Onestack emit | Eradicates `fast|full` internally; `forced_fast` ≠ `legacy_fast_alias` at resolve time; never emits stack size as Path |

**Clash:** AD-2 forbids client Path churn but never forbids **internal** dual enums or requires a single canonical resolve output. Brownfield callers (`tg`, `me`, tests) keep `fast|full`; panel speaks Path — silent FR-37 / SM histogram corruption.

**Severity:** critical  
**Brownfield fact:** today `resolve_routing_ex` → `(fast|full, auto|forced, product_mode)`; Path enum does not exist in code.

---

### Hole H3 — Two owners of Leader (sticky vs overflow)

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/session.py` | `fusion/panel.py` (+ AD-12 overflow) |
| Obeys | AD-7 sticky owns `{leader, stack, phase_meta}`; sticky ≠ Path Phase | AD-12 overflow/long-context Leader selection; AD-4 Leader gets full context |
| Builds | After each success: overwrite sticky `leader` from last served Leader | Mid-request: overflow swaps Leader for this call only; does **not** write session (session “owns” sticky; panel “owns” runtime pick) |

**Clash:** Next turn restores sticky Leader ≠ overflow Leader that actually answered. Capability map splits FR-16 → session and FR-29 → policy/panel with no write-priority rule. Both ADs claim Leader authority without a single mutator.

**Severity:** critical

---

### Hole H4 — Conflicting Path / `routed_by` mutation (Policy vs Execute vs Shadow)

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/policy.py` | `fusion/panel.py` |
| Obeys | AD-3 fixed order; AD-9 Shadow logs candidate, serving path unchanged; AD-10 Policy ↛ Judge | AD-5/8 Execute may escalate (CASCADE/RACE); Onestack `path` = **final** execution Path; `routed_by` from closed PRD set |
| Builds | In Shadow: freezes serving Path = baseline decision; sets single `routed_by` = policy/legacy code; Execute must not change Path | Treats “serving path unchanged” as “initial Path only”; still runs CASCADE→FULL / RACE both-fail; overwrites `routed_by` to `cascade_escalate_*` / `race_*` |

**Clash:** AD-8 (final path) vs AD-9 (unchanged serving path) unresolved. Singular `routed_by` with two writers. Shadow baselines incomparable across implementations.

**Severity:** critical

---

### Hole H5 — Two owners of billable_state stamp

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/panel.py` / `verify.py` / `judge.py` (at each `upstream` call) | `routers/chat.py` on stream cancel / SSE close |
| Obeys | AD-8 every upstream/control call carries billable state; AD-6 fusion does not import routers | AD-6 Bill in chat; AD-8 cancelled_* states; Edge owns SSE wire |
| Builds | Stamps `completed` when upstream returns; never sees client disconnect after yield | On cancel, stamps `cancelled_with_usage` / `cancelled_no_tokens` on the **request** aggregate; leaves per-branch rows as `completed` |

**Clash:** No AD assigns the **sole** authority to finalize billable_state after cancel races. Double meaning of “call” (upstream hop vs user-visible completion). Unpaid / double-paid branches both AD-legal.

**Severity:** high

---

### Hole H6 — Aspect / Brief context ownership

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/verify.py` | `fusion/panel.py` (Brief builder) |
| Obeys | AD-5 Aspects before near-duplicate; AD-4 satellites = Brief only | AD-4 Leader full / satellites Brief; anti-bloat before Execute |
| Builds | Aspects are verifiers, not satellites → receive sanitized Leader context (else Aspect useless on code) | Anything non-Leader is satellite-class → Aspects get Brief only |

**Clash:** AD-4 defines Leader vs Satellites only; Aspects/Judge/Mini-Verifier roles unbound. Token bloat vs false Aspect fails — both compliant.

**Severity:** high

---

### Hole H7 — Session absent degrade (brownfield: no session today)

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/session.py` | Edge `chat.py` + TG callers |
| Obeys | AD-7 “prevents missing session store” → durable SQLAlchemy table always | AD-7 key = header / `zeus.session_id`; Consistency auth unchanged; TG may call `run_fusion` (AD-1) |
| Builds | Missing `session_id` → synthesize server id, always persist (store must exist and be used) | Missing header → sticky no-op; Path-only request (matches today’s zero-session traffic) |

**Clash:** AD-7 mandates a store and a key shape but not the **null-session** contract. One build invents sessions (sticky leaks across users if mis-keyed); the other never warms sticky — FR-16 vacuously “done.”

**Severity:** high  
**Brownfield fact:** no sticky/session module or `X-Zeus-Session-Id` handling in fusion path today.

---

### Hole H8 — Kill-Switch vs per-request `zeus.mode=full` precedence

| | Unit A | Unit B |
| --- | --- | --- |
| Module | flags / prefs clamp (AD-9) | `fusion/policy.py` (AD-11 + AD-3 table order) |
| Obeys | AD-9 Kill-Switch prefs clamp Path to FAST | AD-11 `zeus.*` > `users.fusion_*` > default; AD-3 Kill-Switch first in PRD table (via “policy first-match”) |
| Builds | Kill-Switch is account pref → loses to `zeus.mode=full` (AD-11 literal) | Kill-Switch is hard gate before forced/legacy (PRD FR-28 order) → FAST wins |

**Clash:** AD-9 and AD-11 collide; spine does not say Kill-Switch is outside normal pref precedence. Forced FULL under kill = safety theater.

**Severity:** high

---

### Hole H9 — Facade dual entry / second fusion stack risk

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/__init__.py` facade wrapping migrated package | Residual `app/fusion.py` monolith + `tg_miniapp` / `telegram_bot` direct imports |
| Obeys | AD-1 same Policy→Execute→Bill; AD-6 existing `fusion.py` may facade-reexport | AD-1 TG may call `iter_fusion`/`run_fusion`; AD-6 new logic under `fusion/` |
| Builds | All callers import `app.fusion` package; monolith deleted or thin reexport | During migration, bot keeps `from app.fusion import resolve_routing` (old 1↔3); chat uses package Path pipeline |

**Clash:** AD-6 allows facade “during migration” with no end-state or single import graph. Two Path semantics under one module name — exactly what AD-1 claims to prevent.

**Severity:** medium

---

### Hole H10 — `cost` helpers direction vs Bill ownership

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/panel.py` using “cost helpers” (AD-10) | `chat.py` `_bill_and_enrich` |
| Obeys | AD-10 `fusion → {…, cost helpers}`; AD-8 honest branches | AD-6/8 Bill orchestrated by fusion result in chat |
| Builds | Pre-computes per-branch ₽ into result; chat trusts fusion totals | Chat recomputes from tokens via `estimate_*`; ignores fusion money fields |

**Clash:** “cost helpers” without read/write ownership → divergent charged totals, both AD-legal.

**Severity:** medium

---

### Hole H11 — Observe / metrics write path unbound

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/metrics.py` | Edge logging in `chat.py` |
| Obeys | Observe layer in paradigm table; AD-13 baseline_id / eval | AD-8 Onestack fields; Consistency `trace_id` on every request |
| Builds | Histograms from in-process counters at Policy/Execute | Only UsageLog.meta JSON; no `fusion/metrics` calls |

**Clash:** AD-9 “incomparable Shadow baselines” needs metrics, but no AD requires a single emit path or schema for Shadow compare records.

**Severity:** medium

---

### Hole H12 — Product Mode clamp vs Execute Soft-Stop (RACE/simple)

| | Unit A | Unit B |
| --- | --- | --- |
| Module | `fusion/policy.py` (AD-11 clamp before Execute) | `fusion/panel.py` RACE both-fail |
| Obeys | AD-11 simple ∈ {FAST,CASCADE} unless forced/legacy full | AD-8 final path; PRD Soft-Stop / CASCADE terminal for simple |
| Builds | Never hands RACE to Execute under simple → R2 fixture unreachable in Execute | Policy may emit RACE then clamp is “Execute’s job”; Soft-Stop mutates to CASCADE with `race_soft_stop` |

**Clash:** Spine says clamp in Policy order (AD-3) but does not forbid Execute terminal Path changes under mode constraints. Two legal R2 implementations.

**Severity:** medium

---

## Brownfield fit vs known facts

| Fact | Spine stance | Fit |
| --- | --- | --- |
| `chat.py` → `fusion` → `upstream` | AD-6/10 + diagrams: panel/verify/judge → `upstream`; chat wires only | **Partial.** Direction for new Path logic is right. Today `chat.py` also imports `upstream` directly (non-fusion OK). Spine does not ban Edge→upstream for fusion disaster/failover leftovers — hole for “ad-hoc upstream from router.” |
| No session today | AD-7 adds SQLAlchemy sticky table + `session.py` in Structural Seed | **Acknowledged only in companion.** Spine treats store as required invariant without null-session / rollout AD → H7. |
| `fast|full` vs Path taxonomy | AD-2 + Consistency uppercase Paths; legacy map “per FR-37” | **Weak.** No AD freezes migration: internal enum, Onestack field rename (`mode`→`path`), closed `routed_by` replace `auto|forced`, or dual-write window. Highest brownfield breakage risk → H2. |

Additional brownfield gaps the spine under-specifies:

- Monolith `backend/app/fusion.py` is the entire fusion surface; package `fusion/` does not exist yet — migration ordering not an AD.
- Current Onestack uses agent list + mode strings; AD-8 fields are additive with no compatibility rule for old readers.
- `routed_by` today ∈ {`auto`,`forced`}; PRD closed set is large — spine Consistency cites closed set but does not bind emit ownership (H4).

---

## Findings (by severity)

### Critical

1. **H1 — No Execute→Bill / FusionResult contract** — Bill and Execute can disagree on field names, Path vs mode, and billable_state consumption while obeying AD-6/8/10.
2. **H2 — Dual taxonomy `fast|full` vs Path enum allowed** — AD-2 protects public id only; internal dual stack survives; brownfield default.
3. **H3 — Leader has two mutators** — AD-7 sticky vs AD-12 overflow; no write-priority / sticky update rule.
4. **H4 — Path/`routed_by` mutation conflict + Shadow ambiguity** — AD-8 final path vs AD-9 unchanged serving path; singular `routed_by` with Policy and Execute writers.

### High

5. **H5 — billable_state finalize authority split** between fusion upstream wrappers and chat cancel path.
6. **H6 — Aspect/Judge/Mini-Verifier context class undefined** under AD-4 Leader/Satellite binary.
7. **H7 — Null `session_id` behavior undefined** despite greenfield sticky store (no session in prod today).
8. **H8 — Kill-Switch vs AD-11 `zeus.*` precedence unresolved.**

### Medium

9. **H9 — Migration facade / dual import graph** under AD-1/AD-6 with no end-state.
10. **H10 — cost helper vs chat Bill ownership** for charged ₽.
11. **H11 — Observe/Shadow emit path not invariant.**
12. **H12 — simple-mode clamp vs Execute Soft-Stop terminal Path** underspecified.
13. **AD adoption inconsistency** — AD-6, AD-7, AD-9, AD-13 lack `[ADOPTED]` while peers have it; CE may treat them as optional.
14. **AD-6 “cost.py orchestrated by fusion result”** (paradigm Bill row) vs diagram `chat → cost` — narrative fork inside the spine itself.

### Low

15. **`session_id` ≤128 `[ASSUMPTION]`** in Consistency — not elevated to AD; two length/validation policies possible.
16. **Config: “panel model lists may stay code constants”** — baseline_id (AD-9/13) hash ingredients not listed as AD-mandatory inputs.
17. **Paradigm Bill layer “lives in chat + cost”** while Execute also produces usages — easy to mis-implement as Bill inside panel.
18. **FR-27 deferred** OK, but AD-1 “every zeus/fusion* completion” does not explicitly exclude future tool path forks.

---

## Suggested AD tightenings

### AD-2′ — Canonical Path + legacy projection

Add:

- Internal serving type is **only** `Path = FAST|CASCADE|RACE|FULL` after resolve; `fast|full` may exist solely as a **deprecated projection** for pre-migration callers, implemented in one function `path_to_legacy_stack(Path) -> fast|full`, not as a parallel control plane.
- `routed_by` at resolve time ∈ PRD closed set; `{auto, forced}` forbidden in new emits.
- Onestack field name is `path` (not `mode`); brownfield readers dual-read for one flagged release max.

### AD-7′ — Sticky ownership + null session

Add:

- If `session_id` absent/invalid → sticky **no-op** (no synthesize); Path/Leader selection proceeds without sticky (**brownfield default**).
- Single writer for sticky row: `session.py` API only; panel/policy call `session.get/put`, never SQL elsewhere.
- Sticky update rule: persist Leader/stack only from **final successful** serving Leader after Execute completes; overflow Leader **does** update sticky if it produced the user-visible answer (or explicitly: overflow is sticky-exempt — pick one).

### AD-8′ — FusionResult contract + bill finalize

Add frozen handoff (normative sketch):

```text
FusionResult:
  path, policy_path, escalate_from?, routed_by,  # path = final; routed_by = last decisive code
  phase, complexity, product_mode, leader, panel,
  branches: [{role, model, usage, billable_state, latency_ms}],
  answer / stream events
```

- Sole finalize of request-level cancel states: **Edge (chat)** after stream lifecycle; per-hop states: **Execute** at upstream return; chat must not re-mark per-hop `completed` → `cancelled_*` without an AD-defined merge function.
- Bill reads **only** `FusionResult.branches[*].billable_state` + tokens; no Path↔fast remap for charging.

### AD-9′ / AD-3′ — Shadow + post-Policy Path mutation

Add:

- **Initial Path** = Policy output (after MoR + clamps + Kill-Switch).
- **Final Path** = Execute terminal (escalates/Soft-Stop only via named transitions).
- Onestack: `path` = final; `policy_path` = initial; `routed_by` = **last** decisive code (document overwrite rule) **or** `routed_by_chain[]` — pick one.
- Shadow: baseline applies to **initial Path decision only**; Execute escalates still run unless flag `shadow_freeze_execute`; Shadow logs `(baseline_initial, candidate_initial, final_path)`.

### AD-4′ — Role → context class

| Role | Context |
| --- | --- |
| Leader | sanitized full client context |
| Panel satellites (A/B/C non-leader) | Brief only |
| Mini-Verifier / Aspect-Verifiers | candidate answer + Brief (+ structured error excerpts); **not** full client dump |
| Judge | rank inputs + Brief; not full client dump |

### AD-11′ — Kill-Switch outside pref order

- Kill-Switch (account or global) **overrides** per-request `zeus.mode` / legacy full aliases → FAST; record `routed_by=kill_switch`. Align with PRD FR-28 priority 1.

### AD-6′ — Migration end-state

- After migration milestone M: sole import surface `app.fusion` package; `fusion.py` monolith removed or 1-line reexport; CE Done check = no `resolve_mode`/`fast|full` control flow outside `path_to_legacy_stack`.
- Fusion request path: Edge **must not** call `upstream` for panel/verify/judge work (disaster fallback exception listed explicitly if needed).

### AD-12′ — Leader selection priority

Document ordered Leader choice:

1. Kill-Switch / forced single-model list  
2. Sticky Leader if fresh and in allowed stack  
3. Path-default Leader  
4. Overflow/long-context replace (and sticky rule from AD-7′)

### AD-10′ — Money ownership

- Token/usage assembly: Execute.  
- ₽ / UsageLog / balance: Edge Bill only.  
- `cost` helpers are pure functions; fusion may call for estimates/display but chat Bill is authoritative for charge.

### Meta

- Mark AD-6, AD-7, AD-9, AD-13 `[ADOPTED]` or explicitly `[PROVISIONAL]` with reason — silence reads as optional.
- Align paradigm Bill row text with AD-6 diagram (single story: chat bills from FusionResult).

---

## CE gate recommendation

Do **not** treat spine as build-substrate until at least **H1, H2, H3, H4** are closed by AD amendments (or a normative companion schema that ADs incorporate by reference). Remaining highs (H5–H8) should land in the same pass to avoid a second incompatible dual-build cycle during sticky/billing work.
