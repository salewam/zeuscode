---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - "_bmad-output/planning-artifacts/architecture"
  - "_bmad-output/implementation-artifacts/world-bench/swebench/task_card_single_crew_0_10_v3"
workflowType: 'research'
lastStep: 4
research_type: 'technical'
research_topic: 'Contract-closed multi-agent coding architecture for ZeusCode'
research_goals: 'Validate the proposed Opus contract, GPT implementation, DeepSeek diagnosis, Grok verification, and Opus reconciliation architecture against current industry systems, academic research, open-source coding agents, and practitioner evidence; identify what to keep, change, or remove.'
user_name: 'Money'
date: '2026-08-01'
web_research_enabled: true
source_verification: true
---

# ZeusCode — Новая архитектура

**Date:** 2026-08-01  
**Author:** Money  
**Research Type:** Technical

---

## Synthesized Target Architecture

### Additional Stakeholder Inputs

The final architecture must combine the external research above with three explicit product inputs:

1. **Contract-first development.** The supplied voice note defines a contract as the HLD and LLD interaction scheme between components, including all expected behavior branches. Coding before these interactions are described is considered unsafe.
2. **Parallelize the slow coding path.** Sol Ultra or another primary coding model may work continuously, but one unbounded sequential worker creates excessive critical-path latency. Independent coding work should be decomposed and executed concurrently.
3. **Prevent vibe coding.** Christian Mayer's *The Art of Clean Code* emphasizes reducing complexity, applying 80/20, building the smallest useful solution, avoiding premature optimization, following “do one thing well,” and removing unnecessary elements. These principles should constrain both the runtime and the code it generates. [Christian Mayer, *The Art of Clean Code*](https://library.tsilikin.ru/%D0%A2%D0%B5%D1%85%D0%BD%D0%B8%D0%BA%D0%B0/%D0%9F%D1%80%D0%BE%D0%B3%D1%80%D0%B0%D0%BC%D0%BC%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D0%B5/Desing/%D0%9C%D0%B0%D0%B9%D0%B5%D1%80%20%D0%9A%D1%80%D0%B8%D1%81%D1%82%D0%B8%D0%B0%D0%BD%20%D0%98%D1%81%D0%BA%D1%83%D1%81%D1%81%D1%82%D0%B2%D0%BE%20%D1%87%D0%B8%D1%81%D1%82%D0%BE%D0%B3%D0%BE%20%D0%BA%D0%BE%D0%B4%D0%B0.pdf)

These inputs refine, but do not contradict, the research conclusion. The target is a contract-closed deterministic graph with bounded parallel workers, not an open-ended swarm and not a mandatory four-model ceremony on every turn.

### Architecture Name and Core Invariant

The unified target architecture is:

> **ZeusCode Contract-Closed Parallel Crew:** every coding task begins with an explicit HLD/LLD contract, every independent work unit has exclusive ownership, every phase produces a typed artifact, and no task reaches `VERIFIED` until fresh evidence closes every required acceptance clause for the active workspace and patch.

```text
User request
  → Opus: TaskContract
  → parallel read-only discovery
       ├─ GPT/Sol: InspectionArtifact
       └─ Grok: Acceptance/Reproduction draft
  → Opus/server: WorkGraph
  → bounded parallel implementation
       ├─ GPT/Sol worker A: WorkUnit A
       ├─ GPT/Sol worker B: WorkUnit B
       └─ GPT/Sol worker C: WorkUnit C
  → deterministic merge barrier
  → parallel verification
       ├─ reproduction
       ├─ targeted tests
       ├─ regressions
       ├─ lint/type/build
       └─ security checks
  → DeepSeek only for fresh failures
  → Opus semantic reconciliation when required
  → server Evidence Gate
  → VERIFIED | UNVERIFIED | BLOCKED | FAILED
```

The graph is adaptive because optional nodes activate from typed state and machine evidence. It is not an LLM router: models do not choose arbitrary next steps.

### HLD: Components and Authority

| Component | Owns | Must not own |
|---|---|---|
| ZeusCode API | authentication, billing, task/session binding, limits | client filesystem and shell |
| Contract Manager | versioned task contract, acceptance clauses, scope | execution evidence |
| Crew Orchestrator | phase state, WorkGraph, role calls, retry budgets | inventing successful outcomes |
| Opus 4.6 | contract, decomposition, exceptional semantic reconciliation | production edits or terminal truth |
| GPT-5.4 / Sol Ultra pool | repository inspection and production implementation | acceptance weakening or self-verification |
| Grok 4.5 | reproduction, acceptance design, final-diff verification | default production-code ownership |
| DeepSeek V3.2 | one bounded diagnosis for one fresh failure | code edits, tests, phase or gate authority |
| Client hands | files, git, shell, tests, LSP, isolated worktrees | model routing, billing, server state |
| Merge Coordinator | write-set reservations, patch ordering, conflict detection | semantic acceptance |
| Evidence Gate | workspace-bound receipts and terminal state | model-provided exit codes or green claims |
| Event Ledger | immutable events, artifact hashes, actual role telemetry | mutable hidden narrative state |

The existing product boundary remains unchanged: ZeusCode is the brain and billing layer; Cursor or another client is the hands.

### LLD: Server-Owned Phase Machine

```text
CONTRACTING
  → INSPECTING
  → REPRODUCING
  → PLANNING_WORK
  → IMPLEMENTING
  → MERGING
  → VERIFYING
  → RECONCILING
  → VERIFIED | UNVERIFIED | BLOCKED | FAILED

Fresh execution failure:
  IMPLEMENTING | MERGING | VERIFYING
    → DIAGNOSING
    → previous actionable phase

No measurable progress:
  any non-terminal phase
    → STAGNANT
    → revised WorkGraph | one isolated candidate branch | BLOCKED | FAILED
```

Transitions are deterministic predicates over validated artifacts and trusted evidence. A model may propose an artifact but may not directly advance the phase. Terminal states are irreversible for a task version; changed user requirements create a new version.

### Phase Behavior

#### 1. CONTRACTING

Opus creates a compact `TaskContract` for every coding task:

- observable goal and motivation;
- included and excluded scope;
- public compatibility and security constraints;
- independently verifiable acceptance clauses;
- expected evidence kind for each clause;
- open questions and risk level.

For serious public API, security, migration, serialization, billing, or multi-module work:

```text
Opus draft → one strong critique pass → Opus final contract
```

The critique is not a permanent ceremony for trivial edits. If material ambiguity remains, the phase terminates as `BLOCKED` with concrete questions rather than allowing models to guess.

#### 2. INSPECTING AND REPRODUCING

Two read-only activities may overlap:

- GPT/Sol localizes relevant files, symbols, execution paths, and root-cause hypotheses.
- Grok derives acceptance assertions and a reproduction design from the contract.

Production mutation is prohibited until inspection identifies evidence-backed edit candidates. For bug fixes, the reproduction must either fail on the original state or explicitly record why reproduction is unavailable.

#### 3. PLANNING_WORK

Opus and deterministic validation turn the contract and inspection into a `WorkGraph`. Each `WorkUnit` declares:

- acceptance clauses;
- dependencies;
- read set;
- exclusive write set;
- owner role;
- expected artifact;
- verification requirements;
- turn and wall-clock budgets.

The scheduler rejects dependency cycles, missing acceptance ownership, overlapping parallel write sets, and undeclared public-contract dependencies.

#### 4. IMPLEMENTING

The primary coder is a bounded pool of GPT/Sol workers rather than one endless Sol Ultra trajectory. Each worker receives only:

- the stable TaskContract;
- its WorkUnit;
- relevant inspection/reproduction artifacts;
- permitted paths;
- current base-tree hash;
- exact completion and verification obligations.

Workers execute in isolated client worktrees or patch buffers. They do not receive the full raw transcript by default.

#### 5. MERGING

The merge barrier:

1. checks that every patch targets the declared base;
2. confirms changed paths are inside the reserved write set;
3. rejects modifications to frozen acceptance assertions;
4. orders patches deterministically;
5. detects textual and public-contract conflicts;
6. produces a new combined patch hash;
7. invalidates all pre-merge verification.

Individually green worker branches are not proof that the merged result is correct.

#### 6. VERIFYING

Independent checks run concurrently where the environment permits:

- fail-before/pass-after reproduction;
- targeted tests for changed behavior;
- relevant regressions;
- lint, type and build checks;
- security checks for sensitive changes.

Grok independently inspects the final merged diff and maps every acceptance clause to evidence. Generic test success cannot close an untested public-signature, forwarding, compatibility, or end-to-end clause.

#### 7. DIAGNOSING

DeepSeek activates only for a fresh failure receipt containing:

- command, working directory, exit code and timeout;
- bounded sanitized output and raw-output hash;
- workspace, sequence and current patch hash;
- relevant acceptance clause and changed symbols.

It returns one classification, root-cause explanation and concrete next action. The diagnosis expires after the next mutation or successful rerun. Repeated identical evidence does not trigger another diagnosis.

#### 8. RECONCILING

Opus maps the original contract to the final artifacts and machine evidence for serious, degraded, ambiguous, or semantically sensitive work. It may recommend accept, revise or block. The server still computes terminal truth.

### Typed Artifact Contracts

All artifacts use a common immutable envelope:

```json
{
  "schema": "zeus.<artifact>.v1",
  "task_id": "server-owned id",
  "task_version": 1,
  "artifact_id": "unique id",
  "producer_role": "actual role",
  "producer_model": "actual model id",
  "input_hashes": ["sha256:..."],
  "created_at": "RFC3339",
  "payload": {}
}
```

Invalid structured output receives one bounded schema-repair attempt. It is never silently converted from approximate prose into a trusted artifact.

#### `TaskContract`

Producer: Opus. Consumer: every later phase.

```json
{
  "goal": "observable outcome",
  "motivation": "why it matters",
  "scope_in": ["allowed behavior or path"],
  "scope_out": ["explicit exclusion"],
  "constraints": ["compatibility, security, cost"],
  "acceptance": [
    {
      "id": "AC-1",
      "claim": "one verifiable requirement",
      "evidence_kind": "test|lint|build|inspection",
      "required": true
    }
  ],
  "open_questions": [],
  "risk": "low|medium|high"
}
```

#### `InspectionArtifact`

Producer: GPT/Sol. Consumer: Grok, Opus and implementers.

```json
{
  "relevant_paths": ["relative/path.py"],
  "symbols": ["module.symbol"],
  "execution_path": ["entry → service → output"],
  "root_cause_hypotheses": [
    {"claim": "bounded hypothesis", "support": ["path:line", "evidence-id"]}
  ],
  "unknowns": [],
  "edit_candidates": ["relative/path.py"]
}
```

#### `ReproductionArtifact`

Producer: Grok. Consumer: WorkGraph, implementers and verification.

```json
{
  "acceptance_ids": ["AC-1"],
  "command": "direct allowlisted command",
  "expected_before_fix": "failure signature",
  "expected_after_fix": "success condition",
  "test_paths": ["relative/test_path.py"],
  "frozen_assertions_hash": "sha256:...",
  "reproducible": true,
  "reason_if_not": ""
}
```

#### `WorkGraph`

Producer: Opus proposal plus server validation. Consumer: scheduler.

```json
{
  "units": [
    {
      "id": "WU-1",
      "acceptance_ids": ["AC-1"],
      "depends_on": [],
      "read_set": ["backend/app/..."],
      "write_set": ["backend/app/file.py"],
      "owner_role": "implementer",
      "verification_ids": ["V-1"],
      "budget": {"turns": 4, "seconds": 300}
    }
  ]
}
```

#### `PatchArtifact`

Producer: GPT/Sol worker. Consumer: merge coordinator.

```json
{
  "work_unit_id": "WU-1",
  "base_tree_hash": "sha256:...",
  "patch_hash": "sha256:...",
  "changed_paths": ["relative/path.py"],
  "acceptance_ids": ["AC-1"],
  "assumptions": [],
  "known_limitations": []
}
```

#### `DiagnosisArtifact`

Producer: DeepSeek. Consumer: responsible implementer.

```json
{
  "failure_evidence_id": "EV-...",
  "classification": "code|test|environment|contract|unknown",
  "root_cause": "bounded explanation",
  "recommended_next_action": "single concrete action",
  "confidence": 0.0
}
```

#### `VerificationArtifact`

Producer: machine Evidence Gate plus Grok clause assessment. Consumer: reconciliation and terminal gate.

```json
{
  "workspace_id": "bound client workspace",
  "patch_hash": "sha256:...",
  "checks": [
    {
      "id": "V-1",
      "acceptance_ids": ["AC-1"],
      "command": "exact command",
      "exit_code": 0,
      "evidence_id": "EV-...",
      "verdict": "pass|fail|not_run"
    }
  ],
  "clause_verdicts": [
    {"acceptance_id": "AC-1", "verdict": "satisfied|failed|unproven"}
  ]
}
```

#### `ReconciliationVerdict`

Producer: Opus when required. Consumer: server terminal gate.

```json
{
  "task_version": 1,
  "patch_hash": "sha256:...",
  "acceptance_map": [
    {
      "acceptance_id": "AC-1",
      "evidence_ids": ["EV-..."],
      "assessment": "met|not_met|unclear"
    }
  ],
  "semantic_risks": [],
  "recommendation": "accept|revise|block"
}
```

### Safe Parallelization Rules

Parallelism is allowed only when it shortens the critical path without weakening evidence:

1. dependencies are satisfied;
2. normalized write sets do not overlap;
3. workers do not concurrently change a shared public contract;
4. each worker uses an isolated worktree or patch buffer;
5. each result is tied to the same declared base hash;
6. merge order is deterministic;
7. the combined patch crosses a fresh verification barrier.

Isolation prevents workers from overwriting one another's filesystem. Write-set validation prevents known ownership races before launch. The merge barrier catches textual and shared-contract conflicts. Post-merge checks establish the behavior of the combined result.

Good parallel targets:

- read-only repository localization and acceptance design;
- independent modules with explicit interfaces;
- separate implementation WorkUnits with disjoint ownership;
- lint, tests, builds and security checks;
- one fresh-failure diagnosis while unrelated checks finish.

Keep serial:

- contract publication;
- overlapping or same-file edits;
- public-contract changes consumed by another active unit;
- merge commitment;
- terminal evidence decision;
- semantic reconciliation.

Initial limits:

- maximum three concurrent implementation units;
- maximum four concurrent verification commands;
- one schema-repair retry per unchanged artifact hash;
- one diagnosis per fresh failure hash;
- candidate-patch competition only after stagnation or genuine ambiguity.

The objective is lower wall-clock critical-path latency, not continuous utilization of every model.

### Deterministic Runtime Hooks

Hooks are internal event subscribers, not additional model personalities. They consume immutable event envelopes, are idempotent by `(task_id, task_version, event_id, hook_name)`, and cannot rewrite history.

| Event | Required behavior |
|---|---|
| `task.created` | bind identity and create task version |
| `contract.proposed` | validate schema, ambiguity, scope and acceptance clauses |
| `phase.entered` | enforce allowed predecessor and phase budget |
| `work_graph.proposed` | reject cycles, uncovered clauses and unsafe parallel ownership |
| `work_unit.started` | reserve write set and deduplicate role call |
| `tool.completed` | sanitize and bind evidence to workspace, patch and sequence |
| `tool.failed` | emit one fresh-failure event |
| `patch.changed` | invalidate old verification and diagnosis |
| `merge.completed` | publish combined patch hash and require fresh verification |
| `verification.completed` | map evidence to acceptance clauses |
| `stagnation.detected` | stop repeated probes; revise graph, branch once or terminate |
| `terminal.requested` | derive status from evidence and ignore model self-certification |
| `task.terminal` | seal task version and write truthful telemetry |

Example:

```text
patch.changed
  → invalidate previous GREEN
  → expire previous DeepSeek diagnosis
  → advance evidence sequence
  → require VERIFYING
```

This transition is deterministic and does not require another LLM call.

### Anti-Vibe Coding Invariants

The clean-code input becomes enforceable architecture:

1. no production mutation before a valid contract and inspection artifact;
2. no parallel writes without explicit non-overlapping ownership;
3. no acceptance claim without an evidence ID;
4. no `VERIFIED` inferred from model prose or output text alone;
5. no old green evidence after the patch hash changes;
6. no frozen acceptance-test modification by an implementer;
7. no role listed in telemetry unless it actually produced a valid artifact;
8. no unlimited loop; every phase has time, call and no-progress budgets;
9. no full-transcript replay when bounded artifacts are sufficient;
10. no new framework, database or abstraction without measured need;
11. no premature optimization outside the measured critical path;
12. every component does one job and exposes one typed boundary.

These rules implement Mayer's simplicity, 80/20, minimal viable scope, “do one thing well,” and anti-premature-optimization principles at the runtime level rather than merely asking models to “write clean code.”

### Behavior Matrix

| Situation | Required behavior |
|---|---|
| Trivial isolated edit | compact contract, one implementer, focused deterministic verification |
| Independent multi-file work | WorkGraph shards, isolated parallel workers, deterministic merge |
| Two units need the same file | serialize or redefine ownership; never race |
| Bug cannot be reproduced | record `reproducible=false`; require alternate evidence or remain `UNVERIFIED` |
| Fresh failed check | one DeepSeek diagnosis for that evidence hash |
| Same failure repeats without patch change | do not rediagnose; enter stagnation policy |
| Grok unavailable | run deterministic checks; semantic clauses remain `unproven` |
| Model returns invalid structured output | one repair attempt, then degrade or fail the role |
| Green result belongs to old patch/workspace | reject as stale evidence |
| Submit retry budget exhausted | preserve patch as `UNVERIFIED`; never paint fail-open green |
| User changes requirements | create task version N+1 and invalidate old graph/evidence |
| Context compacts | restore from artifacts and event ledger, not prose summary |

### Truthful Terminal States

- `VERIFIED`: every required clause has fresh passing evidence for the current merged patch and workspace.
- `UNVERIFIED`: a patch exists, but evidence is absent, stale, incomplete or semantically insufficient.
- `BLOCKED`: required user input, permission, dependency or environment is unavailable.
- `FAILED`: phase budgets are exhausted or the contract cannot be satisfied.

Fail-open may produce only `UNVERIFIED`. It may never produce a green gate.

### Performance Strategy

The expected speedup comes from reducing critical-path work:

- parallel read-only discovery and acceptance design;
- two or three isolated implementation units only when ownership is independent;
- parallel post-merge checks;
- stable TaskContract prompt prefixes and provider cache;
- artifact handoffs instead of full transcripts;
- no repeated DeepSeek call for stale failures;
- no Opus narration after every tool action;
- immediate termination at a valid terminal state;
- one bounded stagnation branch rather than endless probing.

The architecture does not promise a 2× improvement before measurement. It defines separate measurements for:

- phase latency;
- end-to-end wall time;
- worker utilization and merge conflicts;
- cache-hit percentage;
- tokens and cost per closed acceptance clause;
- false-green rate;
- official SWE-bench resolution rate.

Parallelism is accepted only if wall-clock time improves while false-green rate and official resolution quality do not regress.

### Worked Example

Task: “When the submit gate blocks a patch, the client must still receive a valid tool call.”

1. Opus publishes:
   - `AC-1`: blocked submit returns one client-compatible bash tool call;
   - `AC-2`: three failed verification attempts may release the patch only as `UNVERIFIED`;
   - `AC-3`: model prose cannot set the gate green.
2. GPT/Sol inspection identifies the submit interception, evidence collector and OpenAI tool protocol tests.
3. Grok freezes a reproduction that submits without fresh evidence and validates the returned `tool_calls` schema.
4. The WorkGraph creates separate units for gate behavior and telemetry only if their write sets are disjoint.
5. Workers return patches against the same base hash. The server validates ownership and merges them in declared order.
6. The merge event invalidates every pre-merge test result.
7. Grok runs the frozen reproduction and focused regression checks on the merged patch.
8. Opus maps semantic clauses to evidence if the task is degraded or serious.
9. The server emits `VERIFIED` only when every required clause is fresh and closed; otherwise it emits `UNVERIFIED`.

The example is contract-closed because expected behavior, ownership, transitions, error paths and proof obligations are explicit before implementation begins.

### Adoption Order

This section is an architecture and research synthesis, not a claim that Runtime v4 is already implemented.

1. Introduce typed artifacts and `CrewSession v4` behind a feature flag.
2. Add workspace-, sequence- and patch-bound evidence receipts.
3. Make `VERIFIED` strict and rename fail-open completion to `UNVERIFIED`.
4. Add phase-owned Grok reproduction/verification, DeepSeek fresh-failure diagnosis and optional Opus reconciliation.
5. Add terminal and stagnation controls; remove repeated completion loops.
6. Prove serial correctness and truthful actual-role telemetry.
7. Add WorkGraph parallelism with isolated worktrees and write-set reservations.
8. Run focused tests, full regression, SWE-bench 0:5, and only then SWE-bench 0:10 after the quality threshold holds.

The implementation should preserve the current OpenAI-compatible `/v1` boundary and avoid introducing a new orchestration framework, graph database, browser farm or server-side tool loop.

### Final Unified Verdict

The requested architecture is not “four models thinking together all the time.” It is one contract-closed coding system:

- Opus defines and reconciles;
- GPT/Sol investigates and implements through bounded workers;
- Grok independently reproduces and verifies;
- DeepSeek diagnoses only fresh failures;
- deterministic code owns transitions, hooks, merge safety, evidence and terminal truth;
- parallelism is applied only to independent work;
- clean-code simplicity limits ceremony and new abstractions.

This structure incorporates the stakeholder's HLD/LLD contract requirement, the request to parallelize slow Sol Ultra coding, the requested hooks, the anti-vibe coding concern, Mayer's simplicity principles, the observed SWE-bench failures, and the external architecture research into one coherent target design.

## Migration from the Current ZeusCode Architecture

### Migration Principle: Replace, Do Not Layer

The new runtime must not be pasted into the existing `_monolith.py` as another collection of branches. That would leave two task models, two gates, two role selectors and two definitions of completion.

The migration follows an extraction-and-replacement rule:

> First extract the currently working bootstrap and incremental paths from the monolith. Then introduce one new owner for each contract, phase and gate. Cut traffic over behind a feature flag. Delete the displaced implementation immediately after its verification gate passes.

Temporary compatibility is permitted only when it has:

- one named owner;
- one removal condition;
- one removal phase;
- no authority to create a second source of truth.

### What Exists Today

The active coding path is already narrower than the physical code suggests:

```text
chat.py
  → fusion.iter_fusion
  → select_crew
  → pick_pipeline
  → Task Card bootstrap or incremental tool loop
  → pre-submit gate
  → FusionResult
  → billing and sticky session
```

The current hot path ends before a large legacy tail in `_monolith.py`. Approximately 1,300 lines containing old CASCADE/RACE/FULL, UI crew and pipeline-v1 execution remain physically present after a fail-closed `RuntimeError`, even though normal single-crew traffic does not reach them.

The first architectural improvement is therefore deletion and extraction, not adding parallel agents.

### Preserve, Evolve, Remove

#### Preserve

These boundaries are already correct and should not be rewritten:

| Existing component | Why it remains |
|---|---|
| `/v1` OpenAI-compatible API and tool streaming in `routers/chat.py` | External Cursor/OpenCode contract |
| `FusionResult`, `BranchUsage` and billable-state envelope | Billing and response compatibility |
| `upstream.py` provider communication | Existing provider and cache integration |
| API-key identity, automatic tool-session binding and sticky DB session | Tenant isolation and continuity |
| Client-hands boundary | Files, shell, git, LSP and tests stay on the client |
| Prompt cache ordering and stable prefixes | Existing latency and cost optimization |
| Explicit web-research path | Orthogonal to the coding crew |
| UsageLog, balance charging and cost accounting | Must not drift during runtime migration |

#### Evolve in Place

| Current owner | Evolution |
|---|---|
| `task_card.py` | `TaskCard` becomes the compatibility view of a richer `TaskContract` |
| `crew.py` | `CrewSession v3` gains a backward-compatible reader and writes `CrewSession v4` with explicit phase and artifact references |
| `verify.py` | Current evidence parsing evolves into workspace-, sequence- and patch-bound receipts |
| `project_memory.py` | Stores typed artifact references instead of becoming another orchestration engine |
| `session.py` | Persists v4 phase state inside existing sticky `phase_meta` |
| `panel.py` | Remains the bounded model-call adapter; later supports WorkUnit workers |
| `log_analyst.py` | Produces `DiagnosisArtifact` for fresh failures only |
| `merge.py` | Becomes the deterministic merge barrier for WorkUnits |
| `metrics.py` | Records phase, artifact and actual-role events |

#### Remove After Cutover

| Legacy or duplicate element | Removal reason |
|---|---|
| Unreachable `_monolith.py` tail after the terminal `RuntimeError` | Dead CASCADE/RACE/FULL and duplicate execution logic |
| Hot-path references to `execute_cascade`, `execute_race`, `execute_full` | Legacy route executors are not part of the new graph |
| `pipeline_v1.execute_pipeline_v1` as a product execution path | Replaced by the phase orchestrator |
| Dynamic path policy and regex task labels as execution authority | Phase transitions use contracts and evidence |
| Duplicate role assignment tables | One canonical Opus/GPT-Sol/Grok/DeepSeek roster |
| `plan_digest` as a second task definition | `TaskContract` becomes the single durable source |
| GREEN/RED fail-open semantics | Replaced by strict terminal states |
| Stale compatibility labels such as physical `CASCADE` for single-crew execution | Replaced after clients adopt phase and terminal telemetry |

Studio and its separate `evidence.py` subsystem are not silently merged into the coding runtime. Studio is already deprecated and should be removed through its own compatibility decision.

### Target Code Structure

The new architecture should not become another large file. Each module owns one responsibility:

```text
backend/app/fusion/
  runtime/
    route.py          # request → current phase
    bootstrap.py      # initial contract bootstrap
    incremental.py    # one client tool-result turn
    pack.py           # FusionResult assembly

  contract.py         # TaskContract and AcceptanceClause
  artifacts.py        # typed immutable role artifacts
  phase.py            # CrewPhase and pure transition predicates
  orchestrator.py     # coordinates phases; no provider or billing code
  workgraph.py        # WorkGraph, WorkUnit, dependency/write-set validation
  evidence_receipt.py # trusted client evidence schema and freshness
  merge.py            # deterministic patch merge barrier
```

Existing provider calls, billing, sticky persistence and client-hands code remain outside these modules.

`_monolith.py` becomes a temporary thin compatibility delegator and then is reduced or removed. It must not receive new phase logic.

### Migration Phases

#### Phase 0 — Baseline and Dependency Freeze

Before refactoring:

- capture focused/full test results;
- record SWE-bench 0:5 baseline, latency, cost and false-green rate;
- identify all imports and test patches targeting `_monolith`;
- freeze public `/v1`, billing and `FusionResult` contracts;
- add no new behavior.

Exit condition: the baseline is reproducible and every compatibility dependency has an owner.

#### Phase 1 — Extract the Current Working Runtime

Move current behavior without changing it:

- bootstrap logic → `runtime/bootstrap.py`;
- incremental tool-loop logic → `runtime/incremental.py`;
- request/phase preparation → `runtime/route.py`;
- result assembly → `runtime/pack.py`.

`iter_fusion` remains the public entry but delegates to extracted modules.

Exit conditions:

- focused and full regression tests match baseline;
- billing fixture totals are unchanged;
- `_monolith.py` is substantially smaller;
- no new model calls or changed routing behavior.

This phase prevents the new architecture from being built on top of a tangled monolith.

#### Phase 2 — Typed Contracts and CrewSession v4

Add behind `ZEUS_CONTRACT_CLOSED`:

- `TaskContract` and `AcceptanceClause`;
- typed role artifacts;
- `CrewPhase`;
- pure transition predicates;
- `CrewSession v4`.

Migration behavior:

- v3 sticky sessions remain readable;
- flag-enabled turns write v4;
- `TaskCard` is rendered from `TaskContract`, not maintained independently;
- `plan_digest` becomes a temporary compatibility projection.

Exit condition: one task can replay from persisted artifacts without relying on the raw transcript.

#### Phase 3 — Serial Contract-Closed Runtime

Implement the full phase machine with one coder first:

```text
CONTRACTING
→ INSPECTING
→ REPRODUCING
→ PLANNING_WORK
→ IMPLEMENTING
→ VERIFYING
→ terminal
```

Parallel coding is deliberately postponed. This proves that contracts, evidence and transitions are correct before adding concurrency.

Exit conditions:

- every transition is covered by deterministic tests;
- invalid model output cannot advance the phase;
- a no-diff/no-evidence turn terminates or requests one exact action;
- one-task SWE replay is no worse than baseline.

#### Phase 4 — Strict Evidence and Honest Terminal States

Introduce evidence receipts containing:

- workspace and task identity;
- patch hash and mutation sequence;
- command and working directory;
- exit code and timeout;
- output hash and bounded sanitized digest;
- acceptance clauses covered.

Replace gate semantics:

- fresh complete evidence → `VERIFIED`;
- patch with insufficient evidence → `UNVERIFIED`;
- unavailable external requirement → `BLOCKED`;
- exhausted or unsatisfied contract → `FAILED`.

Fail-open may preserve a patch only as `UNVERIFIED`.

Exit conditions:

- old-workspace and old-patch green evidence is rejected;
- model prose cannot set terminal truth;
- every required acceptance clause must be closed independently.

#### Phase 5 — Correct Model Roles

Activate role nodes at phase boundaries:

- Opus creates the contract and reconciles only serious/degraded work;
- GPT/Sol inspects and implements;
- Grok owns reproduction and final-diff verification;
- DeepSeek receives one fresh failure bundle per evidence hash.

Exit conditions:

- telemetry records only models that actually produced valid artifacts;
- DeepSeek cannot edit or set gates;
- implementers cannot modify frozen acceptance assertions;
- unavailable roles degrade honestly rather than being silently substituted.

#### Phase 6 — Parallel Read-Only Work

First parallelize only safe operations:

```text
GPT/Sol inspection ║ Grok acceptance/reproduction design
```

No production write occurs until both artifacts are validated or one explicitly degrades.

Exit conditions:

- branch budgets remain bounded;
- latency improves;
- artifacts do not contradict the final contract;
- quality and false-green rate do not regress.

#### Phase 7 — WorkGraph Parallel Implementation

Only after serial correctness is proven:

- generate WorkUnits with dependencies and exclusive write sets;
- launch up to three isolated GPT/Sol workers;
- use client worktrees or patch buffers;
- reserve ownership before launch;
- merge deterministically;
- invalidate all pre-merge verification;
- verify the combined patch.

If write sets overlap or one unit changes a contract consumed by another, the scheduler serializes them.

Exit conditions:

- conflict and dependency tests pass;
- no same-file concurrent writes;
- merged-patch verification is mandatory;
- SWE-bench 0:5 meets the quality threshold;
- wall-clock latency improves without additional false greens.

#### Phase 8 — Cutover

Run old and new decision logic in shadow mode first, but allow only one path to execute tools and incur billing. Compare:

- phase decisions;
- actual role participation;
- test-command selection;
- terminal outcomes;
- latency and cost.

Then:

1. enable v4 for internal smoke traffic;
2. enable for benchmark traffic;
3. enable for a small production percentage;
4. make v4 default;
5. retain a time-limited rollback flag.

Exit condition: the new runtime meets test, billing, latency and SWE thresholds with no protocol regression.

#### Phase 9 — Mandatory Deletion

This is part of the migration, not optional cleanup:

- delete the unreachable `_monolith.py` tail;
- delete legacy CASCADE/RACE/FULL executors from the product path;
- retire pipeline-v1 and UI-crew execution paths or move still-needed UI functionality to an explicit product module;
- remove regex routing authority;
- remove duplicate role tables;
- remove v3 writes, `plan_digest` mirroring and GREEN/RED compatibility after their TTL;
- remove the feature flag and rollback branch after the stability window;
- update architecture tests so deleted paths cannot return.

Exit condition: each runtime concept has exactly one owner and searches show no live import of retired executors.

### Compatibility Shims and Their Expiration

| Temporary shim | Purpose | Mandatory deletion gate |
|---|---|---|
| `iter_fusion` / `run_fusion` facade | Preserve external imports | All internal callers delegate to `orchestrator` |
| v3/v4 `CrewSession.from_dict` | Drain sticky sessions safely | v3 sticky TTL expires |
| `TaskCard` view over `TaskContract` | Preserve current prompt/client fields | Clients consume contract version |
| `plan_digest` projection | Preserve prompt cache compatibility | Stable prefix reads TaskContract directly |
| GREEN/RED mapping | Preserve telemetry during transition | All consumers accept terminal states |
| Legacy role aliases | Preserve existing dashboards | Canonical role telemetry deployed |
| `ZEUS_CONTRACT_CLOSED` flag | Safe cutover and rollback | Stability window passes |

No shim may select a model, advance a phase or certify evidence. Compatibility code translates shapes only.

### File-Level Change Map

#### New

```text
backend/app/fusion/runtime/__init__.py
backend/app/fusion/runtime/route.py
backend/app/fusion/runtime/bootstrap.py
backend/app/fusion/runtime/incremental.py
backend/app/fusion/runtime/pack.py
backend/app/fusion/contract.py
backend/app/fusion/artifacts.py
backend/app/fusion/phase.py
backend/app/fusion/orchestrator.py
backend/app/fusion/workgraph.py
backend/app/fusion/evidence_receipt.py
backend/tests/test_fusion_contract_closed.py
backend/tests/test_fusion_phase_machine.py
backend/tests/test_fusion_workgraph.py
```

#### Modified

```text
backend/app/fusion/_monolith.py
backend/app/fusion/__init__.py
backend/app/fusion/crew.py
backend/app/fusion/task_card.py
backend/app/fusion/verify.py
backend/app/fusion/session.py
backend/app/fusion/panel.py
backend/app/fusion/project_memory.py
backend/app/fusion/log_analyst.py
backend/app/fusion/merge.py
backend/app/fusion/metrics.py
backend/app/routers/chat.py
```

#### Deleted or Quarantined After Cutover

```text
unreachable _monolith.py legacy tail
live product imports of execute_cascade / execute_race / execute_full
pipeline_v1 product execution path
duplicate UI crew execution path
regex/path policy execution authority
duplicate role-assignment tables
obsolete GREEN/RED and plan_digest compatibility
```

Exact whole-file deletion is decided from the import graph at the cutover commit; user-owned or independently useful modules are not deleted merely because their old monolith call site is dead.

### Regression and Deletion Gates

Deletion occurs only when all relevant gates pass:

1. focused adaptive-crew and OpenAI tool-protocol tests;
2. full `backend/tests/test_fusion*.py` regression;
3. fixed billing fixtures with no branch-cost drift;
4. automatic session alias and sticky restoration tests;
5. workspace/patch evidence freshness tests;
6. WorkGraph cycle, ownership and merge-conflict tests;
7. truthful actual-role telemetry assertions;
8. prompt-cache hit rate no worse than baseline;
9. SWE-bench 0:5 quality not below baseline;
10. SWE-bench 0:10 only after the 0:5 threshold passes;
11. latency comparison by phase and end-to-end;
12. CI search gate proving retired executors have no live product import.

### Final Code-Quality Invariants

After migration:

- `_monolith.py` is a thin compatibility facade or gone;
- one `TaskContract` is the task source of truth;
- one `CrewSession v4` owns phase state;
- one Evidence Gate owns terminal truth;
- one role roster owns model assignments;
- one WorkGraph owns parallel execution;
- one merge barrier owns combined patches;
- compatibility code translates data but never decides behavior;
- dead paths are deleted in the same program of work;
- no framework or database is added unless measurements prove a need.

Therefore the new architecture is not installed over the existing structure. The working boundaries are preserved, the current hot path is extracted, the replacement runtime is proven serially, parallelism is added last, traffic is cut over, and the old code is then obligatorily removed.

## Research Overview

This report evaluates the proposed ZeusCode coding crew against current public evidence from official model-provider documentation, engineering publications, peer-reviewed and preprint research, open-source coding-agent implementations, benchmark results, and practitioner discussions.

---

## Technical Research Scope Confirmation

**Research Topic:** Contract-closed multi-agent coding architecture for ZeusCode

**Research Goals:** Validate the proposed Opus contract → GPT implementation → DeepSeek diagnosis → Grok verification → Opus reconciliation architecture; compare it with leading global approaches; identify evidence-backed improvements to quality, latency, cost, verification, and orchestration.

**Technical Research Scope:**

- Architecture analysis — planner/executor/verifier patterns, state machines, role ownership, evidence gates
- Implementation approaches — coding-agent loops, tool use, test-driven repair, termination and stagnation controls
- Technology stack — model APIs, structured outputs, prompt caching, state and telemetry
- Integration patterns — client/server boundary, tool execution, repository evidence, multi-model handoffs
- Performance considerations — benchmark quality, latency, cost, concurrency and role activation
- Industry and community evidence — official sources, academic studies, GitHub projects, Reddit and Hacker News

**Research Methodology:**

- Current web data with rigorous source verification
- Multi-source validation for critical technical claims
- Explicit separation of official evidence, academic evidence and practitioner opinion
- Confidence labels for uncertain or conflicting findings
- Direct comparison against the observed ZeusCode SWE-bench result of 1/10 resolved

**Scope Confirmed:** 2026-08-01

---

## Technology Stack Analysis

### Orchestration Paradigm

The strongest current evidence favors a **centralized, deterministic workflow with bounded specialist calls**, not a free-form swarm:

- Anthropic recommends adding agentic complexity only when simpler workflows fail, and distinguishes deterministic workflows from autonomous agents. Its relevant patterns are orchestrator-workers and evaluator-optimizer, both with explicit task boundaries and evaluation criteria. [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- OpenAI documents manager-style “agents as tools” as the fit when one manager must retain ownership, synthesize specialist outputs, and enforce shared guardrails. It explicitly recommends adding specialists only when they improve capability isolation, policy isolation, prompt clarity, or trace legibility. [OpenAI: Agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/) · [OpenAI API: Orchestration and handoffs](https://developers.openai.com/api/docs/guides/agents/orchestration)
- Google ADK separates LLM agents from deterministic workflow agents. Sequential, parallel, and loop control is code-owned rather than decided by another model; graph workflows add explicit state and transitions. [Google ADK workflow agents](https://github.com/google/adk-docs/blob/main/docs/agents/workflow-agents/index.md)
- Microsoft Magentic-One uses a central Orchestrator plus a task ledger and progress ledger, including explicit re-planning when progress stalls. [Microsoft Research: Magentic-One](https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/)

**Implication for ZeusCode:** the proposed server-owned `CrewPhase` state machine is well aligned with leading designs. Model-driven routing on every tool turn is not.

### Coding-Agent Architecture

Software-engineering evidence is even more specific:

- SWE-agent demonstrated that the agent-computer interface materially changes coding performance; reliable repository navigation, edits, command feedback, and constrained interfaces matter as much as model reasoning. [SWE-agent, NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/5a7c947568c1b1328ccc5230172e1e7c-Paper-Conference.pdf)
- Agentless achieved a reported 32% on SWE-bench Lite with a simple three-stage pipeline — localization, repair, validation — and an average cost of $0.70, outperforming more complex contemporary open-source agents. It generates reproduction tests and uses both reproduction and regression tests to rank patches. [Agentless](https://arxiv.org/pdf/2407.01489)
- MASAI splits software repair into Test Template Generator, Issue Reproducer, Edit Localizer, Fixer, and Ranker, reporting 28.33% on SWE-bench Lite at under $2 per issue. Its explicit motivation includes avoiding long trajectories and extraneous context. [MASAI](https://arxiv.org/html/2406.11638)
- CodeR uses a predefined task graph with Reproducer, Fault Localizer, Editor, and Verifier; the graph is parsed and strictly executed. It also reported 28.33% on SWE-bench Lite with one submission per issue. [CodeR](https://arxiv.org/html/2406.01304v3)

**Implication for ZeusCode:** the proposed architecture is missing a first-class **localization/reproduction phase**. “Opus contract → GPT implementation” is too early. The evidence-backed sequence is closer to:

`Contract → Inspect/localize → Reproduce → Repair → Verify → Reconcile`.

Grok should not merely select a test command; it should own reproduction and acceptance coverage. GPT should not edit until localization and reproduction evidence exist when the task is a bug fix.

### Models, Structured Contracts and State

Current frameworks converge on a small set of implementation primitives:

- **Structured outputs:** role handoffs should use typed JSON/schema, not prose or commands extracted from serialized plans. Anthropic's cookbook validates structured worker outputs; OpenAI agents support typed outputs and guardrails. [Anthropic orchestrator-workers cookbook](https://platform.claude.com/cookbook/patterns-agents-orchestrator-workers) · [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- **Persistent ledgers:** Microsoft separates task facts/plans from step progress; Anthropic's research system persists plans in memory before context truncation. [Magentic-One](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/magentic-one.html) · [Anthropic multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Guardrails and tracing:** OpenAI treats guardrails and tracing as core primitives, not optional telemetry. [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- **Isolated contexts:** Claude Code subagents use separate context windows and scoped tools; agent teams cost more and remain experimental with known coordination limitations. [Claude Code subagents](https://code.claude.com/docs/en/subagents) · [Claude Code agent teams](https://code.claude.com/docs/en/agent-teams)

**Implication for ZeusCode:** `TaskCard`, `AcceptancePlan`, `PostEditVerdict`, and `ReconciliationVerdict` should be typed server state. Actual model invocations, evidence hashes, phase transitions, and terminal status must be traceable.

### Execution Boundary and Storage

The existing ZeusCode boundary remains sound:

- ZeusCode should own contracts, model calls, state transitions, budgets, billing, and evidence interpretation.
- The client should continue to own files, shell, git, tests, and LSP. SWE-agent's results reinforce that the execution interface must be intentionally designed, but they do not justify moving the client agent loop onto the server.
- Existing sticky session state plus project memory is sufficient for the first contract-closed implementation; a new graph database or general-purpose agent framework is not supported by the evidence.
- The workflow should be implemented directly in the existing Python runtime. Adopting AutoGen, CrewAI, LangGraph, or OpenAI Agents SDK would duplicate existing session, billing, provider, and tool contracts without proving a quality gain.

### Cost and Performance Evidence

Multi-agent systems are not automatically more efficient:

- Anthropic reports a 90.2% improvement over single-agent research on an internal research evaluation, but roughly 15× chat token usage; token use explained most performance variance. Anthropic limits the recommendation to high-value, parallelizable tasks. [Anthropic multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- Google and MIT report that multi-agent coordination improved parallelizable tasks but degraded sequential planning tasks by 39–70%; tool-heavy tasks suffered coordination overhead, and centralized verification contained error propagation better than independent agents. [Google Research: Scaling agent systems](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/) · [Paper](https://www.arxiv.org/pdf/2512.08296)
- Agentless shows that a fixed localization/repair/validation workflow can outperform more autonomous systems at lower cost. [Agentless](https://par.nsf.gov/biblio/10682640)

**Implication for ZeusCode:** coding is predominantly sequential and tool-heavy. Calling four models on every turn would likely reduce quality and speed. Specialists should activate at phase boundaries, while deterministic client evidence should control transitions.

### Practitioner Evidence

Practitioner discussions are lower-confidence than papers or official documentation, but they reinforce the same operational lessons:

- A Hacker News discussion characterizes multi-agent development as a distributed-systems problem and emphasizes deterministic compile/lint/test gates plus qualitative agent review at stage boundaries. [HN: Multi-Agentic Software Development Is a Distributed Systems Problem](https://news.ycombinator.com/item?id=47761625)
- A verification-first Claude Code workflow separates define → execute → verify and checks each acceptance criterion rather than treating an unstructured plan as proof. [HN: Verification-first workflow](https://news.ycombinator.com/item?id=46934254)
- Practitioners warn that letting the same agent write both code and tests can lead to tests being weakened to pass, while deep verification loops can become prohibitively token-heavy. [HN: Agentic verification loop](https://news.ycombinator.com/item?id=47618164)

### Technology Adoption Conclusion

**High confidence:** centralized deterministic orchestration, typed role contracts, persistent task/progress ledgers, reproduction tests, independent post-edit verification, machine guardrails, and explicit terminal/stagnation controls are well supported.

**High confidence:** a permanent four-model call on every coding turn is not supported and conflicts with evidence about sequential and tool-heavy tasks.

**Medium confidence:** using different model families for planner, implementer, analyst, and verifier can reduce correlated blind spots, but model diversity alone does not guarantee independent judgment. Independence must come from separate context, explicit criteria, and machine evidence.

**Required correction to the proposed architecture:** insert `Inspect/localize` and `Reproduce` before implementation; make Grok the owner of reproduction and post-edit acceptance; retain Opus as contract/reconciliation owner; keep DeepSeek event-driven; let deterministic state, not an LLM router, decide the phase.

---

## Integration Patterns Analysis

### External API and Client Boundary

ZeusCode should keep the existing OpenAI-compatible `/v1` interface and preserve the product boundary: server = brain, policy, contracts and billing; client = files, shell, LSP and repository workspace.

The Model Context Protocol's host-client-server architecture supports the same separation of concerns: the host coordinates model interaction, clients maintain scoped connections, and servers expose schema-described capabilities. The protocol also requires capability discovery and treats tool annotations as untrusted unless they come from trusted servers. [MCP architecture](https://modelcontextprotocol.io/specification/draft/architecture/index) · [MCP tools](https://modelcontextprotocol.io/specification/2025-03-26/server/tools)

**Decision:** do not move the tool loop into ZeusCode and do not add a server-side browser/filesystem agent. Improve the existing client evidence envelope instead.

### Internal Communication: Contracts, Not Conversation

Agent-to-agent prose is an unreliable integration protocol. A useful modern reference is A2A's separation of:

- **Task:** stateful unit of work with explicit lifecycle state;
- **Message:** communication within the task;
- **Artifact:** immutable task output;
- **Status event:** state transition;
- **Artifact event:** output update.

A2A explicitly recommends returning task outputs as artifacts rather than messages. [A2A specification](https://github.com/a2aproject/A2A/blob/main/docs/specification.md) · [A2A protocol definitions](https://a2a-protocol.org/v1.0.0/definitions/)

ZeusCode does not need to implement A2A internally, but should copy this semantic separation:

- `TaskCard` is the durable task contract.
- `InspectionArtifact` records relevant files, symbols, public API and execution path.
- `ReproductionArtifact` records command, expected failure, observed failure and evidence hash.
- `PatchArtifact` records changed paths and diff hash, not the entire mutable transcript.
- `VerificationArtifact` maps every acceptance clause to machine evidence.
- `DiagnosisArtifact` is a bounded recommendation attached to one fresh failure.
- `ReconciliationVerdict` is the terminal decision.

Models should receive only the artifacts required for their current role. Raw transcript replay should be the fallback, not the primary handoff.

### State Machine and Phase Ownership

Google ADK's workflow agents, CodeR's predefined task graphs, Magentic-One's ledgers and LangGraph's checkpointed graph all support code-owned execution order. [Google ADK](https://github.com/google/adk-docs/blob/main/docs/agents/workflow-agents/index.md) · [CodeR](https://arxiv.org/html/2406.01304v3) · [Magentic-One](https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/) · [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

Recommended phase graph:

1. `CONTRACTING` — Opus creates typed acceptance clauses.
2. `INSPECTING` — GPT gathers repository facts; no edits.
3. `REPRODUCING` — Grok creates/selects a failing reproduction or states why reproduction is impossible.
4. `IMPLEMENTING` — GPT edits against the contract and reproduction.
5. `DIAGNOSING` — DeepSeek activates only after a fresh failed command.
6. `VERIFYING` — Grok runs reproduction plus targeted regression checks.
7. `RECONCILING` — Opus maps every clause to evidence.
8. Terminal: `VERIFIED`, `UNVERIFIED`, `BLOCKED`, or `FAILED`.

Transitions must be server predicates over typed state and trusted evidence. Models propose artifacts; models do not select the next arbitrary phase.

### Repository Evidence Protocol

The 1/10 ZeusCode run exposed a critical integration error: server-side assumptions about the working tree did not reliably represent the client's `/testbed`.

Every tool-result envelope used for gating should include:

- `task_id`, `turn_id`, `tool_call_id`;
- client-generated `workspace_id` bound to the automatic crew session;
- normalized repository root;
- command and working directory;
- start/end timestamps, exit code and timeout status;
- bounded stdout/stderr digest plus raw-output hash;
- before/after git diff hash;
- changed paths;
- test classification (`reproduction`, `targeted`, `regression`, `lint`, `build`);
- whether the evidence occurred after the latest successful mutation.

The server must reject evidence whose workspace or sequence does not match the active task. A green result from an older diff, another directory or another session is not green evidence.

### Reproduction and Verification Handoff

The software-maintenance literature converges on reproduction, localization, patch generation and validation as distinct phases. A 2025 survey of SWE-bench architectures describes preprocessing, issue reproduction, localization, decomposition, patch generation, verification and ranking. [SWE-bench architecture survey](https://arxiv.org/html/2506.17208v2)

SWT-Bench defines a valid reproduction test as one that fails on the original repository and passes with the gold patch, showing that “a test ran” is weaker than “the issue was reproduced.” It also finds complementarity among test-generation methods. [SWT-Bench](https://arxiv.org/html/2406.12952v3)

Therefore the Grok handoff should contain typed assertions:

- exact behavior to reproduce;
- command to run;
- expected pre-fix result;
- affected public API or lifecycle stage;
- regression dimensions: subclass, version, serialization direction, masking, dtype, forwarding path, etc.;
- provenance of each assertion.

After implementation, Grok must independently inspect the final diff and return clause-level verdicts. A passing generic test command cannot satisfy an untested public signature or end-to-end forwarding clause.

### Failure Diagnosis and Retry Semantics

DeepSeek should receive only a fresh, sanitized failure bundle:

- failing command and exit code;
- bounded relevant output;
- current diff hash;
- reproduction/acceptance clause;
- latest changed symbols;
- previous diagnosis hash, if any.

Its output is advice, not trusted evidence. The diagnosis expires after the next mutation or successful rerun.

Checkpointed workflow documentation warns that resumed nodes can re-execute side effects and therefore require idempotency. [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) ZeusCode should enforce the same principle:

- role-call dedupe key = `(task_id, phase, input_artifact_hash, role)`;
- tool evidence dedupe key = `tool_call_id`;
- phase transition uses compare-and-swap on session version;
- terminal state is irreversible unless a new task version is created;
- retry budget belongs to the phase, not to the model's prose loop.

### Guardrails and Trust

OpenAI's production guidance distinguishes input, output and tool guardrails, and uses resumable state for paused runs. [OpenAI guardrails and human review](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals)

Anthropic warns that multi-agent systems can accidentally raise the trust level of a subagent's summary even when it contains untrusted tool-derived content. [Anthropic: How we contain Claude](https://www.anthropic.com/engineering/how-we-contain-claude)

ZeusCode should use this trust order:

1. Server policy and schemas.
2. Authenticated client identity and session binding.
3. Machine evidence with workspace/sequence validation.
4. Model-generated structured artifacts.
5. Raw repository output and external content.

No model output — including Opus or Grok — may directly set `VERIFIED`, `tests_green`, `diff_nonempty`, `exit_code`, or billing counters.

### Observability

Anthropic reports that full production tracing and monitoring decision patterns were necessary to diagnose duplicated work, wrong tool selection and premature continuation. [Anthropic multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)

Each ZeusCode trace should expose:

- requested role vs actual model;
- phase and reason for invocation;
- input/output artifact hashes;
- tool calls and evidence sequence;
- cache hits and token/cost usage;
- clause coverage before submission;
- retries, degradation and stagnation;
- exact terminal reason.

“Crew size = 4” is configuration, not participation telemetry. Actual-role telemetry must count only completed role calls that produced a valid artifact.

### Integration Conclusion

**Keep:** `/v1`, server/client boundary, automatic session identity, Task Card memory, prompt cache, deterministic submit interception.

**Change:** replace transcript-based handoffs with immutable typed artifacts; bind all evidence to the client workspace and diff sequence; introduce inspection and reproduction phases; make phase transitions server-owned and idempotent.

**Do not add:** A2A network services, a general message broker, server-side file agents, or a new orchestration framework. Their useful semantics can be implemented inside the existing runtime with much less migration risk.

---

## Architectural Patterns and Design

### Competing Architecture Schools

#### 1. One autonomous ReAct agent

One model repeatedly inspects, edits and tests.

**Strengths:** minimal communication overhead, coherent sequential reasoning, simple state and low latency. SWE-agent and OpenHands demonstrate that a strong execution interface and event loop can make this pattern highly effective. [SWE-agent](https://doi.org/10.48550/arxiv.2405.15793) · [OpenHands SDK](https://arxiv.org/html/2511.03690v1)

**Weaknesses:** the same model defines correctness, writes the patch and judges itself; context accumulates; recovery and termination are probabilistic.

**ZeusCode fit:** retain a stateful GPT tool loop as the implementation spine, but do not let it own acceptance or terminal truth.

#### 2. Role-playing software company

MetaGPT and ChatDev model product manager, architect, engineer and QA roles. MetaGPT's improvement over unconstrained chat comes from SOPs and structured artifacts rather than role names alone. [MetaGPT](https://arxiv.org/html/2308.00352v7) · [ChatDev](https://aclanthology.org/2024.acl-long.810.pdf)

**Strengths:** clear human-readable responsibility and modular prompts.

**Weaknesses:** expensive sequential ceremony; cascading hallucinations; benchmarks used for early role-playing systems do not establish superiority on real repository repair.

**ZeusCode fit:** use role specialization, reject the “virtual company” metaphor as runtime control.

#### 3. Central orchestrator with workers

Anthropic Research, Magentic-One and manager-style OpenAI agents use a lead that delegates bounded subtasks and synthesizes results.

**Strengths:** central accountability, isolated context windows, contained error propagation.

**Weaknesses:** the orchestrator can become a latency and information bottleneck; dynamic delegation can duplicate work; costs scale quickly.

**ZeusCode fit:** Opus should own the task contract and exceptional reconciliation, but should not narrate or approve every shell turn.

#### 4. Deterministic task graph

Agentless, CodeR, MASAI and Google workflow agents use fixed or code-owned phases.

**Strengths:** predictable costs, testable transitions, easy replay, clear artifact boundaries and less context drift.

**Weaknesses:** a rigid graph can fail on unusual tasks unless it has typed escape paths.

**ZeusCode fit:** this should be the primary architecture.

#### 5. Parallel candidate generation and selection

Cursor recommends isolated worktrees for multiple agents attempting hard problems, while modern SWE-bench systems use candidate generation, test consolidation, filtering and selection. [Cursor agent best practices](https://cursor.com/blog/agent-best-practices) Research on Trae and later test-consolidation systems shows that selection quality, not raw candidate count, determines whether test-time scaling helps; naive selection can worsen after the candidate pool grows. [Adaptive multi-agent scaffolding](https://doi.org/10.48550/arxiv.2606.25514) · [Test Consolidation Augmentation](https://aclanthology.org/2026.acl-long.1359.pdf)

**Strengths:** useful when the repair hypothesis is genuinely ambiguous.

**Weaknesses:** expensive; same-workspace writes conflict; weak selectors choose plausible but wrong patches.

**ZeusCode fit:** reserve for stagnation or high-ambiguity tasks, with isolated client worktrees and at most two candidate patches initially.

#### 6. Decentralized swarm or debate

Agents communicate freely and converge through discussion or voting.

**Strengths:** broad exploration and reduced central bottlenecks on decomposable tasks.

**Weaknesses:** correlated errors, coordination overhead and authority ambiguity. Research finds that ordinary debate can reinforce shared errors; model diversity alone does not create independent evidence. [AceMAD](https://doi.org/10.48550/arxiv.2603.06801) Google's scaling study finds independent systems amplify errors more than centralized coordination. [Scaling agent systems](https://www.arxiv.org/pdf/2512.08296)

**ZeusCode fit:** do not use as the default coding architecture.

### Recommended Architecture: Evidence-Closed Adaptive Coding Graph

The research supports a refinement of “Contract-Closed Crew.” The contract is necessary, but closure must be based on repository evidence. The recommended name and invariant are:

> **Evidence-Closed Adaptive Coding Graph:** every phase produces a typed artifact, every transition is server-owned, and no task reaches `VERIFIED` until every acceptance clause is closed by fresh evidence from the active client workspace.

#### Core sequential spine

```text
User request
  → Opus: TaskContract
  → GPT: InspectionArtifact
  → Grok: ReproductionArtifact
  → GPT: PatchArtifact
  → Grok: VerificationArtifact
  → Server gate
  → Opus reconciliation only when semantic judgment is required
  → VERIFIED | UNVERIFIED | BLOCKED | FAILED
```

DeepSeek is an event-driven side branch:

```text
fresh command/test failure
  → DeepSeek: DiagnosisArtifact
  → GPT receives bounded correction
  → retry from IMPLEMENTING or REPRODUCING
```

Parallel candidate generation is an escalation branch:

```text
two no-progress cycles or unresolved high-ambiguity clause
  → two isolated patch hypotheses
  → consolidated acceptance suite
  → deterministic filtering + Grok selection
```

### Role and Model Assessment

#### Opus 4.6 — contract owner and semantic reconciler

This is a strong assignment. Anthropic reports 80.84% on SWE-bench Verified and specifically describes improved planning, long-horizon work, codebase navigation, debugging and review. [Anthropic Opus 4.6 system card](https://www-cdn.anthropic.com/c788cbc0a3da9135112f97cdf6dcd06f2c16cee2.pdf) · [Announcement](https://www.anthropic.com/news/claude-opus-4-6)

Use Opus for high-leverage judgment, not repetitive execution:

- one compact contract call;
- optional contract revision when inspection disproves an assumption;
- final semantic reconciliation for serious or degraded tasks.

#### GPT-5.4 — investigator and production implementer

This is also strongly supported. OpenAI reports 57.7% on SWE-bench Pro Public and lower latency than its prior coding model; Scale's standardized public evaluation reports 59.1%. [OpenAI GPT-5.4](https://openai.com/index/introducing-gpt-5-4/) · [Scale leaderboard](https://labs.scale.com/api/pdf/leaderboard/swe_bench_pro_public)

Keeping inspection and implementation in one stateful GPT session preserves sequential coherence and repository knowledge. It should be the only default code writer.

#### Grok 4.5 — reproducer and verifier

The assignment is plausible and attractive on cost/latency grounds, but not fully proven for test quality specifically. xAI positions Grok 4.5 for coding and agentic tasks; vendor results report strong Terminal-Bench and SWE-bench Pro performance with high token efficiency. Independent reproduction of all figures is still limited. [xAI Grok 4.5 docs](https://docs.x.ai/developers/grok-4-5) · [Benchmark methodology review](https://www.datacamp.com/blog/grok-4-5)

Grok should be evaluated on:

- issue reproduction rate;
- fail-before/pass-after test quality;
- acceptance-clause recall;
- false-green rate;
- tokens and latency.

Do not infer “good tester” solely from general coding benchmarks.

#### DeepSeek V3.2 — fresh-failure diagnostician

This is the least evidence-backed assignment, but safe if its authority remains narrow. DeepSeek reports competitive coding results, but terminal/tool benchmarks are materially weaker than the frontier models and there is no dedicated log-analysis benchmark establishing superiority. [DeepSeek V3.2 report](https://arxiv.org/html/2512.02556v1)

Use DeepSeek because it is inexpensive and analytically useful, with these constraints:

- only fresh failures;
- no direct edits;
- no gate authority;
- one diagnosis per evidence hash;
- automatically A/B against a GPT or Grok diagnosis sample to verify that it adds value.

### Adaptive Participation Without an LLM Router

The number of model calls should follow deterministic phase predicates:

- **Trivial/local edit:** Opus compact contract → GPT implementation → deterministic checks; Grok only if acceptance cannot be fully machine-closed.
- **Bug fix:** Opus → GPT inspection → Grok reproduction → GPT patch → Grok verification; DeepSeek only on failure.
- **Public API, serialization, security, migration or multi-module change:** full flow plus Opus reconciliation.
- **Fresh failure:** add DeepSeek once for that evidence hash.
- **Stagnation/high ambiguity:** add one parallel patch candidate, not an open-ended swarm.
- **No diff/no new evidence turn:** do not call the doer again; request the exact missing action or terminate.

This is adaptive orchestration, but it is not the legacy semantic router. The workflow reacts to observable state: task type encoded in the contract, diff presence, reproduction status, failure freshness, clause coverage and stagnation.

### Performance Design

Top coding products parallelize **independent tasks**, not tightly coupled same-file reasoning:

- OpenAI Codex says subagents are useful for parallel codebase exploration or independent parts of a feature and explicitly notes higher token use. [Codex subagents](https://developers.openai.com/codex/concepts/subagents)
- Claude Code says agent teams work best for independent tasks and that sequential or same-file work is better handled by one session or focused subagents. [Claude Code agent teams](https://code.claude.com/docs/en/agent-teams)
- Cursor uses isolated worktrees when multiple agents attempt changes and emphasizes that a usable environment capable of running tests is essential. [Cursor Cloud Agents](https://cursor.com/docs/cloud-agent) · [Cursor best practices](https://cursor.com/blog/agent-best-practices)
- Google Jules exposes plan review, isolated execution and concurrent independent sessions rather than forcing internal multi-agent collaboration on every task. [Google Jules](https://jules.google/docs/) · [Jules SDK](https://github.com/google-labs-code/jules-sdk/)

Latency should be reduced by:

- parallelizing Opus contract refinement and read-only repository indexing only when independent;
- retaining one stateful GPT implementation loop;
- running deterministic checks immediately on the client;
- calling Grok at reproduction and final-diff boundaries, not every turn;
- calling DeepSeek only on fresh red evidence;
- reusing artifact hashes and provider prompt cache;
- terminating immediately after a valid submission state.

### Security and Data Architecture

OpenHands' event-sourced design provides a useful pattern: immutable typed events, one mutable conversation state, deterministic replay and observers that do not mutate execution state. [OpenHands event system](https://docs.openhands.dev/sdk/arch/events.md)

ZeusCode should incrementally evolve `CrewSession` toward:

- immutable `CrewEvent` append log;
- versioned materialized `CrewSession`;
- typed artifact references and hashes;
- server-owned counters and terminal status;
- tenant-scoped task memory;
- replayable phase transitions.

This does not require rewriting the runtime around OpenHands. It requires adopting the same invariants.

### Architectural Verdict

- **Current Task Card runtime demonstrated in SWE 1/10:** approximately **4/10**. Transport became stable, but role participation, evidence binding and acceptance closure were inadequate.
- **Pre-research Contract-Closed proposal:** approximately **7/10**. Correct direction, but it lacked explicit localization/reproduction and over-relied on post-hoc verification.
- **Evidence-Closed Adaptive Coding Graph:** approximately **9/10 as a design hypothesis**. It aligns with official industry patterns and software-repair research, but the score is not earned until controlled benchmark evidence shows improvement.

The decisive quality metric is not “all four models were called.” It is:

> How many acceptance clauses were closed by fresh, workspace-bound evidence per dollar and per minute, and how often did that produce an officially resolved patch?

---
