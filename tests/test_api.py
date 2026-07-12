from fastapi.testclient import TestClient

from mplacas.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_does_not_expose_secrets() -> None:
    response = TestClient(app).get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert "password" not in str(body).lower()
    assert "token" not in str(body).lower()
