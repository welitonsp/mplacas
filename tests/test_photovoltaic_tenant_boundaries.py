"""Cross-tenant boundary test for ``photovoltaic.router`` (ADR-065).

The four photovoltaic tables are under PostgreSQL RLS in production
(``migrations/versions/20260802_0040_enable_postgresql_rls.py``). SQLite (used
here) does not enforce RLS, so this test proves the *first* line of defense —
``core.tenancy.ReadPlant`` rejecting a plant outside the caller's
organization with 404 before any query runs — exactly the same pattern as
``test_climate_tenant_boundaries.py``. Every one of the five ADR-065 routes is
covered, since a forgotten ``set_principal_context`` call or a missing
``ReadPlant`` dependency on just one handler would otherwise go unnoticed.
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
    SeasonalPvBaselineRecord,
)
from mplacas.photovoltaic.loss_taxonomy import LOSS_TAXONOMY_MODEL_VERSION
from mplacas.photovoltaic.performance import PERFORMANCE_MODEL_VERSION
from mplacas.photovoltaic.poa import MODEL_VERSION as SOLAR_MODEL_VERSION
from mplacas.photovoltaic.seasonal_baseline import BASELINE_MODEL_VERSION

PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000e2")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _seed(factory) -> tuple[uuid.UUID, uuid.UUID]:
    """Create org A (with plant A and full photovoltaic data) and org B (no plants)."""
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
        session.add(Plant(id=PLANT_A, organization_id=org_a, name="Plant A"))
        session.add(
            DailyPvPerformanceRecord(
                plant_id=PLANT_A,
                observation_date=date(2026, 7, 1),
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
                plant_id=PLANT_A,
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
        session.add(
            DailyPvLossAssessmentRecord(
                plant_id=PLANT_A,
                observation_date=date(2026, 7, 1),
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
        return org_a, org_b


@pytest.fixture
def cross_tenant_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    import asyncio

    factory, engine = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(photovoltaic_router, "SessionFactory", factory)

    org_a, org_b = asyncio.run(_seed(factory))
    token_b = encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)

    yield org_a, org_b, token_b

    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_latest_performance_cross_tenant_is_not_found(cross_tenant_setup) -> None:
    _, _, token_b = cross_tenant_setup
    response = TestClient(app).get(
        "/photovoltaic/performance/latest",
        headers=_headers(token_b),
        params={"plant_id": str(PLANT_A)},
    )
    assert response.status_code == 404


def test_performance_series_cross_tenant_is_not_found(cross_tenant_setup) -> None:
    _, _, token_b = cross_tenant_setup
    response = TestClient(app).get(
        "/photovoltaic/performance",
        headers=_headers(token_b),
        params={
            "plant_id": str(PLANT_A),
            "start_date": "2026-07-01",
            "end_date": "2026-07-02",
        },
    )
    assert response.status_code == 404
    body = response.json()
    # Never leak Org A's data through a 200 with an "empty" series either.
    assert body != {"count": 0, "items": []}


def test_latest_baseline_cross_tenant_is_not_found(cross_tenant_setup) -> None:
    _, _, token_b = cross_tenant_setup
    response = TestClient(app).get(
        "/photovoltaic/baseline/latest",
        headers=_headers(token_b),
        params={"plant_id": str(PLANT_A)},
    )
    assert response.status_code == 404
    # Must not leak Org A's baseline-unavailable reason derivation either.
    assert response.json() == {"detail": "plant not found"}


def test_latest_losses_cross_tenant_is_not_found(cross_tenant_setup) -> None:
    _, _, token_b = cross_tenant_setup
    response = TestClient(app).get(
        "/photovoltaic/losses/latest",
        headers=_headers(token_b),
        params={"plant_id": str(PLANT_A)},
    )
    assert response.status_code == 404


def test_summary_cross_tenant_is_not_found(cross_tenant_setup) -> None:
    """`/summary` always returns 200 for an *authorized* caller, but a caller
    from another organization must still be rejected with 404 before that
    200-always rule ever applies — the exception is scoped to "no data", not
    to "no access".
    """
    _, _, token_b = cross_tenant_setup
    response = TestClient(app).get(
        "/photovoltaic/summary",
        headers=_headers(token_b),
        params={"plant_id": str(PLANT_A)},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}
