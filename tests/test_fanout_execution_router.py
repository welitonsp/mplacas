"""ADR-069 § E7 -- fan-out wiring of the four execution endpoints.

Exercises ``POST /alerts/run``, ``POST /climate/collect``, ``POST
/pipeline/run`` and ``GET /pipeline/status/latest`` against a real (sqlite)
database with an organization that owns two plants, verifying the envelope
shape, partial-failure isolation (one plant's rollback must never discard
another plant's already-committed work/audit event), the "skipped" outcome
for a plant with nothing to do, and cross-organization isolation. The
service-layer work itself (``collect_and_persist_daily_climate``,
``run_operational_alert_pipeline``, ``run_ledger_backed_daily_pipeline``,
``get_latest_pipeline_execution``) is mocked per test -- this file exercises
the router/fan-out wiring, not those services (already covered elsewhere).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.alerts.router as alerts_router
import mplacas.climate.router as climate_router
import mplacas.db.session as db_session
import mplacas.orchestration.router as orchestration_router
from mplacas.audit.db_models import AuditEventRecord
from mplacas.climate.open_meteo import OpenMeteoProviderError
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.orchestration.db_models import PipelineExecutionStatus
from mplacas.photovoltaic.read_service import ExpectedProductionResolution

_TEST_ENGINES: list = []


@pytest.fixture(autouse=True)
def _dispose_test_engines():
    yield
    while _TEST_ENGINES:
        asyncio.run(_TEST_ENGINES.pop().dispose())


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _TEST_ENGINES.append(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed():
    """Org A with two plants (Alpha, Beta), org B with one plant (Gamma)."""
    factory = await _factory()
    async with factory() as session:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        session.add_all(
            [
                OrganizationRecord(
                    id=org_a, name="Org A", slug=f"org-a-{org_a.hex[:8]}", active=True
                ),
                OrganizationRecord(
                    id=org_b, name="Org B", slug=f"org-b-{org_b.hex[:8]}", active=True
                ),
            ]
        )
        await session.flush()

        plant_alpha = uuid.uuid4()
        plant_beta = uuid.uuid4()
        plant_gamma = uuid.uuid4()
        session.add_all(
            [
                Plant(id=plant_alpha, organization_id=org_a, name="Alpha"),
                Plant(id=plant_beta, organization_id=org_a, name="Beta"),
                Plant(id=plant_gamma, organization_id=org_b, name="Gamma"),
            ]
        )
        await session.commit()
    return factory, org_a, org_b, plant_alpha, plant_beta, plant_gamma


@pytest.fixture
def seeded(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALERT_CHAT_ID", "synthetic-chat")
    get_settings.cache_clear()

    factory, org_a, org_b, plant_alpha, plant_beta, plant_gamma = asyncio.run(_seed())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(climate_router, "SessionFactory", factory)
    monkeypatch.setattr(alerts_router, "SessionFactory", factory)
    monkeypatch.setattr(orchestration_router, "SessionFactory", factory)

    yield {
        "factory": factory,
        "org_a": org_a,
        "org_b": org_b,
        "plant_alpha": plant_alpha,
        "plant_beta": plant_beta,
        "plant_gamma": plant_gamma,
    }

    get_settings.cache_clear()


def _bearer(organization_id: uuid.UUID, role: OperationsRole = OperationsRole.ADMIN) -> dict:
    token = encode_access_token(uuid.uuid4(), organization_id, role.value)
    return {"Authorization": f"Bearer {token}"}


def _audit_events(factory) -> list[AuditEventRecord]:
    async def _query():
        async with factory() as session:
            result = await session.execute(select(AuditEventRecord))
            return list(result.scalars())

    return asyncio.run(_query())


# ---------------------------------------------------------------------------
# climate/collect
# ---------------------------------------------------------------------------


def test_climate_collect_fanout_succeeds_on_both_plants(seeded, monkeypatch) -> None:
    async def fake_collect(session, *, plant_id, provider, start_date, end_date, maximum_days):
        return SimpleNamespace(
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
            received=1,
            persistence=SimpleNamespace(inserted=1, updated=0, unchanged=0),
            solar_projection=SimpleNamespace(
                inserted=1, updated=0, unchanged=0, skipped=0, skip_reason=None
            ),
        )

    monkeypatch.setattr(climate_router, "collect_and_persist_daily_climate", fake_collect)

    response = TestClient(app).post(
        "/climate/collect",
        headers=_bearer(seeded["org_a"]),
        params={"start_date": "2026-07-12", "end_date": "2026-07-13"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["succeeded"] == 2
    assert body["failed"] == 0
    assert body["skipped"] == 0
    assert [item["plant_name"] for item in body["items"]] == ["Alpha", "Beta"]
    ids = {item["plant_id"] for item in body["items"]}
    assert ids == {str(seeded["plant_alpha"]), str(seeded["plant_beta"])}
    assert str(seeded["plant_gamma"]) not in ids

    events = _audit_events(seeded["factory"])
    assert len(events) == 2
    assert all(event.outcome == "SUCCEEDED" for event in events)
    assert all(event.resource_id != str(seeded["plant_gamma"]) for event in events)


def test_climate_collect_fanout_partial_failure_persists_the_success(
    seeded, monkeypatch
) -> None:
    async def fake_collect(session, *, plant_id, provider, start_date, end_date, maximum_days):
        if plant_id == seeded["plant_beta"]:
            raise OpenMeteoProviderError("private upstream detail")
        return SimpleNamespace(
            plant_id=plant_id,
            start_date=start_date,
            end_date=end_date,
            received=1,
            persistence=SimpleNamespace(inserted=1, updated=0, unchanged=0),
            solar_projection=SimpleNamespace(
                inserted=1, updated=0, unchanged=0, skipped=0, skip_reason=None
            ),
        )

    monkeypatch.setattr(climate_router, "collect_and_persist_daily_climate", fake_collect)

    response = TestClient(app).post(
        "/climate/collect",
        headers=_bearer(seeded["org_a"]),
        params={"start_date": "2026-07-12", "end_date": "2026-07-13"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    by_name = {item["plant_name"]: item for item in body["items"]}
    assert by_name["Alpha"]["outcome"] == "succeeded"
    assert by_name["Alpha"]["result"] is not None
    assert by_name["Alpha"]["error"] is None
    assert by_name["Beta"]["outcome"] == "failed"
    assert by_name["Beta"]["result"] is None
    assert by_name["Beta"]["error"]["code"] == "OPENMETEOPROVIDERERROR"
    assert "private upstream detail" not in response.text

    # Alpha's audit event (and, by the same transaction, its domain writes)
    # is committed even though Beta's session was rolled back separately.
    events = _audit_events(seeded["factory"])
    outcomes = {event.resource_id: event.outcome for event in events}
    assert outcomes[str(seeded["plant_alpha"])] == "SUCCEEDED"
    assert outcomes[str(seeded["plant_beta"])] == "failure"


def test_climate_collect_explicit_plant_id_still_preserves_502(seeded, monkeypatch) -> None:
    async def fake_collect(session, *, plant_id, provider, start_date, end_date, maximum_days):
        raise OpenMeteoProviderError("private upstream detail")

    monkeypatch.setattr(climate_router, "collect_and_persist_daily_climate", fake_collect)

    response = TestClient(app).post(
        "/climate/collect",
        headers=_bearer(seeded["org_a"]),
        params={
            "plant_id": str(seeded["plant_alpha"]),
            "start_date": "2026-07-12",
            "end_date": "2026-07-13",
        },
    )

    assert response.status_code == 502
    assert "private upstream detail" not in response.text


def test_climate_collect_fanout_cap_rejects_before_any_execution(seeded, monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_FANOUT_MAX_PLANTS", "1")
    get_settings.cache_clear()

    called = {"invoked": False}

    async def fake_collect(*args, **kwargs):
        called["invoked"] = True
        raise AssertionError("must not execute any plant above the cap")

    monkeypatch.setattr(climate_router, "collect_and_persist_daily_climate", fake_collect)

    try:
        response = TestClient(app).post(
            "/climate/collect",
            headers=_bearer(seeded["org_a"]),
            params={"start_date": "2026-07-12", "end_date": "2026-07-13"},
        )
        assert response.status_code == 409
        assert called["invoked"] is False
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# alerts/run
# ---------------------------------------------------------------------------


def test_alerts_run_fanout_skips_plant_without_baseline(seeded, monkeypatch) -> None:
    invoked_for: list[uuid.UUID] = []

    async def fake_resolve(session, *, plant_id, today=None):
        if plant_id == seeded["plant_beta"]:
            return ExpectedProductionResolution(
                expected=None,
                unavailable_reason="NO_PERFORMANCE_HISTORY",
                reference_complete_on=None,
            )
        return ExpectedProductionResolution(
            expected=SimpleNamespace(expected_daily_production_kwh=100),
            unavailable_reason=None,
            reference_complete_on=None,
        )

    async def fake_run_alert_pipeline(session, *, plant_id, **kwargs):
        invoked_for.append(plant_id)
        return SimpleNamespace(
            plant_id=plant_id,
            executive_available=True,
            anomaly_available=True,
            metrics=SimpleNamespace(
                evaluated=1, sent=1, skipped=0, failed=0, duplicates=0, below_minimum_severity=0
            ),
            job=SimpleNamespace(results=()),
        )

    monkeypatch.setattr(alerts_router, "resolve_expected_daily_production", fake_resolve)
    monkeypatch.setattr(alerts_router, "run_operational_alert_pipeline", fake_run_alert_pipeline)

    response = TestClient(app).post(
        "/alerts/run",
        headers=_bearer(seeded["org_a"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["succeeded"] == 1
    assert body["skipped"] == 1
    assert body["failed"] == 0
    by_name = {item["plant_name"]: item for item in body["items"]}
    assert by_name["Alpha"]["outcome"] == "succeeded"
    assert by_name["Beta"]["outcome"] == "skipped"
    assert by_name["Beta"]["result"] == {"unavailable_reason": "NO_PERFORMANCE_HISTORY"}
    assert invoked_for == [seeded["plant_alpha"]]  # never dispatched for Beta


def test_alerts_run_fanout_rejects_explicit_expectation(seeded) -> None:
    response = TestClient(app).post(
        "/alerts/run",
        headers=_bearer(seeded["org_a"]),
        params={"expected_daily_production_kwh": "10"},
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# pipeline/status/latest
# ---------------------------------------------------------------------------


def test_pipeline_status_latest_fanout_skips_plant_without_history(seeded, monkeypatch) -> None:
    async def fake_latest(session, *, plant_id):
        if plant_id == seeded["plant_beta"]:
            return None
        return SimpleNamespace(
            execution_id=uuid.uuid4(),
            plant_id=plant_id,
            target_date=date(2026, 7, 13),
            status=PipelineExecutionStatus.SUCCEEDED,
            attempt_count=1,
            stage="COMPLETED",
            error_code=None,
            started_at=datetime(2026, 7, 13, 8, 0, tzinfo=UTC),
            finished_at=datetime(2026, 7, 13, 8, 1, tzinfo=UTC),
        )

    monkeypatch.setattr(orchestration_router, "get_latest_pipeline_execution", fake_latest)

    response = TestClient(app).get(
        "/pipeline/status/latest",
        headers=_bearer(seeded["org_a"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["succeeded"] == 1
    assert body["skipped"] == 1
    by_name = {item["plant_name"]: item for item in body["items"]}
    assert by_name["Alpha"]["outcome"] == "succeeded"
    assert by_name["Beta"]["outcome"] == "skipped"
    assert by_name["Beta"]["result"] is None


# ---------------------------------------------------------------------------
# pipeline/run
# ---------------------------------------------------------------------------


def test_pipeline_run_fanout_succeeds_on_both_plants(seeded, monkeypatch) -> None:
    async def fake_resolve(session, *, plant_id, today=None):
        return ExpectedProductionResolution(
            expected=SimpleNamespace(expected_daily_production_kwh=100),
            unavailable_reason=None,
            reference_complete_on=None,
        )

    async def fake_runtime(session, *, plant_id, target_date, **kwargs):
        return SimpleNamespace(
            execution_id=uuid.uuid4(),
            plant_id=plant_id,
            target_date=target_date,
            duration_ms=10,
            pipeline=SimpleNamespace(
                climate=SimpleNamespace(
                    received=1,
                    solar_projection=SimpleNamespace(
                        inserted=0, updated=0, unchanged=0, skipped=0, skip_reason=None
                    ),
                ),
                performance=SimpleNamespace(
                    inserted=0, updated=0, unchanged=0, skipped=0, skip_reason=None
                ),
                seasonal_baseline=SimpleNamespace(
                    inserted=0, updated=0, unchanged=0, skipped=0, skip_reason=None
                ),
                loss_taxonomy=SimpleNamespace(
                    inserted=0, updated=0, unchanged=0, skipped=0, skip_reason=None
                ),
                alerts=SimpleNamespace(
                    metrics=SimpleNamespace(evaluated=0, sent=0, skipped=0, failed=0)
                ),
            ),
        )

    monkeypatch.setattr(orchestration_router, "resolve_expected_daily_production", fake_resolve)
    monkeypatch.setattr(orchestration_router, "run_ledger_backed_daily_pipeline", fake_runtime)

    response = TestClient(app).post(
        "/pipeline/run",
        headers=_bearer(seeded["org_a"]),
        params={"target_date": "2026-07-13"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["succeeded"] == 2
    assert body["failed"] == 0
    assert [item["plant_name"] for item in body["items"]] == ["Alpha", "Beta"]
    ids = {item["plant_id"] for item in body["items"]}
    assert str(seeded["plant_gamma"]) not in ids
