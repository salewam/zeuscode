# Backend — Stack

Бриф побеждает этот файл. Если молчит — алгоритм ниже.

---

## Decision tree

```text
1. Бриф/задача явно: Express | Django | Nest | Go | …
   → этот стек; сохрани принципы контракта/ошибок/auth
2. Правим backend ZeusCode (app/routers, models, deps)
   → существующие паттерны: APIRouter, AsyncSession, get_current_user
3. Иначе (новый API / фича / учебный срез)
   → Default stack
```

---

## Default stack

| Слой | Выбор | Запрет без запроса |
|------|--------|-------------------|
| Framework | FastAPI | Flask «потому что проще», Django на один endpoint |
| Schemas | Pydantic v2 (`BaseModel`, `Field`) | Сырые dict на публичном API |
| Async | `async def` + AsyncSession если БД | Sync ORM в async route без нужды |
| Auth | Bearer JWT / Depends | Home-grown crypto, plaintext sessions в ответе |
| DB | SQLAlchemy 2.x async (если нужны данные) | Сырой SQL-строки с интерполяцией |
| HTTP errors | `HTTPException` + status | 200 + ok:false ковром |
| Docs | Авто OpenAPI FastAPI | Писать Swagger руками вместо схем |

### Artifact layout

```text
/src/backend/
  routers/<resource>.py
  schemas/<resource>.py
  services/<resource>.py   # optional
  models.py                # optional
  deps.py                  # optional auth helpers
```

Templates: `../assets/templates/` (`router.py`, `schemas.py`, `service.py`, `deps_auth.py`).

---

## ZeusCode cabinet vs user product

| Контекст | Как писать |
|----------|------------|
| Кабинет / API ZeusCode | Следуй `app/routers/*`, `get_db`, `get_current_user`, стилю `HTTPException(status, detail)` |
| Продукт из задачи пользователя | Default stack; **не** тащи биллинг/Kie/Ultra в чужой домен |

---

## REST conventions (default)

| Действие | Method | Path | Success |
|----------|--------|------|---------|
| List | GET | `/api/resources` | 200 list / page |
| Get | GET | `/api/resources/{id}` | 200 / 404 |
| Create | POST | `/api/resources` | 201 + body |
| Update | PATCH | `/api/resources/{id}` | 200 / 404 |
| Replace | PUT | `/api/resources/{id}` | 200 / 404 |
| Delete | DELETE | `/api/resources/{id}` | 204 или 200 |

Префикс `/api` — если бриф/frontend уже так; иначе согласуй в Мышлении.

Pagination (если список может расти): `limit` (default 20, max 100) + `offset` или cursor.

---

## Error model

Предпочтительно:

```json
{ "detail": "Project not found" }
```

Или структурированно, если бриф просит:

```json
{ "detail": { "code": "project_not_found", "message": "Project not found" } }
```

Не смешивай оба стиля в одном срезе без причины.

---

## When to add a service layer

- Правила > ~15 строк
- Один use-case зовётся из 2+ routes
- Нужны транзакции / несколько моделей

Иначе тонкий router + schema достаточно.
