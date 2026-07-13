# Backend — Anti-patterns → Replace

Каждая строка: **плохо → почему → делай так**. Не рационализируй («потом», «MVP»).

---

## 1. Contract & structure

| Плохо | Почему | Делай |
|-------|--------|--------|
| God-router: auth+billing+projects в одном файле за ход | Несклеимо, ломает review | Один ресурс / один срез |
| Публичный API на сырых `dict` | Нет контракта, ломает клиентов | Pydantic In/Out + `response_model` |
| Менять поля UI молча | Ломает frontend/tests | Следуй UI или явный breaking change |
| Только «идея эндпоинтов» без `path=` | Нет артефакта Studio | Код в `/src/backend/...` |
| 200 + `{success:false}` вместо 4xx | Клиенты не отличить | HTTP status = смысл |
| Код без контракт-таблицы в Мышлении | Hyrum: всё станет зависимостью | method/path/auth/codes сначала |
| List без limit/max | Отдаёт всю таблицу | Query limit + верхняя граница |

## 2. Validation & errors

| Плохо | Почему | Делай |
|-------|--------|--------|
| Ручные `if not body.get("email")` на всё | Дубли, дыры | Pydantic `Field` / `EmailStr` |
| `except Exception: pass` | Глотает баги | Лови конкретное; остальное → 500 лог |
| Stack trace / SQL error клиенту | Утечка + шум | Короткий `detail`, лог на сервере |
| 500 на дубликат unique | Путает ops и UI | 409 Conflict |
| Одна строка `detail="error"` на всё | UI не поможет | Различай 401/404/409/422 |

## 3. Auth & data

| Плохо | Почему | Делай |
|-------|--------|--------|
| Мутации без `Depends(get_current_user)` | Чужие данные | Auth на ресурсных routes |
| `if item.user_id != user.id: 403` всегда | Палит существование id | Обычно 404 |
| Login: «email не найден» vs «неверный пароль» | User enumeration | Одна фраза: invalid credentials |
| Пароль plaintext / обратимое «шифрование» | Компрометация | Hash + verify |
| JWT secret / API key в коде | Утечка | env / settings |

## 4. Data access

| Плохо | Почему | Делай |
|-------|--------|--------|
| `f"SELECT ... {user_id}"` | SQLi | ORM / параметризованные запросы |
| N+1 без нужды на списке | Перф | `selectinload` / join по делу |
| Commit в цикле построчно | Медленно, частично | Одна транзакция на use-case |
| Отдать всю таблицу без лимита | DoS / утечка | Pagination / cap |

## 5. Ops & Studio

| Плохо | Почему | Делай |
|-------|--------|--------|
| Лог `print(password)`, `Authorization` | Секреты в логах | Редактура / не логировать |
| CORS `*` + `allow_credentials=True` | Браузерный риск | Явный origin или пометь риск |
| Микросервисы / Redis / очередь «на вырост» | Оверхед MVP | Монолитный FastAPI пока бриф молчит |
| GraphQL на один CRUD | Сложность | REST, пока нет запроса |

---

## Rationalizations → Reality

| Отмазка | Реальность |
|---------|------------|
| Auth потом | Потом = дыра в проде |
| Валидация в UI достаточна | UI обходят; сервер — источник правды |
| Это черновой API | Черновики утекают в клиентов |
| Dict быстрее Pydantic | Ломает контракт и OpenAPI |
| 403 понятнее 404 на чужой id | Часто палит ресурсы; следуй брифу и security DoD |
