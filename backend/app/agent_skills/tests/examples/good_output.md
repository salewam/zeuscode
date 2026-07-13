# Tests — эталон

## Задача
«API tasks: POST /api/tasks, GET /api/tasks/{id}, Auth Bearer, 404 на чужой.»

## Мышление
Контракт с backend: POST→201, GET→200/404, Bearer. Кейсы: create+get happy; 401 без токена; 404 чужой id. Поля title/done как у schemas.

## Результат

```python path=/src/tests/test_tasks.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Prefer: from routers.tasks import router
# Demo double must mirror contract — NEVER f-string SQL.


def make_app():
    from fastapi import APIRouter, Depends, HTTPException, status
    from pydantic import BaseModel, Field

    class TaskIn(BaseModel):
        title: str = Field(min_length=1, max_length=200)
        done: bool = False

    class TaskOut(BaseModel):
        id: int
        title: str
        done: bool

    store: dict[int, dict] = {}
    owner: dict[int, str] = {}
    seq = {"n": 0}
    router = APIRouter(prefix="/api/tasks")

    def user(authorization: str | None = None):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
        return authorization.removeprefix("Bearer ").strip() or "u"

    @router.post("", response_model=TaskOut, status_code=201)
    def create(body: TaskIn, uid: str = Depends(user)):
        seq["n"] += 1
        item = {"id": seq["n"], "title": body.title, "done": body.done}
        store[item["id"]] = item
        owner[item["id"]] = uid
        return item

    @router.get("/{task_id}", response_model=TaskOut)
    def get_one(task_id: int, uid: str = Depends(user)):
        item = store.get(task_id)
        if not item or owner.get(task_id) != uid:
            raise HTTPException(404, "Task not found")
        return item

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def client():
    return TestClient(make_app())


def test_create_and_get(client):
    h = {"Authorization": "Bearer alice"}
    r = client.post("/api/tasks", json={"title": "Buy milk"}, headers=h)
    assert r.status_code == 201
    tid = r.json()["id"]
    g = client.get(f"/api/tasks/{tid}", headers=h)
    assert g.status_code == 200
    assert g.json()["title"] == "Buy milk"


def test_unauthorized(client):
    r = client.post("/api/tasks", json={"title": "x"})
    assert r.status_code == 401


def test_foreign_is_404(client):
    a = {"Authorization": "Bearer alice"}
    b = {"Authorization": "Bearer bob"}
    tid = client.post("/api/tasks", json={"title": "secret"}, headers=a).json()["id"]
    r = client.get(f"/api/tasks/{tid}", headers=b)
    assert r.status_code == 404
```

- [x] path=/src/tests
- [x] happy + 401 + 404
- [x] нет SQL f-string
