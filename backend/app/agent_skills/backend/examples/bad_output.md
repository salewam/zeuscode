# Backend — антиэталон (bad_output)

Так **нельзя** отвечать. Если видишь похожее у себя — перепиши до сдачи.

---

## Задача (та же)

«API проектов: создать и получить свой проект. Auth Bearer.»

---

## Мышление

Сделаю быстрый REST на dict, auth добавим потом.

## Результат

Вот идея API:

- POST /projects
- GET /projects/:id

```python
@app.post("/projects")
async def create(data: dict):
    try:
        q = f"INSERT INTO projects (title, user_id) VALUES ('{data['title']}', {data['user_id']})"
        await db.execute(q)
        print("token", data.get("password"))
        return {"ok": True, "password": data.get("password")}
    except Exception:
        return {"ok": False}
```

*(схемы и ownership потом)*

---

## Почему это провал (маппинг на anti-patterns)

| Симптом | Нарушение |
|---------|-----------|
| Нет `path=/src/backend/...` | Нет артефакта Studio |
| «Идея» вместо контракта | Не Результат роли |
| `dict` + нет Pydantic | Contract / validation |
| SQL f-string | Injection |
| Auth потом, user_id из body | AuthZ дыра |
| password в ответе и логе | Secrets |
| `except Exception` → ok:false | Error model |
| Схемы «потом» | Rationalization |

Сравни с `good_output.md`: там In/Out, 201/404, ownership, без секретов.
