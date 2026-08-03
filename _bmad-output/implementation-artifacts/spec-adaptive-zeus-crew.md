---
title: 'Адаптивная бригада ZeusCode 2/3/4'
type: 'refactor'
created: '2026-07-31'
status: 'done'
baseline_commit: '172dfb8d829d7ae8d4ae86a15363e9facf6a4508'
review_loop_iteration: 0
context:
  - 'docs/TZ_ZEUSCODE_CREW_AND_RIG.md'
  - '.cursor/rules/zeuscode-product.mdc'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** ZeusCode пересобирает полную бригаду на каждом ходе клиентского tool-loop: кодерская команда проходит research, планирование, несколько доеров и повторную проверку до выдачи `tool_calls`. Это даёт 11–20 LLM-вызовов на ход, высокую цену и отсутствие прогресса в SWE-bench.

**Approach:** Сделать единую stateful-оркестрацию: один раз определить задачу и закрепить бригаду из 2, 3 или 4 ролей, а последующие tool-result ходы выполнять коротким контуром. Opus 4.6 ставит и корректирует задачу, GPT выполняет кодерскую работу, DeepSeek анализирует ошибки/проверяет, четвёртая модель подключается только как профильный специалист.

## Boundaries & Constraints

**Always:** Все запросы `zeuscode` входят в один crew-контур; клиент остаётся руками, сервер — мозгом и биллингом. План, текущий шаг, роли, машинные сигналы, бюджеты и эскалации сохраняются на задачу. Tool-loop продолжение вызывает только необходимые роли. Решение «готово» опирается на тесты/build/compile/diff, а не самооценку доера. Модели разных школ выполняют разные роли; отказ модели заменяет модель в той же роли либо честно понижает состав.

**Ask First:** Изменение публичного API `/v1`, схемы БД вне существующего sticky-state, удаление старых pipeline-модулей, включение серверного исполнения пользовательских инструментов.

**Never:** Не возвращать скрытый solo-remount. Не запускать research для обычного code/tool turn без явной потребности в сети. Не переносить клиентский agent-loop на сервер. Не вызывать все роли на каждом `read/bash/edit`. Не использовать термин или механику каскада как продуктовую архитектуру.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Простая задача | Новый ясный запрос, один файл, низкий риск | Бригада 2; ведущий + доер; машинный гейт | При провале теста расширить до 3 |
| Обычный код/дебаг | Новый code-запрос или traceback | Бригада 3; ведущий + доер + аналитик/верификатор | RED возвращает конкретную коррекцию доеру |
| Высокий риск | Auth/DB/API/security/migration/несколько подсистем | Бригада 4 с профильным специалистом | Не более двух циклов исправления, затем честный soft-stop |
| Tool continuation | История содержит `tool_calls` и `role=tool`, задача сохранена | Не запускать research/clarifier/v1 заново; выдать следующий tool call за ≤3 LLM-вызова | При утраченном состоянии безопасно восстановить краткий план |
| Модель недоступна | Primary роли unhealthy/empty/timeout | Failover внутри роли без разрастания бригады | Отметить degraded и не выдавать пустой ответ |

</frozen-after-approval>

## Code Map

- `backend/app/fusion/crew.py` -- типы состояния задачи, определение хода и выбор состава 2/3/4.
- `backend/app/fusion/policy.py` -- детерминированные сигналы типа, риска и сложности.
- `backend/app/fusion/session.py` -- сериализация состояния бригады в существующий sticky `phase_meta`.
- `backend/app/routers/chat.py` -- загрузка и сохранение crew-state вокруг `/v1`.
- `backend/app/fusion/pipeline.py` -- выбор адаптивного pipeline вместо `always_crew`.
- `backend/app/fusion/_monolith.py` -- разделение bootstrap и короткого tool-loop.
- `backend/app/fusion/research_crew.py` -- research только по явному сетевому сигналу.
- `backend/app/fusion/verify.py` -- переиспользование машинных сигналов без повторных architect/test-author вызовов.
- `backend/tests/test_fusion_adaptive_crew.py` -- матрица состава, продолжений, бюджетов и отказов.

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/fusion/crew.py` -- добавить `TurnKind`, `CrewDecision`, `CrewSession`, выбор 2/3/4 и merge машинных сигналов.
- [x] `backend/app/fusion/policy.py` -- определить bootstrap/tool-loop/exec-feedback и risk-сигналы без отдельного дорогого LLM.
- [x] `backend/app/fusion/session.py`, `backend/app/routers/chat.py` -- сохранять crew-state и восстанавливать его между ходами.
- [x] `backend/app/fusion/pipeline.py` -- заменить безусловный v1 на адаптивное решение; kill-switch оставить аварийным.
- [x] `backend/app/fusion/_monolith.py` -- коротко обрабатывать продолжение: один tool-aware доер, условный log/verifier, без полного планирования.
- [x] `backend/app/fusion/research_crew.py`, `backend/app/fusion/verify.py` -- убрать research-on-code и дубли architect/test-author.
- [x] `backend/tests/test_fusion_adaptive_crew.py` и существующие routing-тесты -- закрепить матрицу и отсутствие solo-remount.

**Acceptance Criteria:**
- Given сохранённая code-задача, when приходит tool-result, then research, clarifier и pipeline-v1 не запускаются, а ответ использует не более трёх LLM-веток.
- Given простой, обычный и высокорисковый запросы, when Zeus классифицирует их, then выбираются соответственно 2, 3 и 4 разные роли с объяснимой причиной.
- Given провал тестов, when приходит `zeus.exec`, then ошибка сохраняется, аналитик формирует коррекцию, а «готово» блокируется до зелёного машинного сигнала.
- Given недоступную модель, when выбирается бригада, then роль получает допустимый failover или состояние `degraded`, но запрос не становится solo и не возвращает пустой ответ.
- Given tool-enabled streaming request, when доер вызывает инструмент, then OpenAI-совместимые `tool_calls` и `finish_reason=tool_calls` доходят до клиента.

## Design Notes

Количество моделей определяется на задачу, но роли вызываются по событиям. Ведущий планирует один раз и возвращается при RED/конфликте/финале; доер ведёт инструментальный цикл; проверяющий включается после ошибки, патча или теста; четвёртый специалист существует только для профильного риска.

## Verification

**Commands:**
- `PYTHONPATH=backend .venv/bin/pytest -q backend/tests/test_fusion_adaptive_crew.py backend/tests/test_zeus_no_agent_tools_remount.py` -- матрица и tool protocol проходят.
- `PYTHONPATH=backend .venv/bin/pytest -q backend/tests/test_fusion_role_routing_epic*.py backend/tests/test_fusion_crew_watch.py backend/tests/test_research_crew_and_ui_live.py` -- существующие контракты согласованы.
- `PYTHONPATH=backend .venv/bin/python -m py_compile backend/app/fusion/crew.py backend/app/fusion/_monolith.py backend/app/fusion/pipeline.py` -- синтаксис корректен.
- SWE-bench `0:1`, затем `0:5` -- все задачи завершаются submit; фиксируются latency, LLM calls, tool schema, cost/task и resolved rate.

## Spec Change Log

## Verification Results

- Focused and routing regression suite: **166 passed**.
- Live `/v1` normal turn: bootstrap **2 branches**, continuation **1 branch**, no research.
- Live RED turn: analyst failover + doer **3 branches**, `exec_feedback`, degraded reported.
- SWE-bench `0:1`: **Submitted 1/1** in 6:13 with 13 API calls; official result **0/1 resolved**.
- SWE failure exposed missing tool-returncode routing; fixed and verified live after the run.
- SWE-bench `0:5` intentionally not started after the unresolved first sample.

## Suggested Review Order

**Adaptive crew entry point**

- Deterministic 2/3/4 selection keeps roles, health, evidence, and budgets truthful.
  [`crew.py:264`](../../backend/app/fusion/crew.py#L264)

- Pipeline maps each selected crew into bootstrap or incremental execution.
  [`pipeline.py:37`](../../backend/app/fusion/pipeline.py#L37)

**Task state and tool protocol**

- Opus seeds the plan once; specialists advise only high-risk bootstrap turns.
  [`_monolith.py:2331`](../../backend/app/fusion/_monolith.py#L2331)

- Tool continuations reuse state and never exceed three internal branches.
  [`_monolith.py:2794`](../../backend/app/fusion/_monolith.py#L2794)

- Automatic and explicit sessions are namespaced per API key.
  [`chat.py:120`](../../backend/app/routers/chat.py#L120)

- Atomic sticky merges preserve concurrent evidence, plans, and counters.
  [`session.py:319`](../../backend/app/fusion/session.py#L319)

**Role collaboration and gates**

- Specialist checks feed analyst contracts and the doer's implementation brief.
  [`pipeline_v1.py:279`](../../backend/app/fusion/pipeline_v1.py#L279)

- Machine evidence, including exit codes, blocks false GREEN results.
  [`verify.py:705`](../../backend/app/fusion/verify.py#L705)

- Code research requires an actual URL, web, latest, or official-doc signal.
  [`research_crew.py:93`](../../backend/app/fusion/research_crew.py#L93)

**Tests**

- Matrix, failures, concurrency, budgets, tool protocol, and no-solo behavior.
  [`test_fusion_adaptive_crew.py:23`](../../backend/tests/test_fusion_adaptive_crew.py#L23)

