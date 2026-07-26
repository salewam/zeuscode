# Epic 1 report — Stories 1.2–1.4 (Agent A)

Date: 2026-07-22  
Repo: `ultra-mode-mvp`  
Ownership: `PARALLEL_CONTRACT.md` Agent A

## Status

Stories **1.2 / 1.3 / 1.4** implemented as far as brownfield `fast|full` stack allows. Facade + EPIC2/EPIC3 hooks from other agents left intact.

## Files changed

| File | Change |
|---|---|
| `backend/app/fusion/_monolith.py` | FusionResult handoff in `_pack_completion`; Path map `fast→FAST` / `full→FULL`; FR-37 `routed_by` split (`legacy_*` ≠ `forced_*`, auto → `compat_1to3_*`); scrub-once via `prepare_messages_for_policy`; Brief satellites; billable_state stamping; cancelled_no_tokens on race cancel |
| `backend/app/fusion/brief.py` | **New** — `SatelliteBrief` / `build_satellite_brief` (last_assistant + errors + goal) |
| `backend/app/fusion/__init__.py` | Append-only re-exports for Epic 1 helpers |
| `backend/app/routers/chat.py` | `_bill_and_enrich` / `_charge_amounts` consume `FusionResult`; `cancelled_no_tokens` = ₽0; Onestack Path fields synced from result (no token-heuristic Path) |
| `backend/tests/test_fusion_result.py` | **New** — handoff + billable states |
| `backend/tests/test_fusion_scrub.py` | **New** — scrub once + Brief contract |
| `backend/tests/test_fusion_onestack.py` | **New** — Path fields + legacy/forced split |
| `backend/tests/test_fusion_routing.py` | Assertions updated for FR-37 `routed_by` codes (compat with resolve change) |

## Tests run

```bash
PYTHONPATH=backend .venv/bin/python -m pytest \
  backend/tests/test_fusion_routing.py \
  backend/tests/test_fusion_result.py \
  backend/tests/test_fusion_scrub.py \
  backend/tests/test_fusion_onestack.py -q
```

Result: **42 passed**

Boundary check: `fusion/*` does **not** import `routers.*`.

## Story acceptance notes

### 1.2 FusionResult + billable states
- Done events / `run_fusion` attach `_fusion_result` (`FusionResult`) + JSON `fusion_result`.
- Branches carry `completed | partial_stream | cancelled_no_tokens | cancelled_with_usage`.
- Chat bills from FusionResult; cancelled_no_tokens skipped (₽0).
- Path not invented from usage totals alone.

### 1.3 Onestack Path + routed_by
- Onestack includes `path`, `policy_path`, `escalate_from`, `routed_by`, `phase`, `complexity`, `trace_id`, `branches`.
- Legacy aliases → `legacy_fast_alias` / `legacy_full_alias`.
- `zeus.mode=fast|full` → `forced_fast` / `forced_full`.
- Brownfield auto → `compat_1to3_auto` / after classify `compat_1to3_classify`.
- Legacy `fusion_mode` kept as bridge.

### 1.4 Scrub once + Brief
- `prepare_messages_for_policy` = sanitize → scrub once at Edge→Policy.
- Scrub covers API keys, Bearer, private-key blocks, email-like secrets; idempotent placeholder.
- Satellites use Brief helper only (no full Cursor/system dump).

## Remaining gaps (brownfield / later epics)

| Gap | Owner |
|---|---|
| Real Path policy (`CASCADE`/`RACE`/`policy_*` routed_by, Effort +1, MoR) | Epic 2 → `policy.py` via `# EPIC2-HOOK` |
| Live FULL/RACE Soft-Stop cancel streams & aspect/judge billable branches | Epic 3 → `panel.py` / `judge.py` (already hooks + `outcome_to_completion`) |
| Sticky Leader / Kill-Switch / Effort prefs surfaces | Epic 4 → `session.py` / metrics / me+TG |
| Shadow baseline serving Path | Epic 2/4 flags |
| `escalate_from` only populated when Epic 2/3 escalate — brownfield fast/full usually `None` | Epic 2/3 |
| Classifier LLM calls billable when tokens present; regex classify stays ₽0 | OK today; Epic 2 may refine control-plane billing |

## What Epic 2 / 3 should hook into

**Epic 2 (`policy.py`)** — already has `# EPIC2-HOOK` in `iter_fusion` after brownfield resolve/classify:
- Return serving `Path` + closed `routed_by` (`policy_*`, clamps, kill_switch).
- Fill `clf_meta.policy_path` / `classify_phase` / `complexity_band` — `_pack_completion` already reads these into FusionResult / Onestack.
- Prefer calling after `prepare_messages_for_policy` (messages already scrubbed).

**Epic 3 (`panel.py` / `judge.py`)** — `# EPIC3-HOOK` already routes RACE/FULL via `outcome_to_completion` which attaches `FusionResult`:
- Ensure every LiveBranch sets accurate `billable_state` (incl. Soft-Stop / cancel).
- Keep using Brief (`build_satellite_brief`) for satellites — do not re-scrub.
- Bill path remains chat → `_fusion_result` only.

## Non-goals / not done here
- No git commit (per instructions).
- Did not rewrite `policy.py` / `panel.py` / `judge.py` / `session.py`.
- Did not reshape `types.py` fields.
