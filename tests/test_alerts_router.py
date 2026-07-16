from __future__ import annotations

import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

from mplacas.alerts.models import AlertSeverity
from mplacas.core.config import get_settings
from mplacas.main import app
import mplacas.alerts.router as alerts_router


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
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALERT_CHAT_ID", "synthetic-chat")
    get_settings.cache_clear()


def test_alerts_run_endpoint_records_sanitized_audit_event(monkeypatch) -> None:
    _configure(monkeypatch)
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000031")

    async def fake_run_alert_pipeline(*args, **kwargs):
        return SimpleNamespace(
            plant_id=plant_id,
            executive_available=True,
            anomaly_available=False,
            metrics=SimpleNamespace(
                evaluated=3,
                sent=1,
                skipped=2,
                failed=0,
                duplicates=1,
                below_minimum_severity=1,
            ),
            job=SimpleNamespace(
                results=(
                    SimpleNamespace(
                        status=SimpleNamespace(value="sent"),
                        fingerprint="fingerprint-1",
                        reason=None,
                    ),
                )
            ),
        )

    monkeypatch.setattr(alerts_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(
        alerts_router,
        "run_operational_alert_pipeline",
        fake_run_alert_pipeline,
    )
    FakeAuditEventRepository.events = []
    monkeypatch.setattr(alerts_router, "AuditEventRepository", FakeAuditEventRepository)

    response = TestClient(app).post(
        "/alerts/run",
        headers={"X-API-Key": "synthetic-key"},
        params={
            "plant_id": str(plant_id),
            "expected_daily_production_kwh": "10",
            "minimum_severity": AlertSeverity.WARNING.value,
        },
    )

    assert response.status_code == 200
    assert "synthetic-token" not in response.text
    assert "synthetic-chat" not in response.text
    event = FakeAuditEventRepository.events[-1]
    assert event["action"] == "alerts.run"
    assert event["resource_type"] == "plant"
    assert event["resource_id"] == str(plant_id)
    assert event["outcome"] == "SUCCEEDED"
    assert event["details"] == {
        "executive_available": True,
        "anomaly_available": False,
        "evaluated": 3,
        "sent": 1,
        "skipped": 2,
        "failed": 0,
        "duplicates": 1,
        "below_minimum_severity": 1,
        "minimum_severity": "WARNING",
    }
    get_settings.cache_clear()
