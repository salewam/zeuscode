# Epic 1 — полная валидация (дыры → фиксы → gate)

**Date:** 2026-07-22  
**Suite:** `test_fusion_routing|result|scrub|onestack|epic1_validation` → **50 passed**  
**Full fusion:** `test_fusion*.py` → see CI note below

## Найденные дыры (до фикса)

| ID | Дыра | AD/AC | Severity |
|---|---|---|---|
| H1 | `_charge_amounts` биллил через `onestack.agents` без FusionResult | AD-14 | **P0** |
| H2 | Serving внутри fusion жил как `fast\|full`; Path только на egress | AD-15 | **P0** |
| H3 | Branch dict без nested `usage` / слабый `model` alias | AD-14 | **P1** |
| H4 | `_monolith` god-module (~2k) | AD-6 | **P2** (долг миграции) |
| H5 | Solo chat: `sanitize` без scrub | AD-17 perimeter | **P2** (вне fusion AC) |

## Что закрыто сейчас

| ID | Фикс |
|---|---|
| H1 | Fusion completions → только FR; без FR — usage totals, **никогда** agents-only |
| H2 | `serving_path` Path enum в `iter_fusion` → `_pack_completion`; `stack_size`/`fusion_mode` = Edge bridge |
| H3 | `BranchUsage.model` + `.usage`; dict branches с nested `usage` |
| — | Gate-тесты: `backend/tests/test_fusion_epic1_validation.py` |

## Матрица после фикса

| Story | AC | AD-6 | AD-8 | AD-10 | AD-14 | AD-15 | AD-17 |
|---|---|---|---|---|---|---|---|
| 1.1 | PASS | PARTIAL* | — | PASS | — | PASS† | — |
| 1.2 | PASS | — | PASS | PASS | PASS | PASS† | — |
| 1.3 | PASS | — | PASS | PASS | PASS | PASS† | — |
| 1.4 | PASS | — | — | PASS | — | — | PASS‡ |

\* `_monolith` ещё центр исполнения — не блокер AC 1.1  
† Serving decision = Path enum; `fast|full` только как `stack_size` Edge adapter  
‡ Fusion Edge→Policy once; solo non-fusion scrub — вне scope

## Gate verdict

**Epic 1 VALIDATED (accept-with-known-debt)**  
- AC 1.1–1.4: **PASS**  
- AD-8/10/14/15/17 для Epic1 surface: **PASS** (после фиксов)  
- AD-6 god-module: **известный долг**, не проваливает story AC  

## Команды

```bash
PYTHONPATH=backend .venv/bin/python -m pytest \
  backend/tests/test_fusion_routing.py \
  backend/tests/test_fusion_result.py \
  backend/tests/test_fusion_scrub.py \
  backend/tests/test_fusion_onestack.py \
  backend/tests/test_fusion_epic1_validation.py -q
```
