from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from mplacas.core.config import get_settings
from mplacas.main import app
from mplacas.orchestration.db_models import PipelineExecutionStatus
from mplacas.photovoltaic.expected_production import (
    EXPECTED_PRODUCTION_MODEL_VERSION,
    EXPECTED_PRODUCTION_NATURE,
    ExpectedDailyProduction,
)
from mplacas.photovoltaic.read_service import ExpectedProductionResolution
import mplacas.orchestration.router as orchestration_router


class FakeSession:
    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
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


def test_pipeline_run_endpoint_is_protected_and_returns_sanitized_metrics(monkeypatch) -> None:
    _configure(monkeypatch)
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000027")

    async def fake_runtime(*args, **kwargs):
        return SimpleNamespace(
            execution_id=uuid.UUID("00000000-0000-0000-0000-000000000127"),
            plant_id=plant_id,
            target_date=date(2026, 7, 13),
            duration_ms=125,
            pipeline=SimpleNamespace(
                climate=SimpleNamespace(
                    received=1,
                    solar_projection=SimpleNamespace(
                        inserted=1,
                        updated=0,
                        unchanged=0,
                        skipped=0,
                        skip_reason=None,
                    ),
                ),
                performance=SimpleNamespace(
                    inserted=1,
                    updated=0,
                    unchanged=0,
                    skipped=0,
                    skip_reason=None,
                ),
                seasonal_baseline=SimpleNamespace(
                    inserted=0,
                    updated=0,
                    unchanged=0,
                    skipped=1,
                    skip_reason="frozen reference year is not complete",
                ),
                loss_taxonomy=SimpleNamespace(
                    inserted=8,
                    updated=0,
                    unchanged=0,
                    skipped=0,
                    skip_reason=None,
                ),
                alerts=SimpleNamespace(
                    metrics=SimpleNamespace(evaluated=2, sent=1, skipped=1, failed=0)
                ),
            ),
        )

    monkeypatch.setattr(orchestration_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(orchestration_router, "run_ledger_backed_daily_pipeline", fake_runtime)
    FakeAuditEventRepository.events = []
    monkeypatch.setattr(orchestration_router, "AuditEventRepository", FakeAuditEventRepository)

    client = TestClient(app)
    unauthorized = client.post(
        "/pipeline/run",
        params={
            "plant_id": str(plant_id),
            "target_date": "2026-07-13",
            "expected_daily_production_kwh": "10",
        },
    )
    assert unauthorized.status_code == 401

    response = client.post(
        "/pipeline/run",
        headers={"X-API-Key": "synthetic-key"},
        params={
            "plant_id": str(plant_id),
            "target_date": "2026-07-13",
            "expected_daily_production_kwh": "10",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["plant_id"] == str(plant_id)
    assert payload["duration_ms"] == 125
    assert payload["solar_projection"] == {
        "inserted": 1,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "skip_reason": None,
    }
    assert payload["performance"] == {
        "inserted": 1,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "skip_reason": None,
    }
    assert payload["seasonal_baseline"] == {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped": 1,
        "skip_reason": "frozen reference year is not complete",
    }
    assert payload["loss_taxonomy"] == {
        "inserted": 8,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "skip_reason": None,
    }
    assert payload["alerts"] == {"evaluated": 2, "sent": 1, "skipped": 1, "failed": 0}
    assert "synthetic-token" not in response.text
    assert FakeAuditEventRepository.events[-1]["action"] == "pipeline.run"
    assert FakeAuditEventRepository.events[-1]["outcome"] == "SUCCEEDED"
    assert "synthetic-chat" not in response.text
    get_settings.cache_clear()


def test_pipeline_run_derives_expected_daily_production_when_omitted(monkeypatch) -> None:
    """ADR-069 § E.11.5: explicit `plant_id`, omitted expectation, baseline available."""
    _configure(monkeypatch)
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000027")
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

    async def fake_runtime(*args, **kwargs):
        received_kwargs.update(kwargs)
        return SimpleNamespace(
            execution_id=uuid.UUID("00000000-0000-0000-0000-000000000127"),
            plant_id=plant_id,
            target_date=date(2026, 7, 13),
            duration_ms=125,
            pipeline=SimpleNamespace(
                climate=SimpleNamespace(
                    received=1,
                    solar_projection=SimpleNamespace(
                        inserted=1, updated=0, unchanged=0, skipped=0, skip_reason=None
                    ),
                ),
                performance=SimpleNamespace(
                    inserted=1, updated=0, unchanged=0, skipped=0, skip_reason=None
                ),
                seasonal_baseline=SimpleNamespace(
                    inserted=0, updated=0, unchanged=0, skipped=1, skip_reason=None
                ),
                loss_taxonomy=SimpleNamespace(
                    inserted=8, updated=0, unchanged=0, skipped=0, skip_reason=None
                ),
                alerts=SimpleNamespace(
                    metrics=SimpleNamespace(evaluated=2, sent=1, skipped=1, failed=0)
                ),
            ),
        )

    monkeypatch.setattr(orchestration_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(
        orchestration_router, "resolve_expected_daily_production", fake_resolve
    )
    monkeypatch.setattr(orchestration_router, "run_ledger_backed_daily_pipeline", fake_runtime)
    FakeAuditEventRepository.events = []
    monkeypatch.setattr(orchestration_router, "AuditEventRepository", FakeAuditEventRepository)

    response = TestClient(app).post(
        "/pipeline/run",
        headers={"X-API-Key": "synthetic-key"},
        params={"plant_id": str(plant_id), "target_date": "2026-07-13"},
    )

    assert response.status_code == 200
    assert received_kwargs["expected_daily_production_kwh"] == Decimal("552.500")
    get_settings.cache_clear()


def test_pipeline_run_returns_422_when_expectation_unavailable(monkeypatch) -> None:
    """ADR-069 § E.11.5: explicit `plant_id`, omitted expectation, no baseline."""
    _configure(monkeypatch)
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000027")

    async def fake_resolve(session, *, plant_id, today=None):
        return ExpectedProductionResolution(
            expected=None,
            unavailable_reason="REFERENCE_YEAR_INCOMPLETE",
            reference_complete_on=None,
        )

    called = {"runtime_invoked": False}

    async def fake_runtime(*args, **kwargs):
        called["runtime_invoked"] = True
        raise AssertionError("pipeline runtime must not run when expectation is unavailable")

    monkeypatch.setattr(orchestration_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(
        orchestration_router, "resolve_expected_daily_production", fake_resolve
    )
    monkeypatch.setattr(orchestration_router, "run_ledger_backed_daily_pipeline", fake_runtime)
    FakeAuditEventRepository.events = []
    monkeypatch.setattr(orchestration_router, "AuditEventRepository", FakeAuditEventRepository)

    response = TestClient(app).post(
        "/pipeline/run",
        headers={"X-API-Key": "synthetic-key"},
        params={"plant_id": str(plant_id), "target_date": "2026-07-13"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {"unavailable_reason": "REFERENCE_YEAR_INCOMPLETE"}
    assert called["runtime_invoked"] is False
    get_settings.cache_clear()


def test_latest_pipeline_status_endpoint_returns_technical_snapshot(monkeypatch) -> None:
    _configure(monkeypatch)
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000027")

    async def fake_latest(*args, **kwargs):
        return SimpleNamespace(
            execution_id=uuid.UUID("00000000-0000-0000-0000-000000000127"),
            plant_id=plant_id,
            target_date=date(2026, 7, 13),
            status=PipelineExecutionStatus.SUCCEEDED,
            attempt_count=2,
            stage="COMPLETED",
            error_code=None,
            started_at=datetime(2026, 7, 13, 8, 0, tzinfo=UTC),
            finished_at=datetime(2026, 7, 13, 8, 1, tzinfo=UTC),
        )

    monkeypatch.setattr(orchestration_router, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(orchestration_router, "get_latest_pipeline_execution", fake_latest)

    response = TestClient(app).get(
        "/pipeline/status/latest",
        headers={"X-API-Key": "synthetic-key"},
        params={"plant_id": str(plant_id)},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCEEDED"
    assert response.json()["attempt_count"] == 2
    get_settings.cache_clear()
