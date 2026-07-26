# Epic 2 — полная валидация (дыры → фиксы → gate)

**Date:** 2026-07-22  
**Suite:** `test_fusion*.py` → **131 passed** (incl. `test_fusion_epic2_validation.py`)

## Найденные дыры (до фикса)

| ID | Дыра | Severity |
|---|---|---|
| H1 | `ZEUS_FUSION_EPIC2_POLICY` default **off** → AC 2.x library-only | **P0** |
| H2 | CASCADE Mini+escalate+failover не в serving path | **P0** |
| H3 | `classify_failed` недостижим из live `classify_smart` | **P0** |
| H4 | MoR tip FAST-only vs PRD full ladder (F14) | **P0** (reconcile) |
| H5 | `mode_ignored` только bool, не `routed_by` | **P1** |
| H6 | `resolve_custom_panel` не wired | **P1** |
| H7 | `run_mini_verifier` отсутствовал (`mini_unavailable`) | **P1** |
| H8 | `mor_*` / cascade codes не в CLOSED set | **P1** |

## Что закрыто

| ID | Фикс |
|---|---|
| H1 | Default **on**; opt-out `ZEUS_FUSION_EPIC2_POLICY=0` |
| H2 | `panel.execute_cascade` + wire в `iter_fusion` при `serving_path=CASCADE` |
| H3 | LLM classify fail → `classify_failed=True`; hook передаёт в policy |
| H4 | Documented MVP freeze FAST→CASCADE; full ladder via `ZEUS_FUSION_MOR_FULL_LADDER=1` |
| H5 | `routed_by=mode_ignored` when unknown mode + policy_* row |
| H6 | Custom 1/2/3 path_hint applied after `resolve_panel` |
| H7 | `verify.run_mini_verifier` (+ heuristic for tests) |
| H8 | CLOSED set + `policy_cascade_mini_pass` / `cascade_disaster` / mor_* |

Also: force/legacy `routed_by` preserved after FULL executor (Epic1 Onestack AC).

## Матрица после фикса

| Story | AC | Notes |
|---|---|---|
| 2.1 Classify+Effort+fail | **PASS** | fail wire + Effort +1 |
| 2.2 Policy+MoR+clamps | **PASS** | MoR freeze documented |
| 2.3 CASCADE Mini+escalate | **PASS** | live executor |
| 2.4 Custom+mode_ignored | **PASS** | wired |
| 2.5 Fixtures F*/I* | **PASS** | harness unchanged green |

| AD | Verdict |
|---|---|
| AD-3 order | **PASS** |
| AD-5 Mini | **PASS** |
| AD-11 simple clamp | **PASS** |
| AD-15 Path enum | **PASS** (policy + CASCADE serving) |

## Gate verdict

**Epic 2 VALIDATED** (accept-with-known-debt: MoR full ladder opt-in; flash native FR-4 fields still bridged via legacy clf_meta).

## Commands

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_fusion*.py -q
```
