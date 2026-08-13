from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.base import Base
from mplacas.db.models import DailyEnergy, DataStatus, Device, Plant
from mplacas.intelligence.anomaly_engine import AnomalyLevel
from mplacas.intelligence.anomaly_service import (
    AnomalyDataNotFoundError,
    analyze_recent_persisted_anomalies,
)


@pytest.mark.asyncio
async def test_correlates_persisted_energy_and_climate_and_counts_streak() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="SYNTHETIC-ANOMALY-001")
        session.add(device)
        await session.flush()
        session.add_all(
            [
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 7, 10),
                    energy_kwh=Decimal("9"),
                    status=DataStatus.CONSOLIDATED,
                ),
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 7, 11),
                    energy_kwh=Decimal("4"),
                    status=DataStatus.CONSOLIDATED,
                ),
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 7, 12),
                    energy_kwh=Decimal("3"),
                    status=DataStatus.CONSOLIDATED,
                ),
                DailyClimateObservationRecord(
                    plant_id=plant.id,
                    observation_date=date(2026, 7, 10),
                    irradiation_kwh_m2=Decimal("5.5"),
                    source="SYNTHETIC",
                ),
                DailyClimateObservationRecord(
                    plant_id=plant.id,
                    observation_date=date(2026, 7, 11),
                    irradiation_kwh_m2=Decimal("5.0"),
                    source="SYNTHETIC",
                ),
                DailyClimateObservationRecord(
                    plant_id=plant.id,
                    observation_date=date(2026, 7, 12),
                    irradiation_kwh_m2=Decimal("5.2"),
                    source="SYNTHETIC",
                ),
            ]
        )
        await session.commit()

        result = await analyze_recent_persisted_anomalies(
            session,
            plant_id=plant.id,
            expected_daily_production_kwh=Decimal("10"),
            days=3,
            end_date=date(2026, 7, 12),
        )

        assert result.days_analyzed == 3
        assert result.current_streak_days == 2
        assert result.worst_level is AnomalyLevel.CRITICAL
        assert result.daily[0].assessment.level is AnomalyLevel.NORMAL
        assert result.daily[1].assessment.level is AnomalyLevel.CRITICAL
        assert result.daily[2].assessment.level is AnomalyLevel.CRITICAL

    await engine.dispose()


@pytest.mark.asyncio
async def test_low_irradiation_relative_to_local_median_is_diagnosed_from_loaded_climate() -> (
    None
):
    """The relative-median threshold must be wired to real persisted data.

    Without `irradiation_median_kwh_m2`/`irradiation_sample_days` populated
    from the loaded climate rows, `assess_daily_performance` always falls
    back to `LOW_PRODUCTION_NOT_EXPLAINED_BY_LOW_IRRADIATION` even on a day
    that was genuinely low-sun relative to its own history.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Median wiring plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="MEDIAN-WIRING-001")
        session.add(device)
        await session.flush()

        # Five unremarkable history days: production matches expectation,
        # irradiation is a steady 5.0 kWh/m^2 -> local median.
        for offset in range(5, 0, -1):
            history_date = date(2026, 7, 12) - timedelta(days=offset)
            session.add(
                DailyEnergy(
                    device_id=device.id,
                    production_date=history_date,
                    energy_kwh=Decimal("10"),
                    status=DataStatus.CONSOLIDATED,
                )
            )
            session.add(
                DailyClimateObservationRecord(
                    plant_id=plant.id,
                    observation_date=history_date,
                    irradiation_kwh_m2=Decimal("5.0"),
                    source="SYNTHETIC",
                )
            )

        # Target day: production crashes (-70%, well past the critical
        # threshold) on a day whose irradiation (1.5) is far below the
        # 5.0 local median -> should be excused as weather, not flagged as
        # an unexplained technical anomaly.
        session.add(
            DailyEnergy(
                device_id=device.id,
                production_date=date(2026, 7, 12),
                energy_kwh=Decimal("3"),
                status=DataStatus.CONSOLIDATED,
            )
        )
        session.add(
            DailyClimateObservationRecord(
                plant_id=plant.id,
                observation_date=date(2026, 7, 12),
                irradiation_kwh_m2=Decimal("1.5"),
                source="SYNTHETIC",
            )
        )
        await session.commit()

        result = await analyze_recent_persisted_anomalies(
            session,
            plant_id=plant.id,
            expected_daily_production_kwh=Decimal("10"),
            days=6,
            end_date=date(2026, 7, 12),
        )

        target_day = result.daily[-1]
        assert target_day.observation_date == date(2026, 7, 12)
        assert target_day.assessment.level is AnomalyLevel.CRITICAL
        codes = {diagnostic.code for diagnostic in target_day.assessment.diagnostics}
        assert "LOW_PRODUCTION_WITH_LOW_IRRADIATION" in codes
        assert "LOW_PRODUCTION_NOT_EXPLAINED_BY_LOW_IRRADIATION" not in codes

    await engine.dispose()


@pytest.mark.asyncio
async def test_median_reaches_beyond_the_realistic_seven_day_operations_window() -> None:
    """`mplacas.alerts.operations` calls this with `anomaly_days=7` in
    practice — with a median bounded to the analyzed window itself, the
    first day (or two) of any 7-day call could never reach the
    `DEFAULT_MINIMUM_IRRADIATION_SAMPLE_DAYS` floor, and the low-irradiation
    excuse would be unreachable exactly where it is needed most. The
    historical climate query must therefore reach further back than
    `first_day` (see `IRRADIATION_MEDIAN_LOOKBACK_DAYS`).
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Seven day window plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="SEVEN-DAY-WINDOW-001")
        session.add(device)
        await session.flush()

        first_day = date(2026, 7, 6)
        last_day = date(2026, 7, 12)  # 7-day analyzed window: 06/07..12/07.

        # Five history days entirely *before* the analyzed window — under the
        # old window-bounded median these would never be visible to any day
        # being assessed, including the target day below (the very first day
        # of the window).
        for offset in range(5, 0, -1):
            history_date = first_day - timedelta(days=offset)
            session.add(
                DailyEnergy(
                    device_id=device.id,
                    production_date=history_date,
                    energy_kwh=Decimal("10"),
                    status=DataStatus.CONSOLIDATED,
                )
            )
            session.add(
                DailyClimateObservationRecord(
                    plant_id=plant.id,
                    observation_date=history_date,
                    irradiation_kwh_m2=Decimal("5.0"),
                    source="SYNTHETIC",
                )
            )

        # Target day is the FIRST day of the analyzed window: production
        # crashes on genuinely low irradiation relative to the pre-window
        # history above.
        session.add(
            DailyEnergy(
                device_id=device.id,
                production_date=first_day,
                energy_kwh=Decimal("3"),
                status=DataStatus.CONSOLIDATED,
            )
        )
        session.add(
            DailyClimateObservationRecord(
                plant_id=plant.id,
                observation_date=first_day,
                irradiation_kwh_m2=Decimal("1.5"),
                source="SYNTHETIC",
            )
        )

        # The remaining six days of the analyzed window: unremarkable.
        for offset in range(1, 7):
            regular_date = first_day + timedelta(days=offset)
            session.add(
                DailyEnergy(
                    device_id=device.id,
                    production_date=regular_date,
                    energy_kwh=Decimal("10"),
                    status=DataStatus.CONSOLIDATED,
                )
            )
            session.add(
                DailyClimateObservationRecord(
                    plant_id=plant.id,
                    observation_date=regular_date,
                    irradiation_kwh_m2=Decimal("5.0"),
                    source="SYNTHETIC",
                )
            )
        await session.commit()

        result = await analyze_recent_persisted_anomalies(
            session,
            plant_id=plant.id,
            expected_daily_production_kwh=Decimal("10"),
            days=7,
            end_date=last_day,
        )

        assert result.start_date == first_day
        target_day = result.daily[0]
        assert target_day.observation_date == first_day
        assert target_day.assessment.level is AnomalyLevel.CRITICAL
        codes = {diagnostic.code for diagnostic in target_day.assessment.diagnostics}
        assert "LOW_PRODUCTION_WITH_LOW_IRRADIATION" in codes
        assert "LOW_PRODUCTION_NOT_EXPLAINED_BY_LOW_IRRADIATION" not in codes

    await engine.dispose()


@pytest.mark.asyncio
async def test_rejects_explicit_non_positive_expected_production() -> None:
    """`None` (expectation unavailable) is not a programming error, but an
    explicit non-positive value passed by a caller still is."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Guard synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.commit()

        with pytest.raises(ValueError, match="greater than zero"):
            await analyze_recent_persisted_anomalies(
                session,
                plant_id=plant.id,
                expected_daily_production_kwh=Decimal("0"),
                days=7,
                end_date=date(2026, 7, 12),
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_none_expected_production_returns_unassessed_series_without_error() -> None:
    """A plant with real, persisted daily production but no resolvable
    seasonal baseline must still return the full production series: every
    day carries `assessment=None`, `worst_level` is `None`, and the streak
    is not counted — no exception, no fabricated severity."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="No-expectation synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="SYNTHETIC-NO-EXPECTATION-001")
        session.add(device)
        await session.flush()

        last_day = date(2026, 7, 12)
        first_day = last_day - timedelta(days=6)
        for offset in range(7):
            current_day = first_day + timedelta(days=offset)
            session.add(
                DailyEnergy(
                    device_id=device.id,
                    production_date=current_day,
                    energy_kwh=Decimal("10"),
                    status=DataStatus.CONSOLIDATED,
                )
            )
        await session.commit()

        result = await analyze_recent_persisted_anomalies(
            session,
            plant_id=plant.id,
            expected_daily_production_kwh=None,
            days=7,
            end_date=last_day,
            expected_unavailable_reason="NO_PERFORMANCE_HISTORY",
        )

        assert result.days_analyzed == 7
        assert result.worst_level is None
        assert result.current_streak_days == 0
        assert result.expected_unavailable_reason == "NO_PERFORMANCE_HISTORY"
        assert all(item.assessment is None for item in result.daily)
        assert all(item.expected_production_kwh is None for item in result.daily)
        assert all(item.actual_production_kwh == Decimal("10") for item in result.daily)

    await engine.dispose()


@pytest.mark.asyncio
async def test_rejects_period_without_persisted_production() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Empty synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.commit()

        with pytest.raises(AnomalyDataNotFoundError, match="daily production"):
            await analyze_recent_persisted_anomalies(
                session,
                plant_id=plant.id,
                expected_daily_production_kwh=Decimal("10"),
                days=7,
                end_date=date(2026, 7, 12),
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_period_yield_and_per_day_deviation_moved_from_frontend() -> None:
    """Plan T7: `computeYieldStats` moved from `frontend/src/lib/dashboard/
    yield.ts` into this module. Reproduces the same aggregate (total
    production / total irradiation across the window) and per-day percent
    deviation the frontend used to compute.

    Revised for plan T7b (P1, "dia de produção zero com sol desaparece"): a
    day with zero production but a positive irradiation reading (day C) now
    gets a *defined* yield of `0` (worst possible deviation, -100%) instead
    of `None` — it is still excluded from the aggregate itself (`sample_days`
    only counts A and B), so it cannot drag down the reference it is judged
    against. A day with no positive irradiation reading at all (day D) still
    has no ratio, `None`, because there is no denominator to divide by.
    """
    from mplacas.intelligence.anomaly_service import YIELD_ATYPICAL_THRESHOLD_PERCENT

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="Yield synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="SYNTHETIC-YIELD-001")
        session.add(device)
        await session.flush()
        session.add_all(
            [
                # Day A: yield = 10/4 = 2.5 -> +25% vs period yield (2.0).
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 7, 10),
                    energy_kwh=Decimal("10"),
                    status=DataStatus.CONSOLIDATED,
                ),
                DailyClimateObservationRecord(
                    plant_id=plant.id,
                    observation_date=date(2026, 7, 10),
                    irradiation_kwh_m2=Decimal("4"),
                    source="SYNTHETIC",
                ),
                # Day B: yield = 6/4 = 1.5 -> -25% vs period yield.
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 7, 11),
                    energy_kwh=Decimal("6"),
                    status=DataStatus.CONSOLIDATED,
                ),
                DailyClimateObservationRecord(
                    plant_id=plant.id,
                    observation_date=date(2026, 7, 11),
                    irradiation_kwh_m2=Decimal("4"),
                    source="SYNTHETIC",
                ),
                # Day C: zero production with a positive irradiation reading
                # -> excluded from the aggregate, but its own yield is a
                # defined 0 (plan T7b P1), not None.
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 7, 12),
                    energy_kwh=Decimal("0"),
                    status=DataStatus.CONSOLIDATED,
                ),
                DailyClimateObservationRecord(
                    plant_id=plant.id,
                    observation_date=date(2026, 7, 12),
                    irradiation_kwh_m2=Decimal("5"),
                    source="SYNTHETIC",
                ),
                # Day D: production reported, but no climate row at all ->
                # excluded from the aggregate; own yield is None.
                DailyEnergy(
                    device_id=device.id,
                    production_date=date(2026, 7, 13),
                    energy_kwh=Decimal("5"),
                    status=DataStatus.CONSOLIDATED,
                ),
            ]
        )
        await session.commit()

        result = await analyze_recent_persisted_anomalies(
            session,
            plant_id=plant.id,
            expected_daily_production_kwh=None,
            days=4,
            end_date=date(2026, 7, 13),
            expected_unavailable_reason="NO_PERFORMANCE_HISTORY",
        )

        assert result.days_analyzed == 4
        # (10 + 6) / (4 + 4) = 2.0 -- days C and D excluded from both sums.
        assert result.period_yield_kwh_per_kwh_m2 == Decimal("2")
        assert result.yield_atypical_threshold_percent == YIELD_ATYPICAL_THRESHOLD_PERCENT
        assert result.yield_atypical_threshold_percent == Decimal("20")
        # Plan T7b P1 ("o rótulo usa a contagem errada"): only days A and B
        # fed the aggregate, even though 4 days have a production row
        # (`days_analyzed`) — the frontend must label the yield with this
        # field, not with `days_analyzed`.
        assert result.period_yield_sample_days == 2

        by_date = {item.observation_date: item for item in result.daily}
        assert by_date[date(2026, 7, 10)].yield_kwh_per_kwh_m2 == Decimal("2.5")
        assert by_date[date(2026, 7, 10)].yield_deviation_from_period_percent == Decimal("25")
        assert by_date[date(2026, 7, 11)].yield_kwh_per_kwh_m2 == Decimal("1.5")
        assert by_date[date(2026, 7, 11)].yield_deviation_from_period_percent == Decimal("-25")
        # Day C: zero production under sun (irradiation=5) -> defined yield
        # of 0, and the worst possible deviation (-100%) — it must be
        # visible as an atypical day, not silently dropped as "no data".
        assert by_date[date(2026, 7, 12)].yield_kwh_per_kwh_m2 == Decimal("0")
        assert by_date[date(2026, 7, 12)].yield_deviation_from_period_percent == Decimal("-100")
        # Day D: no climate row at all -> genuinely no ratio possible.
        assert by_date[date(2026, 7, 13)].yield_kwh_per_kwh_m2 is None
        assert by_date[date(2026, 7, 13)].yield_deviation_from_period_percent is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_period_yield_unavailable_when_no_day_has_both_production_and_irradiation() -> None:
    """Mirrors `computeYieldStats`'s `periodYield == null` early return: no
    day in the window qualifies, so the aggregate — and every per-day yield
    — is `None`, never `0` or a fabricated number."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        plant = Plant(name="No irradiation synthetic plant", timezone="America/Sao_Paulo")
        session.add(plant)
        await session.flush()
        device = Device(plant_id=plant.id, serial_number="SYNTHETIC-NO-IRRADIATION-001")
        session.add(device)
        await session.flush()
        session.add(
            DailyEnergy(
                device_id=device.id,
                production_date=date(2026, 7, 12),
                energy_kwh=Decimal("10"),
                status=DataStatus.CONSOLIDATED,
            )
        )
        await session.commit()

        result = await analyze_recent_persisted_anomalies(
            session,
            plant_id=plant.id,
            expected_daily_production_kwh=None,
            days=1,
            end_date=date(2026, 7, 12),
        )

        assert result.period_yield_kwh_per_kwh_m2 is None
        assert result.daily[0].yield_kwh_per_kwh_m2 is None
        assert result.daily[0].yield_deviation_from_period_percent is None
        assert result.period_yield_sample_days == 0

    await engine.dispose()
