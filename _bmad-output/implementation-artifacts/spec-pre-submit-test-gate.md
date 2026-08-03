---
title: 'Ролевой test-gate ZeusCode перед submit'
type: 'refactor'
created: '2026-08-01'
status: 'done'
baseline_commit: '172dfb8d829d7ae8d4ae86a15363e9facf6a4508'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/spec-adaptive-zeus-crew.md'
  - '.cursor/rules/zeuscode-product.mdc'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Инкрементальный coding-контур ZeusCode может принять команду submit после успешного repro или простого `git diff`, не запустив релевантный тест. Роли также назначены неточно: GPT выполняет часть test-author работы, Grok 4.5 не участвует, а DeepSeek получает только часть ошибочных логов.

**Approach:** Закрепить специализацию: Opus 4.6 руководит задачей, GPT-5.4 пишет production-код, Grok 4.5 проектирует и проверяет тесты, DeepSeek анализирует машинные логи и возвращает коррекцию GPT. Добавить обязательный event-driven gate, который перехватывает преждевременный submit и требует зелёный релевантный тест после последнего изменения diff.

## Boundaries & Constraints

**Always:** Каждый tool-result бесплатно разбирается детерминированным анализатором и сохраняется как machine evidence. DeepSeek вызывается на ошибке, traceback, pytest/build summary, подозрительном предупреждении и перед submit; его вывод адресуется GPT. Grok включается после появления diff для выбора теста и перед submit для проверки покрытия. Submit разрешён только при непустом diff и успешном релевантном тесте, выполненном после последнего изменения. Роли имеют health-aware failover внутри своей функции.

**Ask First:** Изменение публичного `/v1` API, формата mini-swe, серверное исполнение пользовательских команд или превращение всех четырёх ролей в обязательные LLM-вызовы на каждом tool-turn.

**Never:** Не позволять DeepSeek писать production-код по умолчанию. Не отдавать test-author роль GPT при здоровом Grok 4.5. Не вызывать Opus после каждого shell/read/edit. Не считать repro, `git diff`, импорт или exit code 0 доказательством прохождения тестов. Не блокировать некодовые ответы требованием pytest.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|---------------------------|----------------|
| Преждевременный submit | Bash tool-call содержит submit-marker, diff есть, тестов после diff нет | Submit заменяется запросом релевантного теста от Grok | Gate RED, причина и test command сохраняются |
| Зелёный submit | Релевантный тест после последнего diff завершился с code 0 | Исходный submit tool-call проходит без изменения | Evidence прикладывается к telemetry |
| Красный тест | Pytest/build вернул non-zero или failures | DeepSeek сжимает лог в correction для GPT; GPT исправляет код | Grok обновляет тест только если неверен тестовый контракт |
| Модель недоступна | Grok/DeepSeek unhealthy или timeout | Используется role-appropriate fallback | Состояние degraded; запрет submit не снимается |
| Некодовая задача | Нет diff и submit-marker | Новый gate не запускается | Текущий adaptive path сохраняется |

</frozen-after-approval>

## Code Map

- `backend/app/fusion/roles.py` -- закрепление Opus/GPT-5.4/Grok-4.5/DeepSeek и role-specific fallback.
- `backend/app/fusion/crew.py` -- отдельное назначение test verifier без отказа от адаптивной активации ролей.
- `backend/app/fusion/verify.py` -- извлечение pytest/build/diff evidence из tool messages и решение pre-submit gate.
- `backend/app/fusion/_monolith.py` -- перехват submit tool-call, вызов Grok/DeepSeek по событиям и доставка correction GPT.
- `backend/app/fusion/policy.py` -- tool-output сигналы и устранение ложного security-tier от SWE boilerplate.
- `backend/scripts/world_bench/mini_swe_zeus.yaml` -- API base без жёсткой привязки к порту 8080.
- `backend/tests/test_fusion_adaptive_crew.py` -- контракты ролей, evidence, submit guard и incremental budget.

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/fusion/roles.py`, `backend/app/fusion/crew.py` -- назначить production doer=`gpt-5.4`, test author/verifier=`grok-4.5`, log analyst=`deepseek-v4-pro`, leader=`claude-opus-4-6`; сохранить health-aware fallback.
- [x] `backend/app/fusion/verify.py` -- добавить детерминированное извлечение test/diff evidence и проверку свежести зелёного теста относительно diff.
- [x] `backend/app/fusion/_monolith.py` -- блокировать submit-marker без свежего GREEN, направлять Grok test-plan и DeepSeek correction в следующий GPT tool-turn.
- [x] `backend/app/fusion/policy.py` -- классифицировать pytest failures из tool output и не повышать SWE-задачу до security из-за общего шаблона.
- [x] `backend/scripts/world_bench/mini_swe_zeus.yaml` -- сделать endpoint настраиваемым, чтобы benchmark не конфликтовал с другими live suites.
- [x] `backend/tests/test_fusion_adaptive_crew.py` -- покрыть матрицу и replay неудачного `astropy-11693`.

**Acceptance Criteria:**
- Given submit tool-call без pytest после последнего diff, when Zeus обрабатывает ответ доера, then submit не доходит до клиента, Grok предлагает релевантный test command, а gate становится RED.
- Given красный pytest tool-result, when начинается следующий turn, then DeepSeek формирует краткую диагностическую correction, GPT получает её, а Opus не вызывается.
- Given свежий зелёный релевантный тест и непустой diff, when GPT вызывает submit, then tool-call проходит и telemetry содержит использованные роли и evidence.
- Given обычные успешные read/edit/tool turns, when нет submit-кандидата и ошибки, then Grok, DeepSeek и Opus не вызываются, сохраняя быстрый doer-only path.

## Design Notes

«DeepSeek всегда смотрит логи» реализуется без LLM-вызова на каждый shell chunk: детерминированный слой всегда читает и сохраняет все результаты, а DeepSeek получает только семантически значимые события. Это сохраняет постоянный аналитический контроль, но не возвращает прежнюю стоимость полного crew на каждом ходе.

Реестр команды фиксирован, активация остаётся адаптивной: bootstrap = Opus+GPT; обычный tool-loop = GPT; test candidate = Grok+GPT; RED = DeepSeek+GPT; спорный повторный RED или высокий риск = Opus+остальные нужные роли.

## Verification

**Commands:**
- `PYTHONPATH=backend .venv/bin/pytest -q backend/tests/test_fusion_adaptive_crew.py backend/tests/test_fusion_crew_watch.py backend/tests/test_openai_tools_protocol.py` -- роли, gate и tool protocol проходят.
- `PYTHONPATH=backend .venv/bin/python -m py_compile backend/app/fusion/roles.py backend/app/fusion/crew.py backend/app/fusion/verify.py backend/app/fusion/_monolith.py` -- изменённые модули компилируются.
- Replay `astropy__astropy-11693` до submit -- преждевременный patch блокируется до запуска целевого pytest.

## Spec Change Log

## Suggested Review Order

**Submit boundary**

- Перехватывает реальный mini-swe marker и сериализует submit отдельно от других tools.
  [`_monolith.py:3277`](../../backend/app/fusion/_monolith.py#L3277)

- Требует непустой diff и свежий релевантный GREEN после последней мутации.
  [`verify.py:1201`](../../backend/app/fusion/verify.py#L1201)

**Evidence and command safety**

- Детерминированно отслеживает diff/test/build, freshness, replay и неизвестные shell-мутации.
  [`verify.py:966`](../../backend/app/fusion/verify.py#L966)

- Разрешает Grok только один безопасный прямой test command без shell-программы.
  [`verify.py:894`](../../backend/app/fusion/verify.py#L894)

**Role topology and state**

- GPT пишет production-код; Grok тестирует; Opus руководит; DeepSeek анализирует логи.
  [`roles.py:48`](../../backend/app/fusion/roles.py#L48)

- Игнорирует клиентский crew-state и доверяет только server-owned sticky state.
  [`chat.py:227`](../../backend/app/routers/chat.py#L227)

**Benchmark and regression proof**

- SWE по умолчанию проверяет adaptive ZeusCode и использует настраиваемый endpoint.
  [`mini_swe_zeus.yaml:15`](../../backend/scripts/world_bench/mini_swe_zeus.yaml#L15)

- Replay Astropy доказывает freshness относительно последнего diff.
  [`test_fusion_adaptive_crew.py:250`](../../backend/tests/test_fusion_adaptive_crew.py#L250)

- Интеграционный тест проверяет замену premature mini-swe submit.
  [`test_fusion_adaptive_crew.py:1580`](../../backend/tests/test_fusion_adaptive_crew.py#L1580)
