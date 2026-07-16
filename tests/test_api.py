from fastapi.testclient import TestClient

from mplacas.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"]


def test_request_id_header_is_preserved_when_safe() -> None:
    response = TestClient(app).get("/health", headers={"X-Request-ID": "audit-123"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "audit-123"


def test_request_id_header_is_replaced_when_unsafe() -> None:
    response = TestClient(app).get("/health", headers={"X-Request-ID": "bad id"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "bad id"
    assert len(response.headers["x-request-id"]) == 32


def test_ready_does_not_expose_secrets() -> None:
    response = TestClient(app).get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert "password" not in str(body).lower()
    assert "token" not in str(body).lower()
