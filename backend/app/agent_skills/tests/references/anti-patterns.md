# Tests — Anti-patterns

| Плохо | Почему | Делай |
|-------|--------|--------|
| Свой FastAPI + `f"SELECT...{id}"` | SQLi + не контракт команды | TestClient к `/src/backend` или совместимый double |
| Поля `text` при backend `title` | Ломает склейку | Копируй схемы |
| Ожидание 403 при backend 404 ownership | Ложный баг | Статус из backend Мышления |
| Тест без `assert` / только print | Фальшь | assert status + body |
| `assert True` / `assert 1` / голый `pass` | Vacuous — не доказывает контракт | assert status_code + json fields |
| `@pytest.mark.skip` | Долг | Убери или почини |
| Полный CRUD тесты на задачу «только POST+GET» | Scope creep | Только запрошенное |
| Дублировать auth «проще» без Bearer | Дыра | Как в контракте |
| 200 + `{ok:false}` в mock-router | Анти-паттерн API | HTTP status |
| Только `assert mock.called_with` | Ломается при рефакторе | Assert на исход (state) |
| Фикс бага без RED-теста | Нет Prove-It | Сначала падающий тест на симптом |
