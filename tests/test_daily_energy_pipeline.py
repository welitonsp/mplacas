from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest

import mplacas.orchestration.daily_pipeline as pipeline_module
from mplacas.photovoltaic.loss_taxonomy_service import (
    LossTaxonomyComputationSummary,
)
from mplacas.photovoltaic.performance_service import PerformanceComputationSummary
from mplacas.photovoltaic.seasonal_baseline_service import (
    SeasonalBaselineComputationSummary,
)


@pytest.mark.asyncio
async def test_pipeline_calculates_performance_and_baseline_before_alerts(monkeypatch) -> None:
    events: list[str] = []
    plant_id = uuid.uuid4()

    async def fake_climate(*args, **kwargs):
        events.append("climate_and_poa")
        return SimpleNamespace(
            received=1,
            persistence=SimpleNamespace(inserted=1, updated=0, unchanged=0),
            solar_projection=SimpleNamespace(
                inserted=1,
                updated=0,
                unchanged=0,
                skipped=0,
                skip_reason=None,
            ),
        )

    async def fake_performance(*args, **kwargs):
        events.append("performance")
        return PerformanceComputationSummary(1, 0, 0, 0)

    async def fake_baseline(*args, **kwargs):
        events.append("seasonal_baseline")
        return SeasonalBaselineComputationSummary(1, 0, 0, 0)

    async def fake_loss_taxonomy(*args, **kwargs):
        events.append("loss_taxonomy")
        return LossTaxonomyComputationSummary(8, 0, 0, 0)

    async def fake_alerts(*args, **kwargs):
        events.append("alerts")
        return SimpleNamespace(
            metrics=SimpleNamespace(evaluated=1, sent=0, skipped=1, failed=0),
            outcome="evaluated",
        )

    monkeypatch.setattr(
        pipeline_module, "collect_and_persist_daily_climate", fake_climate
    )
    monkeypatch.setattr(
        pipeline_module, "calculate_and_persist_daily_performance", fake_performance
    )
    monkeypatch.setattr(
        pipeline_module, "calculate_and_persist_seasonal_baseline", fake_baseline
    )
    monkeypatch.setattr(
        pipeline_module, "classify_and_persist_daily_losses", fake_loss_taxonomy
    )
    monkeypatch.setattr(
        pipeline_module, "run_operational_alert_pipeline", fake_alerts
    )

    result = await pipeline_module.run_daily_energy_pipeline(
        SimpleNamespace(),
        plant_id=plant_id,
        target_date=date(2026, 7, 15),
        climate_provider=SimpleNamespace(),
        alert_provider=SimpleNamespace(),
        alert_destination_ref="telegram:test",
        expected_daily_production_kwh=Decimal("10"),
    )

    assert events == [
        "climate_and_poa",
        "performance",
        "seasonal_baseline",
        "loss_taxonomy",
        "alerts",
    ]
    assert result.performance.inserted == 1
    assert result.seasonal_baseline.inserted == 1
    assert result.loss_taxonomy.inserted == 8
    assert result.plant_id == plant_id
    assert result.alerts.outcome == "evaluated"


@pytest.mark.asyncio
async def test_pipeline_skips_only_alerts_when_no_derivable_expectation(
    monkeypatch,
) -> None:
    """ADR-069 § E9 correction (deadlock fix).

    A plant with no derivable expectation (``expected_daily_production_kwh
    is None``, e.g. it has no seasonal baseline yet) must still run
    climate/POA collection, performance calculation and seasonal baseline
    calculation -- otherwise the baseline could never accumulate the
    history it needs to eventually exist. Only alert dispatch, which needs
    the expectation to score anomaly severity, is skipped.
    """
    events: list[str] = []
    plant_id = uuid.uuid4()

    async def fake_climate(*args, **kwargs):
        events.append("climate_and_poa")
        return SimpleNamespace(
            received=1,
            persistence=SimpleNamespace(inserted=1, updated=0, unchanged=0),
            solar_projection=SimpleNamespace(
                inserted=1,
                updated=0,
                unchanged=0,
                skipped=0,
                skip_reason=None,
            ),
        )

    async def fake_performance(*args, **kwargs):
        events.append("performance")
        return PerformanceComputationSummary(1, 0, 0, 0)

    async def fake_baseline(*args, **kwargs):
        events.append("seasonal_baseline")
        return SeasonalBaselineComputationSummary(1, 0, 0, 0)

    async def fake_loss_taxonomy(*args, **kwargs):
        events.append("loss_taxonomy")
        return LossTaxonomyComputationSummary(8, 0, 0, 0)

    async def fake_alerts(*args, **kwargs):
        events.append("alerts")
        raise AssertionError(
            "run_operational_alert_pipeline must not be called when "
            "expected_daily_production_kwh is None"
        )

    monkeypatch.setattr(
        pipeline_module, "collect_and_persist_daily_climate", fake_climate
    )
    monkeypatch.setattr(
        pipeline_module, "calculate_and_persist_daily_performance", fake_performance
    )
    monkeypatch.setattr(
        pipeline_module, "calculate_and_persist_seasonal_baseline", fake_baseline
    )
    monkeypatch.setattr(
        pipeline_module, "classify_and_persist_daily_losses", fake_loss_taxonomy
    )
    monkeypatch.setattr(
        pipeline_module, "run_operational_alert_pipeline", fake_alerts
    )

    result = await pipeline_module.run_daily_energy_pipeline(
        SimpleNamespace(),
        plant_id=plant_id,
        target_date=date(2026, 7, 15),
        climate_provider=SimpleNamespace(),
        alert_provider=SimpleNamespace(),
        alert_destination_ref="telegram:test",
        expected_daily_production_kwh=None,
    )

    # Climate, performance, baseline and loss taxonomy all still ran and
    # persisted data -- the plant was not skipped. Only alerts did not run.
    assert events == [
        "climate_and_poa",
        "performance",
        "seasonal_baseline",
        "loss_taxonomy",
    ]
    assert result.performance.inserted == 1
    assert result.seasonal_baseline.inserted == 1
    assert result.loss_taxonomy.inserted == 8
    assert result.alerts.outcome == "skipped"
    assert result.alerts.unavailable_reason == (
        pipeline_module.ALERTS_SKIPPED_NO_EXPECTATION_REASON
    )
    assert result.alerts.metrics.evaluated == 0
    assert result.alerts.metrics.sent == 0


@pytest.mark.asyncio
async def test_pipeline_accumulates_performance_across_successive_runs_without_expectation(
    monkeypatch,
) -> None:
    """Simulates several nightly runs for a plant that never had a baseline.

    Each run has ``expected_daily_production_kwh=None`` (mirroring
    ``resolve_expected_daily_production`` returning nothing for a plant
    without a formed baseline). The performance and seasonal baseline
    calculation steps must still be invoked, and therefore accumulate data,
    on every single run -- they must never be blocked by the missing
    expectation. Once enough history exists the baseline service itself
    (exercised separately, unit-tested elsewhere) would start returning a
    baseline; here we assert the accumulation path that makes that possible
    is never short-circuited.
    """
    plant_id = uuid.uuid4()
    performance_calls: list[date] = []
    baseline_calls: list[date] = []

    async def fake_climate(*args, **kwargs):
        return SimpleNamespace(
            received=1,
            persistence=SimpleNamespace(inserted=1, updated=0, unchanged=0),
            solar_projection=SimpleNamespace(
                inserted=1,
                updated=0,
                unchanged=0,
                skipped=0,
                skip_reason=None,
            ),
        )

    async def fake_performance(*args, **kwargs):
        performance_calls.append(kwargs["observation_date"])
        return PerformanceComputationSummary(1, 0, 0, 0)

    async def fake_baseline(*args, **kwargs):
        baseline_calls.append(kwargs["observation_date"])
        return SeasonalBaselineComputationSummary(1, 0, 0, 0)

    async def fake_loss_taxonomy(*args, **kwargs):
        return LossTaxonomyComputationSummary(8, 0, 0, 0)

    monkeypatch.setattr(
        pipeline_module, "collect_and_persist_daily_climate", fake_climate
    )
    monkeypatch.setattr(
        pipeline_module, "calculate_and_persist_daily_performance", fake_performance
    )
    monkeypatch.setattr(
        pipeline_module, "calculate_and_persist_seasonal_baseline", fake_baseline
    )
    monkeypatch.setattr(
        pipeline_module, "classify_and_persist_daily_losses", fake_loss_taxonomy
    )

    days = [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)]
    for observation_date in days:
        result = await pipeline_module.run_daily_energy_pipeline(
            SimpleNamespace(),
            plant_id=plant_id,
            target_date=observation_date,
            climate_provider=SimpleNamespace(),
            alert_provider=SimpleNamespace(),
            alert_destination_ref="telegram:test",
            expected_daily_production_kwh=None,
        )
        assert result.alerts.outcome == "skipped"

    assert performance_calls == days
    assert baseline_calls == days
