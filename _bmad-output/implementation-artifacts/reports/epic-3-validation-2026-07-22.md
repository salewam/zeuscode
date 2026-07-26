# Epic 3 — полная валидация (дыры → фиксы → gate)

**Date:** 2026-07-22  
**Suite:** `test_fusion*.py` → **139 passed** (incl. `test_fusion_epic3_validation.py`)

## Найденные дыры (до фикса)

| ID | Дыра | Severity |
|---|---|---|
| H1 | `serving_path` RACE/FULL мог уйти в brownfield FULL (без Aspects/Judge) | **P0** |
| H2 | F13: `zeus.path=RACE` на heavy не clamp | **P0** |
| H3 | `cancel_event` не прокинут из chat SSE | **P0** |
| H4 | `PanelDiversityError` → сырой 500 | **P1** |
| H5 | `anti_bias_fail` только meta, не release gate | **P1** |
| H6 | CASCADE без prompt adapt | **P1** |
| H7 | Prompt adapt не в publish/regression helpers | **P1** |

## Что закрыто

| ID | Фикс |
|---|---|
| H1 | Dispatcher: `serving_path∈{CASCADE,RACE,FULL}` или `resolved=full` → всегда Epic executors |
| H2 | `clamp_f13_never_race_on_heavy` в override + serving |
| H3 | `iter_fusion(cancel_event=…)`; chat SSE `cancel_event.set()` on disconnect |
| H4 | Catch → HTTP 502 structured diversity disaster |
| H5 | Onestack `anti_bias_fail` + `release_blocked`; `check_release_not_anti_bias` |
| H6 | `execute_cascade(adapt_prompts=True)` |
| H7 | `check_prompt_adapt_contract` in `publish_gate.py` |

## Матрица после фикса

| Story | AC | Notes |
|---|---|---|
| 3.1 RACE + both-fail | **PASS** | + F13 clamp |
| 3.2 FULL Brief/Aspects/τ | **PASS** | diversity handled |
| 3.3 Rank+Judge+anti-bias | **PASS** | release gate helper |
| 3.4 Soft-Stop/cancel | **PASS** | Edge cancel wired |
| 3.5 Prompt adapt | **PASS** | CASCADE + contract check |

## Gate verdict

**Epic 3 VALIDATED** (known debt: Aspects still heuristic-default without LLM; anti-bias blocks publish helper — must be called by CI/publish path).

## Commands

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_fusion*.py -q
```
