from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

from fastapi.testclient import TestClient

from mplacas.climate.open_meteo import OpenMeteoProviderError
from mplacas.core.config import get_settings
from mplacas.main import app
import mplacas.climate.router as climate_router


class FakeSession:
    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def commit(self) -> None:
        return None


class FakeAuditEventRepository:
    events: list[dict[str, object]] = []

    def __init__(self, session) -> None:
        self.session = session

    async def record(self, request, **kwargs):
        self.events.append(kwargs)
        return SimpleNamespace()


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-key")
    get_settings.cache_clear()


def test_climate_collection_endpoint_returns_persistence_metrics(monkeypatch) -> None:
    _configure(monkeypatch)
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000024")

    async def fake_collect(*args, **kwargs):
        return SimpleNamespace(
            plant_id=plant_id,
            start_date=date(2026, 7, 12),
            end_date=date(2026, 7, 13),
            received=2,
            persistence=SimpleNamespace(inserted=1, updated=1, unchanged=0),
        )

    monkeypatch.setattr(climate_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(climate_router, "collect_and_persist_daily_climate", fake_collect)
    FakeAuditEventRepository.events = []
    monkeypatch.setattr(climate_router, "AuditEventRepository", FakeAuditEventRepository)

    client = TestClient(app)
    unauthorized = client.post(
        "/climate/collect",
        params={
            "plant_id": str(plant_id),
            "start_date": "2026-07-12",
            "end_date": "2026-07-13",
        },
    )
    assert unauthorized.status_code == 401

    response = client.post(
        "/climate/collect",
        headers={"X-API-Key": "synthetic-key"},
        params={
            "plant_id": str(plant_id),
            "start_date": "2026-07-12",
            "end_date": "2026-07-13",
        },
    )
    assert response.status_code == 200
    assert response.json()["received"] == 2
    assert response.json()["persistence"] == {"inserted": 1, "updated": 1, "unchanged": 0}
    event = FakeAuditEventRepository.events[-1]
    assert event["action"] == "climate.collect"
    assert event["resource_id"] == str(plant_id)
    assert event["outcome"] == "SUCCEEDED"
    assert event["details"] == {
        "start_date": "2026-07-12",
        "end_date": "2026-07-13",
        "provider": "OPEN_METEO_ARCHIVE",
        "received": 2,
        "inserted": 1,
        "updated": 1,
        "unchanged": 0,
    }
    get_settings.cache_clear()


def test_climate_collection_endpoint_sanitizes_provider_failure(monkeypatch) -> None:
    _configure(monkeypatch)
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000024")

    async def fake_collect(*args, **kwargs):
        raise OpenMeteoProviderError("private upstream detail")

    monkeypatch.setattr(climate_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(climate_router, "collect_and_persist_daily_climate", fake_collect)

    response = TestClient(app).post(
        "/climate/collect",
        headers={"X-API-Key": "synthetic-key"},
        params={
            "plant_id": str(plant_id),
            "start_date": "2026-07-13",
            "end_date": "2026-07-13",
        },
    )
    assert response.status_code == 502
    assert "private upstream detail" not in response.text
    get_settings.cache_clear()
