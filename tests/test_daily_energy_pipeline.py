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
            metrics=SimpleNamespace(evaluated=1, sent=0, skipped=1, failed=0)
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
