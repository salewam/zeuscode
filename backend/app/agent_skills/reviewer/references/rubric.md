# Reviewer — Rubric (anchors)

Оценивай критерий → severity → вклад в вердикт.

**Iron law:** нет claims без evidence (gate finding или цитата `path=` + фрагмент).

## Critical (→ FAIL если в scope)

| Критерий | Якорь FAIL | Не FAIL |
|----------|------------|---------|
| Артефакты | Нет `path=` кода по задаче | Есть path= среза |
| Secrets | sk-/password в ответе клиента/API | JWT из env |
| Injection | SQL f-string в backend **или** tests | ORM/параметры |
| Controls | div onclick как основной UX | button/a |
| Task break | Просили X, артефакты делают противоположное Y | Частичный happy path |

## Major (→ PASS_WITH_RISKS)

| Критерий | Пример |
|----------|--------|
| a11y/AI-look | outline none, indigo, input без label |
| Contract drift | tests path/поля ≠ backend |
| Ownership weak | path-id без 404/user_id сигнала |
| response_model=dict | публичный API |
| Design handoff | design без states/handoff при наличии артефакта |

## Minor / info (не валят gate)

- Нет PATCH, если не просили
- user_id в Out «на вкус»
- Нет rate limit в MVP-срезе
- «Можно улучшить структуру файлов»

## Калибровка

1. Сначала прочитай **задачу** — выпиши must-have (1–5 буллетов).
2. Findings только к must-have или security red flags.
3. Всё остальное → Next или minor.
4. Severity map: critical→FAIL · major→PASS_WITH_RISKS · else→PASS.
