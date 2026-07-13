from fastapi import FastAPI
from fastapi.testclient import TestClient


def build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/items/{item_id}")
    def get_item(item_id: int) -> dict[str, int | str]:
        if item_id != 1:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Item not found")
        return {"id": item_id, "title": "Example"}

    return app


def test_health_happy_path() -> None:
    client = TestClient(build_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_item_not_found_negative() -> None:
    client = TestClient(build_app())

    response = client.get("/api/items/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Item not found"
