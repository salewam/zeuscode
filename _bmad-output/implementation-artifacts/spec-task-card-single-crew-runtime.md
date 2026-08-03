---
title: 'Task Card и единый модельный контур ZeusCode'
type: 'refactor'
created: '2026-08-01'
status: 'in-review'
review_loop_iteration: 0
baseline_commit: '172dfb8d829d7ae8d4ae86a15363e9facf6a4508'
context:
  - '/Users/money/Desktop/Projects/ultra-mode-mvp/_bmad-output/implementation-artifacts/spec-adaptive-zeus-crew.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Runtime ZeusCode одновременно содержит рабочую crew-архитектуру и старый автоматический слой FAST/CASCADE/RACE/FULL, regex-классификацию и дублирующую таблицу ролей. Это усложняет исполнение и телеметрию, а неструктурированный `plan_digest` не является долговечной карточкой задачи.

**Approach:** Оставить один путь «Task Card → бригада → детерминированные гейты». Opus создаёт карточку каждой coding-задачи; для серьёзной задачи GPT 5.4 один раз критикует черновик, затем Opus выпускает финальную карточку. Цель — снизить p50 latency минимум на 50% без потери качества.

## Boundaries & Constraints

**Always:** Opus владеет Task Card; GPT пишет код и критикует серьёзный план; Grok 4.5 отвечает за тесты; DeepSeek — только за свежие ошибки. Карточка хранит цель, мотивацию, scope, тест, критерии готовности и поручения. Простая задача получает compact card; серьёзная — draft → critique → final. Карточка персистентна, tenant-isolated и служит cache-stable prefix. Код активирует роль лишь по факту: новая задача, diff без теста или свежая ошибка.

**Ask First:** Изменение публичного API/биллинга, ослабление submit/test/security gates, удаление совместимости, которую реально использует внешний клиент.

**Never:** Не исполнять FAST/CASCADE/RACE/FULL; не выбирать модели через regex/power-score; не вызывать DeepSeek по старой ошибке; не ослаблять гейты; не заявлять 2× без замера.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Простая coding-задача | Новый tool-enabled запрос | Opus создаёт компактную карточку, GPT начинает работу | При отказе Opus — безопасная минимальная карточка и degraded telemetry |
| Серьёзная coding-задача | Риск/масштаб подтверждён | Opus draft → GPT critique → Opus final → GPT action | Ошибка критика не блокирует; ставится degraded |
| Свежий failed tool event | Ненулевой exit/traceback | DeepSeek разбирает только свежий лог, результат привязан к карточке | После успешного следующего шага finding закрывается |
| Diff без свежего теста | Изменение после последнего GREEN | Grok выбирает безопасную тест-команду | Детерминированная fallback-цепочка и существующий fail-open лимит |

</frozen-after-approval>

## Code Map

- `backend/app/fusion/task_card.py` — структура, валидация и промпты карточки.
- `backend/app/fusion/project_memory.py` — сохранение/получение карточек и outcome аналитика.
- `backend/app/fusion/crew.py` — один roster и классификация хода.
- `backend/app/fusion/_monolith.py` — bootstrap draft/critique/final и единый incremental runtime.
- `backend/app/fusion/panel.py` — cache-stable Task Card prefix и bounded model calls.
- `backend/app/fusion/pipeline.py` — bootstrap/incremental/kill-switch.
- `backend/app/fusion/policy.py` — оставить только machine/turn signals.
- `backend/app/fusion/roles.py` — свести к одному crew roster и сохранить client aliases/API.
- `backend/app/fusion/model_power.py` — убрать из coding routing; оставить UI author/critic выбор.
- `backend/app/fusion/metrics.py` — latency по фазам и usefulness DeepSeek.

## Tasks & Acceptance

**Execution:**
- [x] Ввести типизированную Task Card, безопасный parser/fallback и tenant-isolated persistence.
- [x] Реализовать compact bootstrap и serious draft → GPT critique → Opus final с конкретными role assignments.
- [x] Заменить отдельный size-4 specialist critique на GPT critique внутри full Task Card, чтобы не добавлять четвёртый planning-вызов.
- [x] Перевести doer/verifier/analyst на финальную карточку как единый контракт и стабильный кэш-префикс.
- [x] Удалить исполняемый legacy routing и дублирующую role topology, сохранив только доказанно нужные внешние контракты.
- [x] Закрывать findings DeepSeek по следующему успешному событию и считать accepted/resolved/irrelevant outcomes.
- [x] Сначала выводить тест из memory/plan/paths, звать Grok лишь при неоднозначности; analyst и verifier запускать параллельно.
- [x] Требовать tool call с первого doer-вызова, переиспользовать analyst report по evidence hash и сжимать старые tool logs без потери error tail.
- [ ] Обновить focused/regression тесты и benchmark latency/quality.

**Acceptance Criteria:**
- Given любой новый coding request, when начинается bootstrap, then существует сохранённая валидная Task Card с явными поручениями.
- Given серьёзная задача, when bootstrap завершён, then телеметрия доказывает ровно один critique GPT и финальную revision Opus.
- Given tool loop, when выбирается следующий участник, then решение не зависит от FAST/CASCADE/RACE/FULL, regex task label или power score.
- Given свежая ошибка, when DeepSeek выдаёт finding и следующий шаг исполняется, then finding получает outcome, а старый failure больше не вызывает аналитика.
- Given benchmark, when сравниваются версии, then p50 latency ≤50% baseline, cache hit не хуже, тесты проходят, SWE-bench 1–5 не теряет resolved задачи.

## Spec Change Log

## Design Notes

Критика добавляет два вызова лишь серьёзным задачам. Ускорение строится на сокращении последующих пустых ходов, Grok-вызовов при уже известном тесте, повторных аналитиков и полного log-контекста. 2× проверяется отдельно для multi-model turns и end-to-end; результат нельзя объявлять заранее.

## Verification

**Commands:**
- `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_fusion_adaptive_crew.py -q` -- все focused тесты проходят.
- `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q` -- нет новых regression failures.
- `.venv/bin/python backend/scripts/smoke_prompt_cache.py` -- cache hit не ниже текущего live baseline.
- SWE-bench tasks 1–5 через официальный harness -- resolved count не ниже baseline; task 1 остаётся resolved.
- Latency smoke/benchmark до и после -- p50 end-to-end ≤50% baseline с разбивкой draft/critique/final/doer/analyst/verifier.
