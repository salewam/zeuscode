# Epic 2 report — Agent B (Stories 2.1–2.5)

**Date:** 2026-07-22  
**Repo:** `ultra-mode-mvp`  
**Scope:** Path policy + Mini-Verifier + fixture harness

## Files changed / added

| Path | Role |
|---|---|
| `backend/app/fusion/policy.py` | Full FR-28/AD-3 engine: classify fields, Effort +1, first-match table, MoR tip 0\|1, mode clamps, CASCADE escalate map, Leader failover, custom panel (FR-34), unknown mode ignore (FR-37) |
| `backend/app/fusion/verify.py` | Mini-Verifier JSON `{good_enough,confidence,reason}` + threshold (≥0.8). Aspect block remains under `# EPIC3-ASPECT` (Agent C) |
| `backend/app/fusion/_monolith.py` | Thin `# EPIC2-HOOK` soft call via `soft_resolve_for_monolith` (flag-gated) |
| `backend/app/fusion/__init__.py` | Re-exports `policy`, `verify` |
| `backend/tests/test_fusion_policy.py` | Unit coverage 2.1–2.4 + Mini + no-`routers` import guard |
| `backend/tests/test_fusion_policy_fixtures.py` | Fixture harness runner |
| `backend/tests/fixtures/fusion_policy/cases.json` | F1,F2,F5,F7,F8a,F8b,F9,F10,F14,F15,F16 + I1–I3 |
| `backend/tests/test_fusion_routing.py` | Expectation sync to FR-37 `compat_1to3_*` / `forced_*` / `legacy_*` (Agent A codes) |

## Feature flag / brownfield

- Env: `ZEUS_FUSION_EPIC2_POLICY=1|true|on` enables serving Path from `policy.py`.
- Default **off** → existing `resolve_routing_ex` + `classify_smart` unchanged.
- Hook is soft: any exception / incomplete decision → brownfield path continues.
- Path→legacy stack map: `FAST|CASCADE→fast`, `RACE|FULL→full` until Epic 3 executors own Paths.

## Tests run

```bash
PYTHONPATH=backend .venv/bin/python -m pytest \
  backend/tests/test_fusion_routing.py \
  backend/tests/test_fusion_policy*.py -q
# → 55 passed
```

Also asserted `fusion/*` does not import `routers.*`.

## Hooks for Epic 3

| Hook | Where | Notes |
|---|---|---|
| `PolicyDecision.path/policy_path/routed_by` | `policy.select_path_policy` | Execute may only append escalate codes (`cascade_escalate_*`, `race_*`) |
| `cascade_escalate_action(...)` | `policy.py` | FR-8 map after Mini fail — panel should call, not re-derive |
| `next_leader_failover` / `leader_failover_chain` | `policy.py` | FR-15 ordered ready lists |
| `mini_verifier_passed` | `verify.py` | CASCADE/RACE early-exit gate; Leader self-score never stops |
| `resolve_custom_panel` | `policy.py` | 1/2/3 models → FAST-eq / A+B / A/B/C |
| Aspect APIs | `verify.py` `# EPIC3-ASPECT` | Owned by Agent C — do not reshape Mini API |
| Soft monolith hook | `# EPIC2-HOOK` in `iter_fusion` | Replace `path_to_legacy_stack` once panel runs real Paths |

## Story coverage

| Story | Status |
|---|---|
| 2.1 Classify phase/complexity/confidence + Effort +1 + fail→CASCADE | Done (`classify_local` / `classify_from_legacy`, `bump_complexity`) |
| 2.2 Path table + MoR + clamps + closed `routed_by` | Done |
| 2.3 Mini-Verifier + escalate map + Leader failover | Done (decision helpers; execution still brownfield until panel wires CASCADE) |
| 2.4 Custom panel + unknown mode ignore + thinking passthrough | Done |
| 2.5 Fixture harness F1/F2/F5/F7/F8a/F8b/F9/F10/F14–F16 + I1–I3 | Done |

## Gaps / follow-ups

1. **MoR tip scope:** PRD formulas with full `escalate_one` ladder would tip many CASCADE→RACE (breaks F6/F14). MVP tip applies only when `policy_path==FAST` (FAST→CASCADE). Full ladder tip needs PRD/fixture reconciliation.
2. **CASCADE execution** is not yet a live Path executor — panel (Epic 3) must call Mini + `cascade_escalate_action` on the serving Path.
3. **LLM classify → FR-4 fields** bridged via `classify_from_legacy`; dedicated flash schema with native `classify_phase`/`complexity_band` not shipped.
4. **F3/F4/F6/F11–F13/F17/R1/R2** owned outside S2.5 (Epic 3/4 eval).
5. Prefs surfaces for Effort/Kill-Switch UI = Agent D; policy already reads `zeus.effort` / `zeus.kill_switch`.
