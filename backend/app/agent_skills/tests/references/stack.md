# Tests — Stack

```
бриф/backend задаёт стек тестов? → его
иначе → pytest + httpx/TestClient
UI-only задача → лёгкие assert по DOM/строкам или playwright только если просят
```

## Default layout

```text
/src/tests/
  test_<resource>.py
  conftest.py          # optional fixtures
```

## Prefer

1. Import router/schemas from `/src/backend/...` если возможно в артефакте
2. Иначе — минимальный ASGI double с **теми же** path/status/detail
3. Fixtures: auth header, sample payload

## Avoid without request

- Selenium на API-задачу
- Отдельная БД с миграциями «для одного теста»
- Snapshot-тесты всего HTML без нужды
