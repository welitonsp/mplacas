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


def test_cloud_trace_context_is_propagated_to_response_and_request_log(caplog) -> None:
    trace_id = "0123456789abcdef0123456789abcdef"
    caplog.set_level("INFO", logger="mplacas.main")

    response = TestClient(app).get(
        "/health",
        headers={"X-Cloud-Trace-Context": f"{trace_id}/74;o=1"},
    )

    assert response.status_code == 200
    assert response.headers["x-trace-id"] == trace_id
    matching = [record for record in caplog.records if record.message == "http_request_completed"]
    assert matching[-1].trace_id == trace_id
    assert matching[-1].span_id == "000000000000004a"
    assert matching[-1].trace_sampled is True


def test_ready_does_not_expose_secrets() -> None:
    response = TestClient(app).get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert "password" not in str(body).lower()
    assert "token" not in str(body).lower()
