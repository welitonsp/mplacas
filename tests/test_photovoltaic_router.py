"""Contract tests for ``photovoltaic.router`` (ADR-065).

Exercises the actual FastAPI app end-to-end against an in-memory SQLite
database, authenticated as an organization-scoped bearer principal — the
same style as ``test_climate_router.py`` / ``test_climate_tenant_boundaries.py``.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.photovoltaic.router as photovoltaic_router
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.photovoltaic.db_models import (
    DailyPvLossAssessmentRecord,
    DailyPvPerformanceRecord,
)
from mplacas.photovoltaic.loss_taxonomy import LOSS_TAXONOMY_MODEL_VERSION
from mplacas.photovoltaic.performance import PERFORMANCE_MODEL_VERSION
from mplacas.photovoltaic.poa import MODEL_VERSION as SOLAR_MODEL_VERSION

PLANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000f1")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


def _performance_row(observation_date: date) -> DailyPvPerformanceRecord:
    return DailyPvPerformanceRecord(
        plant_id=PLANT_ID,
        observation_date=observation_date,
        solar_model_version=SOLAR_MODEL_VERSION,
        performance_model_version=PERFORMANCE_MODEL_VERSION,
        climate_source="OPEN_METEO_ARCHIVE",
        performance_ratio_nature="IEC_61724_STYLE_AC_PR_MODELED_POA",
        availability_nature="CAPACITY_WEIGHTED_DAILY_REPORTING_PROXY",
        uncertainty_percent=None,
        uncertainty_nature="NOT_QUANTIFIED_SENSOR_CLASSES_UNAVAILABLE",
        measured_energy_kwh=Decimal("100.000"),
        dc_capacity_kwp=Decimal("100.000"),
        poa_irradiation_kwh_m2=Decimal("5.000"),
        final_yield_kwh_per_kwp=Decimal("1.000"),
        reference_yield_hours=Decimal("5.000"),
        performance_ratio=Decimal("0.8500"),
        temperature_corrected_performance_ratio=None,
        reporting_availability_ratio=Decimal("0.9800"),
        reporting_device_count=1,
        configured_device_count=1,
        reporting_capacity_kwp=Decimal("100.000"),
        configured_device_capacity_kwp=Decimal("100.000"),
        data_quality_status="FINAL",
        quality_flags=[],
        units_json={"performance_ratio": "ratio"},
        assumptions_json={},
    )


async def _seed(factory) -> uuid.UUID:
    async with factory() as session:
        org_id = uuid.uuid4()
        session.add(
            OrganizationRecord(
                id=org_id, name="Org", slug=f"org-{org_id.hex[:8]}", active=True
            )
        )
        session.add(Plant(id=PLANT_ID, organization_id=org_id, name="Plant"))
        session.add(_performance_row(date(2026, 7, 1)))
        session.add(_performance_row(date(2026, 7, 2)))
        session.add(
            DailyPvLossAssessmentRecord(
                plant_id=PLANT_ID,
                observation_date=date(2026, 7, 2),
                category="COMMUNICATION",
                evidence_level="NOT_DETECTED",
                taxonomy_model_version=LOSS_TAXONOMY_MODEL_VERSION,
                performance_model_version=PERFORMANCE_MODEL_VERSION,
                baseline_model_version=None,
                estimated_loss_percent=None,
                evidence_codes=[],
                limitation=None,
                assumptions_json={},
            )
        )
        await session.commit()
        return org_id


@pytest.fixture
def seeded_app(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    import asyncio

    factory, engine = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(photovoltaic_router, "SessionFactory", factory)

    org_id = asyncio.run(_seed(factory))
    token = encode_access_token(uuid.uuid4(), org_id, OperationsRole.ADMIN.value)

    yield token

    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_latest_performance_returns_most_recent_result(seeded_app) -> None:
    client = TestClient(app)
    response = client.get(
        "/photovoltaic/performance/latest",
        headers=_auth(seeded_app),
        params={"plant_id": str(PLANT_ID)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["observation_date"] == "2026-07-02"
    assert body["performance_ratio"] == "0.8500"


def test_latest_performance_404_when_absent(seeded_app) -> None:
    other_plant = uuid.uuid4()
    client = TestClient(app)
    # The plant does not exist at all, so plant-scope check itself 404s.
    response = client.get(
        "/photovoltaic/performance/latest",
        headers=_auth(seeded_app),
        params={"plant_id": str(other_plant)},
    )
    assert response.status_code == 404


def test_performance_series_returns_items_in_window(seeded_app) -> None:
    client = TestClient(app)
    response = client.get(
        "/photovoltaic/performance",
        headers=_auth(seeded_app),
        params={
            "plant_id": str(PLANT_ID),
            "start_date": "2026-07-01",
            "end_date": "2026-07-02",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["units"] == {"performance_ratio": "ratio"}
    assert [item["observation_date"] for item in body["items"]] == [
        "2026-07-01",
        "2026-07-02",
    ]


def test_performance_series_returns_empty_list_outside_window(seeded_app) -> None:
    client = TestClient(app)
    response = client.get(
        "/photovoltaic/performance",
        headers=_auth(seeded_app),
        params={
            "plant_id": str(PLANT_ID),
            "start_date": "2020-01-01",
            "end_date": "2020-01-02",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["items"] == []
    assert body["units"] is None


def test_performance_series_rejects_inverted_window(seeded_app) -> None:
    client = TestClient(app)
    response = client.get(
        "/photovoltaic/performance",
        headers=_auth(seeded_app),
        params={
            "plant_id": str(PLANT_ID),
            "start_date": "2026-07-02",
            "end_date": "2026-07-01",
        },
    )
    assert response.status_code == 422


def test_performance_series_rejects_window_over_366_days(seeded_app) -> None:
    client = TestClient(app)
    response = client.get(
        "/photovoltaic/performance",
        headers=_auth(seeded_app),
        params={
            "plant_id": str(PLANT_ID),
            "start_date": "2025-01-01",
            "end_date": "2026-12-31",
        },
    )
    assert response.status_code == 422


def test_latest_baseline_404_embeds_derived_reason(seeded_app) -> None:
    client = TestClient(app)
    response = client.get(
        "/photovoltaic/baseline/latest",
        headers=_auth(seeded_app),
        params={"plant_id": str(PLANT_ID)},
    )
    assert response.status_code == 404
    assert "REFERENCE_YEAR_INCOMPLETE" in response.json()["detail"]


def test_latest_losses_returns_items_for_most_recent_date(seeded_app) -> None:
    client = TestClient(app)
    response = client.get(
        "/photovoltaic/losses/latest",
        headers=_auth(seeded_app),
        params={"plant_id": str(PLANT_ID)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["observation_date"] == "2026-07-02"
    assert body["units"] == {"estimated_loss": "percent"}
    assert len(body["items"]) == 1
    assert body["items"][0]["category"] == "COMMUNICATION"


def test_latest_losses_404_when_absent(seeded_app) -> None:
    other_plant = uuid.uuid4()
    client = TestClient(app)
    response = client.get(
        "/photovoltaic/losses/latest",
        headers=_auth(seeded_app),
        params={"plant_id": str(other_plant)},
    )
    assert response.status_code == 404


def test_summary_always_returns_200_with_null_baseline_and_reason(seeded_app) -> None:
    client = TestClient(app)
    response = client.get(
        "/photovoltaic/summary",
        headers=_auth(seeded_app),
        params={"plant_id": str(PLANT_ID)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plant_id"] == str(PLANT_ID)
    assert body["performance"] is not None
    assert body["performance_unavailable_reason"] is None
    assert body["baseline"] is None
    assert body["baseline_unavailable_reason"] == "REFERENCE_YEAR_INCOMPLETE"
    assert body["reference_complete_on"] is not None
    assert body["losses"] is not None
    assert body["losses_unavailable_reason"] is None
    # No baseline yet: the four expected-production fields (ADR-068
    # section 3) are present, with the three data fields null and the
    # reason mirroring the baseline's own reason.
    assert body["expected_daily_production_kwh"] is None
    assert body["expected_daily_production_model_version"] is None
    assert body["expected_daily_production_nature"] is None
    assert body["expected_daily_production_unavailable_reason"] == "REFERENCE_YEAR_INCOMPLETE"


def test_summary_returns_200_with_all_blocks_null_for_new_plant(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    import asyncio

    factory, engine = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(photovoltaic_router, "SessionFactory", factory)

    async def _seed_empty() -> tuple[uuid.UUID, uuid.UUID]:
        async with factory() as session:
            org_id = uuid.uuid4()
            plant_id = uuid.uuid4()
            session.add(
                OrganizationRecord(
                    id=org_id, name="Org2", slug=f"org2-{org_id.hex[:8]}", active=True
                )
            )
            session.add(Plant(id=plant_id, organization_id=org_id, name="New Plant"))
            await session.commit()
            return org_id, plant_id

    org_id, plant_id = asyncio.run(_seed_empty())
    token = encode_access_token(uuid.uuid4(), org_id, OperationsRole.ADMIN.value)

    client = TestClient(app)
    response = client.get(
        "/photovoltaic/summary",
        headers=_auth(token),
        params={"plant_id": str(plant_id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["performance"] is None
    assert body["performance_unavailable_reason"] == "NO_PERFORMANCE_RESULTS"
    assert body["baseline"] is None
    assert body["baseline_unavailable_reason"] == "NO_PERFORMANCE_HISTORY"
    assert body["reference_complete_on"] is None
    assert body["losses"] is None
    assert body["losses_unavailable_reason"] == "NO_LOSS_ASSESSMENTS"
    assert body["expected_daily_production_kwh"] is None
    assert body["expected_daily_production_model_version"] is None
    assert body["expected_daily_production_nature"] is None
    assert body["expected_daily_production_unavailable_reason"] == "NO_PERFORMANCE_HISTORY"

    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def test_summary_returns_populated_expected_production_when_baseline_available(
    monkeypatch,
) -> None:
    """ADR-068 section 3: the four fields carry real values, additively, when
    a baseline and performance record are both available.
    """
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    import asyncio

    from mplacas.photovoltaic.db_models import SeasonalPvBaselineRecord
    from mplacas.photovoltaic.seasonal_baseline import BASELINE_MODEL_VERSION

    factory, engine = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(photovoltaic_router, "SessionFactory", factory)

    async def _seed_with_baseline() -> tuple[uuid.UUID, uuid.UUID]:
        async with factory() as session:
            org_id = uuid.uuid4()
            plant_id = uuid.uuid4()
            session.add(
                OrganizationRecord(
                    id=org_id, name="Org3", slug=f"org3-{org_id.hex[:8]}", active=True
                )
            )
            session.add(Plant(id=plant_id, organization_id=org_id, name="Plant3"))
            session.add(
                DailyPvPerformanceRecord(
                    plant_id=plant_id,
                    observation_date=date(2027, 7, 1),
                    solar_model_version=SOLAR_MODEL_VERSION,
                    performance_model_version=PERFORMANCE_MODEL_VERSION,
                    climate_source="OPEN_METEO_ARCHIVE",
                    performance_ratio_nature="IEC_61724_STYLE_AC_PR_MODELED_POA",
                    availability_nature="CAPACITY_WEIGHTED_DAILY_REPORTING_PROXY",
                    uncertainty_percent=None,
                    uncertainty_nature="NOT_QUANTIFIED_SENSOR_CLASSES_UNAVAILABLE",
                    measured_energy_kwh=Decimal("100.000"),
                    dc_capacity_kwp=Decimal("100.000"),
                    poa_irradiation_kwh_m2=Decimal("5.000"),
                    final_yield_kwh_per_kwp=Decimal("1.000"),
                    reference_yield_hours=Decimal("5.000"),
                    performance_ratio=Decimal("0.8500"),
                    temperature_corrected_performance_ratio=None,
                    reporting_availability_ratio=Decimal("0.9800"),
                    reporting_device_count=1,
                    configured_device_count=1,
                    reporting_capacity_kwp=Decimal("100.000"),
                    configured_device_capacity_kwp=Decimal("100.000"),
                    data_quality_status="FINAL",
                    quality_flags=[],
                    units_json={"performance_ratio": "ratio"},
                    assumptions_json={},
                )
            )
            session.add(
                SeasonalPvBaselineRecord(
                    plant_id=plant_id,
                    observation_date=date(2027, 7, 1),
                    baseline_model_version=BASELINE_MODEL_VERSION,
                    performance_model_version=PERFORMANCE_MODEL_VERSION,
                    metric_nature="TEMPERATURE_CORRECTED_PR_PREFERRED",
                    clear_sky_index_nature="EMPIRICAL_SEASONAL_POA_P90",
                    season_key="MONTH_07",
                    reference_start_date=date(2026, 7, 1),
                    reference_end_date=date(2027, 7, 1),
                    baseline_sample_count=20,
                    baseline_excluded_count=0,
                    comparison_start_date=date(2027, 7, 2),
                    comparison_sample_count=10,
                    clear_sky_poa_p90_kwh_m2=Decimal("6.500"),
                    target_clear_sky_index=Decimal("0.9500"),
                    baseline_median_performance_ratio=Decimal("0.8500"),
                    baseline_mad=Decimal("0.0100"),
                    baseline_q10=Decimal("0.8300"),
                    baseline_q90=Decimal("0.8700"),
                    comparison_median_performance_ratio=Decimal("0.8000"),
                    degradation_percent=Decimal("-5.88"),
                    annualized_degradation_percent=Decimal("-5.90"),
                    degradation_status="DEGRADED",
                    quality_flags=[],
                    assumptions_json={},
                )
            )
            await session.commit()
            return org_id, plant_id

    org_id, plant_id = asyncio.run(_seed_with_baseline())
    token = encode_access_token(uuid.uuid4(), org_id, OperationsRole.ADMIN.value)

    client = TestClient(app)
    response = client.get(
        "/photovoltaic/summary",
        headers=_auth(token),
        params={"plant_id": str(plant_id)},
    )
    assert response.status_code == 200
    body = response.json()
    # dc_capacity_kwp (100.000) x clear_sky_poa_p90_kwh_m2 (6.500) x
    # baseline_median_performance_ratio (0.8500) = 552.500
    assert body["expected_daily_production_kwh"] == "552.500"
    assert (
        body["expected_daily_production_model_version"]
        == "MPLACAS_EXPECTED_DAILY_PRODUCTION_V1"
    )
    assert body["expected_daily_production_nature"] == "SEASONAL_CLEAR_SKY_P90_ENVELOPE"
    assert body["expected_daily_production_unavailable_reason"] is None

    asyncio.run(engine.dispose())
    get_settings.cache_clear()
