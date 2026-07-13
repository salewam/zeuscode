"""Minimal pytest template — mirror backend contract, never SQL f-string."""

import pytest
from fastapi.testclient import TestClient

# from routers.resource import router
# app = FastAPI(); app.include_router(router)


@pytest.fixture()
def client():
    raise NotImplementedError("Wire TestClient to team router or contract-compatible double")


def test_happy(client: TestClient):
    # r = client.post("/api/...", json={...}, headers={"Authorization": "Bearer u"})
    # assert r.status_code == 201
    assert False, "replace with real happy path"


def test_unauthorized(client: TestClient):
    # r = client.post("/api/...", json={...})
    # assert r.status_code == 401
    assert False, "replace with real negative"
