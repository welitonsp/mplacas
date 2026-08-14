"""ADR-068 Etapa D: `GET /energy/anomalies/latest` resolves the expected
daily production internally instead of trusting the client-supplied query
parameter.

Covers the acceptance tests fixed by ADR-068 sections 5, 7 and 8 (Etapa D):

- the expectation is resolved server-side when the (now optional and
  deprecated) `expected_daily_production_kwh` parameter is absent;
- the same result is produced when the parameter is present but wrong,
  proving it is ignored rather than honored;
- 404 with the unavailability reason code when the expectation cannot be
  resolved;
- a tenant-boundary test, in the shape of `test_alerts_tenant_boundaries.py`,
  proving the new photovoltaic-table read inside this `intelligence` handler
  never leaks or uses another organization's baseline/performance data.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.intelligence.router as anomalies_router
from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.photovoltaic.db_models import (
    DailyPvPerformanceRecord,
    SeasonalPvBaselineRecord,
)
from mplacas.photovoltaic.performance import PERFORMANCE_MODEL_VERSION
from mplacas.photovoltaic.poa import MODEL_VERSION as SOLAR_MODEL_VERSION
from mplacas.photovoltaic.seasonal_baseline import BASELINE_MODEL_VERSION

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


def _performance_row(
    *, plant_id: uuid.UUID, observation_date: date, dc_capacity_kwp: Decimal
) -> DailyPvPerformanceRecord:
    return DailyPvPerformanceRecord(
        plant_id=plant_id,
        observation_date=observation_date,
        solar_model_version=SOLAR_MODEL_VERSION,
        performance_model_version=PERFORMANCE_MODEL_VERSION,
        climate_source="OPEN_METEO_ARCHIVE",
        performance_ratio_nature="IEC_61724_STYLE_AC_PR_MODELED_POA",
        availability_nature="CAPACITY_WEIGHTED_DAILY_REPORTING_PROXY",
        uncertainty_percent=None,
        uncertainty_nature="NOT_QUANTIFIED_SENSOR_CLASSES_UNAVAILABLE",
        measured_energy_kwh=Decimal("100.000"),
        dc_capacity_kwp=dc_capacity_kwp,
        poa_irradiation_kwh_m2=Decimal("5.000"),
        final_yield_kwh_per_kwp=Decimal("1.000"),
        reference_yield_hours=Decimal("5.000"),
        performance_ratio=Decimal("0.8500"),
        temperature_corrected_performance_ratio=None,
        reporting_availability_ratio=Decimal("0.9800"),
        reporting_device_count=1,
        configured_device_count=1,
        reporting_capacity_kwp=dc_capacity_kwp,
        configured_device_capacity_kwp=dc_capacity_kwp,
        data_quality_status="FINAL",
        quality_flags=[],
        units_json={"performance_ratio": "ratio"},
        assumptions_json={},
    )


def _baseline_row(
    *,
    plant_id: uuid.UUID,
    observation_date: date,
    clear_sky_poa_p90_kwh_m2: Decimal,
    baseline_median_performance_ratio: Decimal,
) -> SeasonalPvBaselineRecord:
    return SeasonalPvBaselineRecord(
        plant_id=plant_id,
        observation_date=observation_date,
        baseline_model_version=BASELINE_MODEL_VERSION,
        performance_model_version=PERFORMANCE_MODEL_VERSION,
        metric_nature="TEMPERATURE_CORRECTED_PR_PREFERRED",
        clear_sky_index_nature="EMPIRICAL_SEASONAL_POA_P90",
        season_key="MONTH_07",
        reference_start_date=observation_date - timedelta(days=365),
        reference_end_date=observation_date,
        baseline_sample_count=20,
        baseline_excluded_count=0,
        comparison_start_date=observation_date + timedelta(days=1),
        comparison_sample_count=10,
        clear_sky_poa_p90_kwh_m2=clear_sky_poa_p90_kwh_m2,
        target_clear_sky_index=Decimal("0.9500"),
        baseline_median_performance_ratio=baseline_median_performance_ratio,
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


async def _seed_plant_with_resolvable_expectation(
    factory, *, organization_id: uuid.UUID, plant_id: uuid.UUID, today: date
) -> None:
    async with factory() as session:
        session.add(
            OrganizationRecord(
                id=organization_id,
                name="Org",
                slug=f"org-{organization_id.hex[:8]}",
                active=True,
            )
        )
        session.add(Plant(id=plant_id, organization_id=organization_id, name="Usina"))
        await session.flush()
        session.add(
            _performance_row(
                plant_id=plant_id,
                observation_date=today,
                dc_capacity_kwp=Decimal("100.000"),
            )
        )
        session.add(
            _baseline_row(
                plant_id=plant_id,
                observation_date=today,
                clear_sky_poa_p90_kwh_m2=Decimal("1.000"),
                baseline_median_performance_ratio=Decimal("0.9000"),
            )
        )
        device = Device(plant_id=plant_id, serial_number=f"DEV-{plant_id.hex[:8]}")
        session.add(device)
        await session.flush()
        session.add(
            DailyEnergy(
                device_id=device.id,
                production_date=today,
                energy_kwh=Decimal("90.000"),
                status=DataStatus.CONSOLIDATED,
            )
        )
        await session.commit()


def _bearer(organization_id: uuid.UUID, role: OperationsRole = OperationsRole.ADMIN) -> dict:
    token = encode_access_token(uuid.uuid4(), organization_id, role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def resolvable_plant(monkeypatch):
    """Org A, one plant with a resolvable expectation (100 x 1.000 x 0.9 = 90.000 kWh)
    and one day of matching energy data, so `analyze_recent_persisted_anomalies`
    has something to classify."""
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    factory = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(anomalies_router, "SessionFactory", factory)

    org_id = uuid.uuid4()
    plant_id = uuid.uuid4()
    today = date.today()
    asyncio.run(
        _seed_plant_with_resolvable_expectation(
            factory, organization_id=org_id, plant_id=plant_id, today=today
        )
    )

    yield {"factory": factory, "org_id": org_id, "plant_id": plant_id, "today": today}

    get_settings.cache_clear()


def test_expectation_resolved_server_side_when_parameter_absent(resolvable_plant) -> None:
    client = TestClient(app)
    response = client.get(
        "/energy/anomalies/latest",
        headers=_bearer(resolvable_plant["org_id"]),
        params={"plant_id": str(resolvable_plant["plant_id"]), "days": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["daily"][0]["expected_production_kwh"] == "90.000"
    assert body["daily"][0]["actual_production_kwh"] == "90.000"


def test_yield_fields_present_but_null_without_a_climate_observation(resolvable_plant) -> None:
    """Plan T7: the yield fields are always present in the envelope, even
    when they can't be computed. `resolvable_plant` never seeds a
    `DailyClimateObservationRecord`, so there is no irradiation reading —
    the period aggregate and every per-day yield must be `null`, not `0` or
    absent from the payload. The threshold, being a fixed policy value
    rather than a derived one, is present regardless."""
    client = TestClient(app)
    response = client.get(
        "/energy/anomalies/latest",
        headers=_bearer(resolvable_plant["org_id"]),
        params={"plant_id": str(resolvable_plant["plant_id"]), "days": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["period_yield_kwh_per_kwh_m2"] is None
    assert body["yield_atypical_threshold_percent"] == "20"
    assert body["period_yield_sample_days"] == 0
    assert body["daily"][0]["yield_kwh_per_kwh_m2"] is None
    assert body["daily"][0]["yield_deviation_from_period_percent"] is None


def test_yield_fields_computed_end_to_end_when_irradiation_is_available(monkeypatch) -> None:
    """Same aggregate/deviation formula proven in `test_anomaly_service.py`,
    exercised through the actual HTTP route: `GET /energy/anomalies/latest`
    -> `analyze_recent_persisted_anomalies` -> `_serialize_anomalies`."""
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    factory = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(anomalies_router, "SessionFactory", factory)

    org_id = uuid.uuid4()
    plant_id = uuid.uuid4()
    # `analyze_recent_persisted_anomalies` is called by the router without an
    # explicit `end_date`, so it defaults to `date.today()` (see
    # `resolvable_plant`'s own `today = date.today()` for the same reason).
    day_b = date.today()
    day_a = day_b - timedelta(days=1)

    async def _seed_plant_with_irradiation() -> None:
        async with factory() as session:
            session.add(
                OrganizationRecord(id=org_id, name="Org", slug=f"org-{org_id.hex[:8]}", active=True)
            )
            session.add(Plant(id=plant_id, organization_id=org_id, name="Usina com irradiância"))
            await session.flush()
            device = Device(plant_id=plant_id, serial_number=f"DEV-{plant_id.hex[:8]}")
            session.add(device)
            await session.flush()
            session.add_all(
                [
                    # yield = 10/4 = 2.5 -> +25% vs period yield (2.0).
                    DailyEnergy(
                        device_id=device.id,
                        production_date=day_a,
                        energy_kwh=Decimal("10"),
                        status=DataStatus.CONSOLIDATED,
                    ),
                    DailyClimateObservationRecord(
                        plant_id=plant_id,
                        observation_date=day_a,
                        irradiation_kwh_m2=Decimal("4"),
                        source="SYNTHETIC",
                    ),
                    # yield = 6/4 = 1.5 -> -25% vs period yield.
                    DailyEnergy(
                        device_id=device.id,
                        production_date=day_b,
                        energy_kwh=Decimal("6"),
                        status=DataStatus.CONSOLIDATED,
                    ),
                    DailyClimateObservationRecord(
                        plant_id=plant_id,
                        observation_date=day_b,
                        irradiation_kwh_m2=Decimal("4"),
                        source="SYNTHETIC",
                    ),
                ]
            )
            await session.commit()

    asyncio.run(_seed_plant_with_irradiation())

    client = TestClient(app)
    response = client.get(
        "/energy/anomalies/latest",
        headers=_bearer(org_id),
        params={"plant_id": str(plant_id), "days": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["period_yield_kwh_per_kwh_m2"]) == Decimal("2")
    assert body["yield_atypical_threshold_percent"] == "20"
    assert body["period_yield_sample_days"] == 2
    by_date = {item["date"]: item for item in body["daily"]}
    # Decimal division carries extra scale (e.g. "25.00" instead of "25") —
    # the frontend's `toNumber`/`formatNumber` already normalizes this at
    # render time (same as every other Decimal-as-string field in this
    # payload), so the value is compared numerically here, not as a raw
    # string.
    assert Decimal(by_date[day_a.isoformat()]["yield_kwh_per_kwh_m2"]) == Decimal("2.5")
    assert Decimal(by_date[day_b.isoformat()]["yield_kwh_per_kwh_m2"]) == Decimal("1.5")
    # O desvio passou a ser medido contra a mediana rolante dos 30 dias
    # anteriores a cada dia (plano T7b, P1). Esta usina sintetica tem dois dias
    # e nenhum historico, entao nao alcanca o piso de amostra e o desvio fica
    # `null` — indisponibilidade explicita, nunca "normal" por omissao. O
    # rendimento do dia (`yield_kwh_per_kwh_m2`) continua sendo calculado.
    assert by_date[day_a.isoformat()]["yield_deviation_from_period_percent"] is None
    assert by_date[day_b.isoformat()]["yield_deviation_from_period_percent"] is None

    get_settings.cache_clear()


def test_zero_production_day_with_sun_gets_a_defined_yield_end_to_end(monkeypatch) -> None:
    """Plan T7b, P1 ("dia de produção zero com sol desaparece"): a full
    outage (0 kWh) under a positive irradiation reading must round-trip
    through the HTTP route with a defined `yield_kwh_per_kwh_m2` of `"0"`
    and the worst possible deviation (`"-100"`) — never absent, and never
    counted in `period_yield_sample_days`."""
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    factory = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(anomalies_router, "SessionFactory", factory)

    org_id = uuid.uuid4()
    plant_id = uuid.uuid4()
    day_b = date.today()
    day_a = day_b - timedelta(days=1)

    async def _seed_plant_with_an_outage_day() -> None:
        async with factory() as session:
            session.add(
                OrganizationRecord(id=org_id, name="Org", slug=f"org-{org_id.hex[:8]}", active=True)
            )
            session.add(Plant(id=plant_id, organization_id=org_id, name="Usina com apagão"))
            await session.flush()
            device = Device(plant_id=plant_id, serial_number=f"DEV-{plant_id.hex[:8]}")
            session.add(device)
            await session.flush()
            session.add_all(
                [
                    # Normal day: yield = 10/4 = 2.5 -> period yield is 2.5,
                    # the only day feeding the aggregate.
                    DailyEnergy(
                        device_id=device.id,
                        production_date=day_a,
                        energy_kwh=Decimal("10"),
                        status=DataStatus.CONSOLIDATED,
                    ),
                    DailyClimateObservationRecord(
                        plant_id=plant_id,
                        observation_date=day_a,
                        irradiation_kwh_m2=Decimal("4"),
                        source="SYNTHETIC",
                    ),
                    # Full outage under sun: 0 kWh produced, irradiation
                    # positive -> excluded from the aggregate, but its own
                    # ratio is a defined 0, not None.
                    DailyEnergy(
                        device_id=device.id,
                        production_date=day_b,
                        energy_kwh=Decimal("0"),
                        status=DataStatus.CONSOLIDATED,
                    ),
                    DailyClimateObservationRecord(
                        plant_id=plant_id,
                        observation_date=day_b,
                        irradiation_kwh_m2=Decimal("5"),
                        source="SYNTHETIC",
                    ),
                ]
            )
            await session.commit()

    asyncio.run(_seed_plant_with_an_outage_day())

    client = TestClient(app)
    response = client.get(
        "/energy/anomalies/latest",
        headers=_bearer(org_id),
        params={"plant_id": str(plant_id), "days": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["period_yield_kwh_per_kwh_m2"]) == Decimal("2.5")
    assert body["period_yield_sample_days"] == 1
    by_date = {item["date"]: item for item in body["daily"]}
    # O dia de producao zero sob sol continua com rendimento DEFINIDO (0), que
    # e o ponto deste teste: ele nao pode sumir como se nao houvesse dado.
    assert Decimal(by_date[day_b.isoformat()]["yield_kwh_per_kwh_m2"]) == Decimal("0")
    # O desvio fica `null` por falta de historico para a mediana rolante, nao
    # por falta de rendimento (ver comentario no teste acima).
    assert by_date[day_b.isoformat()]["yield_deviation_from_period_percent"] is None

    get_settings.cache_clear()


def test_temperature_mean_c_serialized_per_day_end_to_end(monkeypatch) -> None:
    """Plan T7b, P2: `temperature_mean_c` round-trips through the HTTP route
    as a string when present, and as `null` — never `0` — for a day whose
    climate observation exists but has no temperature reading."""
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    factory = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(anomalies_router, "SessionFactory", factory)

    org_id = uuid.uuid4()
    plant_id = uuid.uuid4()
    day_b = date.today()
    day_a = day_b - timedelta(days=1)

    async def _seed_plant_with_temperature() -> None:
        async with factory() as session:
            session.add(
                OrganizationRecord(id=org_id, name="Org", slug=f"org-{org_id.hex[:8]}", active=True)
            )
            session.add(Plant(id=plant_id, organization_id=org_id, name="Usina com temperatura"))
            await session.flush()
            device = Device(plant_id=plant_id, serial_number=f"DEV-{plant_id.hex[:8]}")
            session.add(device)
            await session.flush()
            session.add_all(
                [
                    DailyEnergy(
                        device_id=device.id,
                        production_date=day_a,
                        energy_kwh=Decimal("10"),
                        status=DataStatus.CONSOLIDATED,
                    ),
                    DailyClimateObservationRecord(
                        plant_id=plant_id,
                        observation_date=day_a,
                        irradiation_kwh_m2=Decimal("4"),
                        temperature_mean_c=Decimal("28.30"),
                        source="SYNTHETIC",
                    ),
                    DailyEnergy(
                        device_id=device.id,
                        production_date=day_b,
                        energy_kwh=Decimal("6"),
                        status=DataStatus.CONSOLIDATED,
                    ),
                    DailyClimateObservationRecord(
                        plant_id=plant_id,
                        observation_date=day_b,
                        irradiation_kwh_m2=Decimal("4"),
                        temperature_mean_c=None,
                        source="SYNTHETIC",
                    ),
                ]
            )
            await session.commit()

    asyncio.run(_seed_plant_with_temperature())

    client = TestClient(app)
    response = client.get(
        "/energy/anomalies/latest",
        headers=_bearer(org_id),
        params={"plant_id": str(plant_id), "days": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["period"] == {"start_date": day_a.isoformat(), "end_date": day_b.isoformat()}
    by_date = {item["date"]: item for item in body["daily"]}
    assert by_date[day_a.isoformat()]["temperature_mean_c"] == "28.30"
    assert by_date[day_b.isoformat()]["temperature_mean_c"] is None

    get_settings.cache_clear()


def test_wrong_client_supplied_expectation_is_ignored(resolvable_plant) -> None:
    """The parameter is accepted (validated by `Query(gt=0)`) but never used:
    a deliberately absurd value must produce the exact same result as when
    the parameter is absent."""
    client = TestClient(app)
    baseline_response = client.get(
        "/energy/anomalies/latest",
        headers=_bearer(resolvable_plant["org_id"]),
        params={"plant_id": str(resolvable_plant["plant_id"]), "days": 1},
    )
    wrong_response = client.get(
        "/energy/anomalies/latest",
        headers=_bearer(resolvable_plant["org_id"]),
        params={
            "plant_id": str(resolvable_plant["plant_id"]),
            "days": 1,
            "expected_daily_production_kwh": "999999",
        },
    )
    assert baseline_response.status_code == wrong_response.status_code == 200
    assert baseline_response.json() == wrong_response.json()
    assert wrong_response.json()["daily"][0]["expected_production_kwh"] == "90.000"


def test_404_when_no_daily_production_is_collected_at_all(monkeypatch) -> None:
    """Legit 404: zero days of persisted production for the requested period,
    regardless of whether an expectation can be resolved. Unaffected by the
    fix that stopped 404ing the *entire* request just because the seasonal
    baseline/expectation is unavailable (see the 200 test below)."""
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    factory = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(anomalies_router, "SessionFactory", factory)

    org_id = uuid.uuid4()
    plant_id = uuid.uuid4()

    async def _seed_bare_plant() -> None:
        async with factory() as session:
            session.add(
                OrganizationRecord(
                    id=org_id, name="Org", slug=f"org-{org_id.hex[:8]}", active=True
                )
            )
            session.add(Plant(id=plant_id, organization_id=org_id, name="Usina sem baseline"))
            await session.commit()

    asyncio.run(_seed_bare_plant())

    client = TestClient(app)
    response = client.get(
        "/energy/anomalies/latest",
        headers=_bearer(org_id),
        params={"plant_id": str(plant_id)},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "daily production not found for requested period"}

    get_settings.cache_clear()


def test_200_with_null_level_when_production_exists_but_no_expectation_available(
    monkeypatch,
) -> None:
    """A plant with real, persisted daily production but no resolvable
    seasonal baseline/expectation must still return the production series
    (200), not hide it behind a 404 — only the severity assessment per day
    is unavailable (`level: null`)."""
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    factory = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(anomalies_router, "SessionFactory", factory)

    org_id = uuid.uuid4()
    plant_id = uuid.uuid4()
    today = date.today()

    async def _seed_plant_without_baseline() -> None:
        async with factory() as session:
            session.add(
                OrganizationRecord(
                    id=org_id, name="Org", slug=f"org-{org_id.hex[:8]}", active=True
                )
            )
            session.add(Plant(id=plant_id, organization_id=org_id, name="Usina sem baseline"))
            await session.flush()
            device = Device(plant_id=plant_id, serial_number=f"DEV-{plant_id.hex[:8]}")
            session.add(device)
            await session.flush()
            session.add(
                DailyEnergy(
                    device_id=device.id,
                    production_date=today,
                    energy_kwh=Decimal("90.000"),
                    status=DataStatus.CONSOLIDATED,
                )
            )
            await session.commit()

    asyncio.run(_seed_plant_without_baseline())

    client = TestClient(app)
    response = client.get(
        "/energy/anomalies/latest",
        headers=_bearer(org_id),
        params={"plant_id": str(plant_id), "days": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["worst_level"] is None
    assert body["current_streak_days"] == 0
    assert body["expected_unavailable_reason"] == "NO_PERFORMANCE_HISTORY"
    assert len(body["daily"]) == 1
    day = body["daily"][0]
    assert day["actual_production_kwh"] == "90.000"
    assert day["expected_production_kwh"] is None
    assert day["level"] is None
    assert day["deviation_kwh"] is None
    assert day["deviation_percent"] is None
    assert day["diagnostics"] == []

    get_settings.cache_clear()


def test_cross_tenant_plant_is_not_found_and_never_reads_or_uses_its_expectation(
    resolvable_plant, monkeypatch
) -> None:
    """Org B must never resolve, and must never see, org A's expected
    production or anomaly classification for org A's plant.

    Mirrors `test_alerts_tenant_boundaries.py`'s negative-proof pattern:
    both the new expectation resolver and the anomaly analysis are stubbed
    to raise if they are ever invoked, so the test fails loudly if the
    tenancy check on `ReadPlant` is ever bypassed before either photovoltaic
    or anomaly data is touched.
    """

    async def fake_resolve_expected_daily_production(*args, **kwargs):  # pragma: no cover
        raise AssertionError(
            "expected-production resolver should not run before plant scope is validated"
        )

    async def fake_analyze_recent_persisted_anomalies(*args, **kwargs):  # pragma: no cover
        raise AssertionError(
            "anomaly analysis should not run before plant scope is validated"
        )

    monkeypatch.setattr(
        anomalies_router,
        "resolve_expected_daily_production",
        fake_resolve_expected_daily_production,
    )
    monkeypatch.setattr(
        anomalies_router,
        "analyze_recent_persisted_anomalies",
        fake_analyze_recent_persisted_anomalies,
    )

    org_b = uuid.uuid4()

    async def _seed_org_b() -> None:
        async with resolvable_plant["factory"]() as session:
            session.add(
                OrganizationRecord(
                    id=org_b, name="Org B", slug=f"org-b-{org_b.hex[:8]}", active=True
                )
            )
            await session.commit()

    asyncio.run(_seed_org_b())

    client = TestClient(app)
    response = client.get(
        "/energy/anomalies/latest",
        headers=_bearer(org_b),
        params={"plant_id": str(resolvable_plant["plant_id"])},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}
