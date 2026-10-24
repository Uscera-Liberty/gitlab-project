import pytest
from fastapi.testclient import TestClient

from app.db import SEED_USERS
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Для каждого теста — своя чистая БД во временной папке
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_seed_users_present(client):
    users = client.get("/users").json()
    assert len(users) == len(SEED_USERS)
    assert users[0]["email"] == "alice@example.com"
    assert users[0]["role"] == "admin"


def test_pagination(client):
    users = client.get("/users", params={"limit": 2, "offset": 1}).json()
    assert [u["id"] for u in users] == [2, 3]


def test_create_and_get_user(client):
    resp = client.post("/users", json={"name": "Eve", "email": "eve@example.com"})
    assert resp.status_code == 201
    user = resp.json()
    assert user["role"] == "user"

    resp = client.get(f"/users/{user['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Eve"


def test_create_duplicate_email(client):
    resp = client.post("/users", json={"name": "X", "email": "alice@example.com"})
    assert resp.status_code == 409


def test_create_invalid_email(client):
    resp = client.post("/users", json={"name": "X", "email": "not-an-email"})
    assert resp.status_code == 422


def test_update_user(client):
    resp = client.put("/users/2", json={"role": "admin"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "admin"
    assert body["name"] == "Bob Builder"  # не переданные поля не меняются


def test_update_duplicate_email(client):
    resp = client.put("/users/2", json={"email": "alice@example.com"})
    assert resp.status_code == 409


def test_delete_user(client):
    assert client.delete("/users/3").status_code == 204
    assert client.get("/users/3").status_code == 404
    assert len(client.get("/users").json()) == len(SEED_USERS) - 1


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_not_found(client, method):
    kwargs = {"json": {"name": "Z"}} if method == "put" else {}
    resp = getattr(client, method)("/users/999", **kwargs)
    assert resp.status_code == 404
