# Backend — Definition of Done

Задача **не сдана**, пока пункты не закрыты или явно `N/A` + причина в ## Мышлении.

Планка по режиму — в конце.

---

## A. Acceptance

- [ ] API закрывает формулировку задачи (не «похожий CRUD»)
- [ ] Happy path воспроизводим: method + path + body → ожидаемый JSON/status
- [ ] Один ход = один ресурс или один связный срез (не весь продукт)

## B. Contract

- [ ] В ## Мышлении: method, path, auth, request, response, ключевые 4xx
- [ ] Имена полей стабильны и согласованы с frontend-артефактом (если есть)
- [ ] `response_model` / явная Out-схема на публичных успешных ответах
- [ ] Статусы осмысленны: 200/201/204, 400/401/403/404/409/422, 500 только на сбои

## C. Validation & edge cases

- [ ] Вход через Pydantic (`BaseModel` + `Field`); длины, email, enum — в схеме
- [ ] Пустые/слишком длинные строки отвергаются
- [ ] Conflict (дубликат unique) → 409, не 500
- [ ] Not found → 404 с понятным `detail`
- [ ] Unauthorized / invalid credentials → 401 (без утечки «email существует», если login)

## D. Auth & ownership

- [ ] Эндпоинты с данными юзера требуют auth (`Depends`)
- [ ] Ownership: чужой ресурс → 404 (предпочтительно) или явный 403 по брифу
- [ ] Нет «auth потом» на мутациях пользовательских данных

## E. Security

- [ ] Нет секретов / паролей / raw JWT secret в артефакте
- [ ] Пароли только hash; сравнение через verify helper
- [ ] Нет SQL через f-string / конкатенацию
- [ ] Логи не печатают password / token / Authorization
- [ ] CORS `*` + credentials не без пометки риска в Мышлении

Детали security — см. раздел E и skill `references/security.md` (оркестратор подгрузит в ultra+).

## F. Code artifact

- [ ] Fenced blocks с `path=/src/backend/...`
- [ ] Router тонкий; жирная логика в service (если > ~15 строк правил)
- [ ] Импорты реалистичны; нет псевдо-`from magic import stuff` без файла
- [ ] Файл не god-object 400+ строк без разбиения

## G. Studio handoff

- [ ] Frontend может собрать fetch по контракту из Мышления + схем
- [ ] Tests: стабильные path/status/`detail` для ассертов
- [ ] Breaking change относительно UI назван явно

## H. Режимная планка

| Режим | Минимум |
|--------|---------|
| light | A + B (кратко) + F (path) + happy + базовая валидация |
| standard | A–G без глубокого threat-model; C и D обязательно |
| ultra | A–G полностью + anti-patterns жёстко + security |
| premium | ultra + сверка с `examples/good_output.md` + security self-check |

## Ещё не done (стоп-фразы)

- «auth потом» / «валидацию добавим» / «это черновик API»
- описание эндпоинтов без кода с `path=`
- `except Exception: return {"ok": false}`
- пароль в ответе или в логе
- один handler на весь продукт
