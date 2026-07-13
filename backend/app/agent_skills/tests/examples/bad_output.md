# Tests — антиэталон

## Задача
«API tasks POST/GET с auth.»

## Мышление
Сделаю свой сервер проще, на SQL.

## Результат

```python
@app.post("/todos")
def create(data: dict):
    q = f"INSERT INTO todos (text) VALUES ('{data['text']}')"
    ...
```

```python
@pytest.mark.skip
def test_later():
    pass
```

| Симптом | Нарушение |
|---------|-----------|
| `/todos` + `text` | Не контракт `/api/tasks` + `title` |
| SQL f-string | Security + anti-patterns |
| skip | Запрет |
| Нет path=/src/tests | Нет артефакта |
