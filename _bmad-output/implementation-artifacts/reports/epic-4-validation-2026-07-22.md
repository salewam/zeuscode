# Epic 4 — полная валидация (дыры → фиксы → gate)

**Date:** 2026-07-22  
**Suite:** `test_fusion*.py` → **149 passed** (incl. `test_fusion_epic4_validation.py`)

## Найденные дыры (до фикса)

| ID | Дыра | Severity |
|---|---|---|
| H1 | `sticky_leader` писался в zeus, но `pick_leader` его не читал (FR16/AD-7/AD-16) | **P0** |
| H2 | Shadow/canary helpers не на hot path — `soft_resolve` отдавал candidate как serving | **P0** |
| H3 | Settings runtime budgets декоративные (rate/concurrency/timeout не consumed) | **P0** |
| H4 | Global kill не проставлял `zeus.kill_switch` → `routed_by` мог быть не `kill_switch` | **P1** |
| H5 | `note_verifier` / `note_dead_model` / alert stubs — dead code | **P1** |
| H6 | Feedback ingest без server-side enrich по `trace_id` | **P1** |
| H7 | Eval canary bars только в JSON, не в harness summary | **P1** |
| H8 | Overflow/long-context Leader selection отсутствовал (AD-16) | **P1** |

## Что закрыто

| ID | Фикс |
|---|---|
| H1 | `pick_leader(..., sticky_leader=)` + wire из `zeus.sticky_leader` в `iter_fusion` |
| H2 | `apply_serving_flags` в `soft_resolve_for_monolith` + brownfield fallback в monolith; `log_shadow_compare` |
| H3 | `check_rate_limit` (chat 429), panel/race Semaphores из Settings, RACE timeout clamp к `global_timeout_s` |
| H4 | `apply_effort_kill_prefs` / `apply_user_fusion_pref` → `zeus.kill_switch=True` при global kill |
| H5 | `_note_mini` + `note_dead_model` в panel; `check_alert_stubs` gate-tested |
| H6 | `remember_trace_routing` / `lookup_trace_routing`; feedback `_persist` enrich |
| H7 | Harness: `canary_bars_ok` + `canary_bars_mode`; `bucket_pass_rates` hook for canary→100% |
| H8 | Overflow bonus + sticky skip when `context_chars ≥ overflow_chars` |

## Матрица после фикса

| Story | AC | Notes |
|---|---|---|
| 4.1 Sticky Leader/stack | **PASS** | sticky→pick_leader; Path never sticky; write at end |
| 4.2 Effort + Kill-Switch | **PASS** | me/tg/bot + global kill → `routed_by=kill_switch` |
| 4.3 Shadow + canary + baseline_id | **PASS** | serve baseline under shadow; cohort canary; baseline in observe |
| 4.4 Eval N≥50 + oracle | **PASS*** | suite+oracle; bars documented; enforce when `bucket_pass_rates` filled |
| 4.5 Runtime budgets | **PASS** | presence + light enforce (RPM/sem/timeout) |
| 4.6 Feedback no Elo | **PASS** | enrich by trace; `elo_writeback: false` |
| 4.7 Publish regression gate | **PASS** | router + script; CI process still ops |
| 4.8 Observability | **PASS** | observe+baseline_id; alert stubs wired from panel signals |
| 4.9 Canary-exit ops | **PASS*** | runbook + load-test stub; live signed results still ops freeze |

\* Offline / ops depth: live load-test results and frozen `bucket_pass_rates` remain pre-canary-100% ops items (per epics Notes).

## Gate verdict

**Epic 4 VALIDATED** for MVP ship of sticky/prefs/shadow/eval/budgets/feedback/publish/observe scaffolding.  
Remaining ops debt before canary→100%: fill `bucket_pass_rates`, run signed load-test, wire Onestack exporter beyond in-process counters.

## Commands

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_fusion*.py -q
```
