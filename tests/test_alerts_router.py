from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from mplacas.alerts.models import AlertSeverity
from mplacas.core.config import get_settings
from mplacas.main import app
from mplacas.photovoltaic.expected_production import (
    EXPECTED_PRODUCTION_MODEL_VERSION,
    EXPECTED_PRODUCTION_NATURE,
    ExpectedDailyProduction,
)
from mplacas.photovoltaic.read_service import ExpectedProductionResolution
import mplacas.alerts.router as alerts_router
import mplacas.core.tenancy as tenancy_module


class FakeQueryResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class FakeSession:
    plant_name = "Usina Teste"

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def execute(self, *args: object, **kwargs: object) -> FakeQueryResult:
        return FakeQueryResult(self.plant_name)


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
    body = response.json()
    assert body["count"] == 1
    assert body["succeeded"] == 1
    assert body["failed"] == 0
    assert body["skipped"] == 0
    item = body["items"][0]
    assert item["plant_id"] == str(plant_id)
    assert item["plant_name"] == "Usina Teste"
    assert item["outcome"] == "succeeded"
    assert item["error"] is None
    assert item["result"]["executive_available"] is True
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


def test_alerts_run_derives_expected_daily_production_when_omitted(monkeypatch) -> None:
    """ADR-069 § E.11.5: explicit `plant_id`, omitted expectation, baseline available."""
    _configure(monkeypatch)
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000031")
    derived = ExpectedDailyProduction(
        expected_daily_production_kwh=Decimal("552.500"),
        dc_capacity_kwp=Decimal("100.000"),
        clear_sky_poa_p90_kwh_m2=Decimal("6.500"),
        baseline_median_performance_ratio=Decimal("0.8500"),
        model_version=EXPECTED_PRODUCTION_MODEL_VERSION,
        nature=EXPECTED_PRODUCTION_NATURE,
    )
    received_kwargs: dict[str, object] = {}

    async def fake_resolve(session, *, plant_id, today=None):
        return ExpectedProductionResolution(
            expected=derived, unavailable_reason=None, reference_complete_on=None
        )

    async def fake_run_alert_pipeline(*args, **kwargs):
        received_kwargs.update(kwargs)
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
            job=SimpleNamespace(results=()),
        )

    monkeypatch.setattr(alerts_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(alerts_router, "resolve_expected_daily_production", fake_resolve)
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
            "minimum_severity": AlertSeverity.WARNING.value,
        },
    )

    assert response.status_code == 200
    assert received_kwargs["expected_daily_production_kwh"] == Decimal("552.500")
    get_settings.cache_clear()


def test_alerts_run_returns_422_when_expectation_unavailable(monkeypatch) -> None:
    """ADR-069 § E.11.5: explicit `plant_id`, omitted expectation, no baseline."""
    _configure(monkeypatch)
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000031")

    async def fake_resolve(session, *, plant_id, today=None):
        return ExpectedProductionResolution(
            expected=None,
            unavailable_reason="NO_PERFORMANCE_HISTORY",
            reference_complete_on=None,
        )

    called = {"pipeline_invoked": False}

    async def fake_run_alert_pipeline(*args, **kwargs):
        called["pipeline_invoked"] = True
        raise AssertionError("alert pipeline must not run when expectation is unavailable")

    monkeypatch.setattr(alerts_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(alerts_router, "resolve_expected_daily_production", fake_resolve)
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
            "minimum_severity": AlertSeverity.WARNING.value,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {"unavailable_reason": "NO_PERFORMANCE_HISTORY"}
    assert called["pipeline_invoked"] is False
    get_settings.cache_clear()


def test_alerts_run_static_key_single_plant_omitted_allows_expectation(
    monkeypatch,
) -> None:
    """ADR-069 § E.11.3: static key, single-plant install, no ambiguity.

    ``plant_id`` omitted (as today's single-usina callers do) and
    ``expected_daily_production_kwh`` supplied must succeed (200), not 409:
    ``scoped.explicit`` is ``False`` here, but the resolved set has exactly
    one plant, so there is no real ambiguity.
    """
    _configure(monkeypatch)
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000031")

    async def fake_infer_single_plant(organization_id):
        assert organization_id is None
        return plant_id

    async def fake_run_alert_pipeline(*args, **kwargs):
        return SimpleNamespace(
            plant_id=plant_id,
            executive_available=True,
            anomaly_available=False,
            metrics=SimpleNamespace(
                evaluated=1,
                sent=1,
                skipped=0,
                failed=0,
                duplicates=0,
                below_minimum_severity=0,
            ),
            job=SimpleNamespace(results=()),
        )

    monkeypatch.setattr(
        tenancy_module, "_infer_single_plant_for_organization", fake_infer_single_plant
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
            "expected_daily_production_kwh": "1000",
            "minimum_severity": AlertSeverity.WARNING.value,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["succeeded"] == 1
    assert body["items"][0]["plant_id"] == str(plant_id)
    get_settings.cache_clear()
