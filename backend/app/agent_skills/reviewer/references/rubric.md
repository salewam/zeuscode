# Reviewer — Rubric (anchors)

Оценивай критерий → severity → вклад в вердикт.

**Iron law:** нет claims без evidence (gate finding или цитата `path=` + фрагмент).

**Uniqueness:** не вали за «нет `.btn` / sticky / Georgia / `#vitrine`», если смысл закрыт иначе и бриф UNIQUE. Вали за пустоту, ложь, AI-look, клон чужого бренда.

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
| a11y/AI-look | outline none, indigo, Inter, input без label |
| Contract drift | tests path/поля ≠ backend |
| Ownership weak | path-id без 404/user_id сигнала |
| response_model=dict | публичный API |
| Design handoff | design без states/handoff при наличии артефакта |
| **Landing ship** | `missing_asset` / `placeholder_contact` / `api_orphan` / `fake_form_success` / `broken_css_import` / `no_hero_media` / `thin_landing` / `empty_hero` / `weak_media` / `thin_deck` / `missing_zeus_badge` / `clone_*` |
| Form lie | success copy в `catch` или «принята» без fetch |
| Dead booking | FE `fetch('/api/booking')` без backend route |
| Fake phone | `000-00-00` / example.com в UI |
| Ghost media | `url(assets/hero…)` без файла в артефактах |
| Empty hero | solid/gradient hero без предметного media |
| Thin shell | пустая оболочка без секций/оффера |
| No Zeus badge | нет «Сделано на ZeusCode» |
| Clone stamp | чужой бренд/адрес эталона при другом брифе |
| No motion | нет transition+:hover (или иного явного motion) |
| No mobile | нет @media max-width |
| Thin deck | слишком мало содержательных слайдов |

## Minor / info (не валят gate)

- Нет sticky / нет Georgia — если chrome и type всё равно читаемые
- Нет `class=btn` — если CTA через button/a с нормальными стилями
- Нет `#vitrine` — если media-ряд сделан иначе
- Нет PATCH, если не просили
- Grammar / мелкий копирайт (если не egg_copy)

## Калибровка

1. Сначала прочитай **задачу** — выпиши must-have (1–5 буллетов).
2. Findings только к must-have или security / landing-ship red flags.
3. Лендинг: телефон, media, fetch honesty, UNIQUE брифа.
4. Не требуй один визуальный штамп (sticky+Georgia+янтарь) для всех ниш.
5. Severity map: critical→FAIL · major→PASS_WITH_RISKS · else→PASS.
