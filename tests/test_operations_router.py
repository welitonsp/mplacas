from fastapi.testclient import TestClient

from mplacas.core.config import get_settings
from mplacas.main import app
import mplacas.operations.router as operations_router


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeJobRunRepository:
    def __init__(self, session) -> None:
        self.session = session

    async def list_recent(self, limit: int = 20) -> list[object]:
        return []


def test_operations_endpoints_require_operational_key(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-key")
    get_settings.cache_clear()
    client = TestClient(app)

    for path in ("/operations/jobs", "/operations/status"):
        response = client.get(path)
        assert response.status_code == 401

    get_settings.cache_clear()


def test_operations_read_key_can_access_read_endpoint(monkeypatch, caplog) -> None:
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-admin-key")
    monkeypatch.setenv("MPLACAS_OPERATIONS_READ_API_KEY", "synthetic-read-key")
    get_settings.cache_clear()
    monkeypatch.setattr(operations_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(operations_router, "JobRunRepository", FakeJobRunRepository)
    caplog.set_level("INFO", logger="mplacas.main")

    response = TestClient(app).get(
        "/operations/jobs",
        headers={"X-API-Key": "synthetic-read-key"},
    )

    assert response.status_code == 200
    assert response.json() == {"count": 0, "items": []}
    matching = [
        record
        for record in caplog.records
        if record.name == "mplacas.main" and record.message == "http_request_completed"
    ]
    assert matching
    assert matching[-1].operations_role == "READ"
    assert matching[-1].operations_credential_id.startswith("operations:read:")
    assert "synthetic-read-key" not in matching[-1].operations_credential_id
    get_settings.cache_clear()


def test_scoped_read_key_cannot_access_global_operational_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-admin-key")
    monkeypatch.setenv("MPLACAS_OPERATIONS_READ_API_KEY", "synthetic-read-key")
    monkeypatch.setenv(
        "MPLACAS_OPERATIONS_READ_PLANT_IDS",
        "00000000-0000-0000-0000-000000000040",
    )
    get_settings.cache_clear()
    client = TestClient(app)

    for path in ("/operations/jobs", "/operations/status"):
        response = client.get(path, headers={"X-API-Key": "synthetic-read-key"})
        assert response.status_code == 403

    get_settings.cache_clear()
