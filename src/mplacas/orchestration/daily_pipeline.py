from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.alerts.job import AlertJobSummary
from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.operations import (
    AlertPipelineMetrics,
    AlertPipelineResult,
    run_operational_alert_pipeline,
)
from mplacas.alerts.telegram import TelegramAlertProvider
from mplacas.climate.collection_service import (
    ClimateCollectionResult,
    collect_and_persist_daily_climate,
)
from mplacas.climate.provider import ClimateProvider
from mplacas.observability.operations import observe_operation
from mplacas.photovoltaic.performance_service import (
    PerformanceComputationSummary,
    calculate_and_persist_daily_performance,
)
from mplacas.photovoltaic.loss_taxonomy_service import (
    LossTaxonomyComputationSummary,
    classify_and_persist_daily_losses,
)
from mplacas.photovoltaic.seasonal_baseline_service import (
    SeasonalBaselineComputationSummary,
    calculate_and_persist_seasonal_baseline,
)

logger = logging.getLogger(__name__)

ALERTS_SKIPPED_NO_EXPECTATION_REASON = (
    "no derivable expected daily production for alerts"
)


@dataclass(frozen=True, slots=True)
class DailyEnergyPipelineResult:
    plant_id: uuid.UUID
    target_date: date
    climate: ClimateCollectionResult
    performance: PerformanceComputationSummary
    seasonal_baseline: SeasonalBaselineComputationSummary
    loss_taxonomy: LossTaxonomyComputationSummary
    alerts: AlertPipelineResult


async def run_daily_energy_pipeline(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    target_date: date,
    climate_provider: ClimateProvider,
    alert_provider: TelegramAlertProvider,
    alert_destination_ref: str,
    expected_daily_production_kwh: Decimal | None,
    expected_cycle_production_kwh: Decimal | None = None,
    anomaly_days: int = 7,
    minimum_severity: AlertSeverity = AlertSeverity.WARNING,
    outbox_max_attempts: int = 10,
) -> DailyEnergyPipelineResult:
    """Collect climate data and dispatch alerts in one auditable execution.

    Alert delivery intents are persisted atomically with climate changes before
    the outbox dispatcher crosses the process boundary to Telegram.

    ``expected_daily_production_kwh`` may be ``None`` when the plant has no
    derivable expectation yet (e.g. it has no seasonal baseline). In that
    case climate collection, performance calculation, seasonal baseline
    calculation and loss taxonomy classification all run normally -- only
    the alert dispatch step is skipped, since alert severity depends on the
    expectation. This lets the baseline accumulate over successive runs
    instead of being permanently starved (ADR-069 § E9 correction).
    """
    if expected_daily_production_kwh is not None and expected_daily_production_kwh <= 0:
        raise ValueError("expected daily production must be positive")
    if expected_cycle_production_kwh is not None and expected_cycle_production_kwh <= 0:
        raise ValueError("expected cycle production must be positive")
    if not 1 <= anomaly_days <= 90:
        raise ValueError("anomaly days must be between 1 and 90")
    if not alert_destination_ref.strip():
        raise ValueError("alert destination reference is required")

    operation_fields = {
        "plant_id": str(plant_id),
        "target_date": target_date.isoformat(),
    }
    with observe_operation(
        logger,
        "daily_pipeline.climate_collection",
        **operation_fields,
    ) as climate_operation:
        climate = await collect_and_persist_daily_climate(
            session,
            plant_id=plant_id,
            provider=climate_provider,
            start_date=target_date,
            end_date=target_date,
            maximum_days=1,
        )
        climate_operation.add_result(
            received=climate.received,
            inserted=climate.persistence.inserted,
            updated=climate.persistence.updated,
            unchanged=climate.persistence.unchanged,
            solar_projected=(
                climate.solar_projection.inserted + climate.solar_projection.updated
            ),
            solar_skipped=climate.solar_projection.skipped,
        )
    with observe_operation(
        logger,
        "daily_pipeline.performance_calculation",
        **operation_fields,
    ) as performance_operation:
        performance = await calculate_and_persist_daily_performance(
            session,
            plant_id=plant_id,
            observation_date=target_date,
        )
        performance_operation.add_result(
            inserted=performance.inserted,
            updated=performance.updated,
            unchanged=performance.unchanged,
            skipped=performance.skipped,
        )
    with observe_operation(
        logger,
        "daily_pipeline.seasonal_baseline_calculation",
        **operation_fields,
    ) as baseline_operation:
        seasonal_baseline = await calculate_and_persist_seasonal_baseline(
            session,
            plant_id=plant_id,
            observation_date=target_date,
        )
        baseline_operation.add_result(
            inserted=seasonal_baseline.inserted,
            updated=seasonal_baseline.updated,
            unchanged=seasonal_baseline.unchanged,
            skipped=seasonal_baseline.skipped,
        )
    with observe_operation(
        logger,
        "daily_pipeline.loss_taxonomy_classification",
        **operation_fields,
    ) as loss_operation:
        loss_taxonomy = await classify_and_persist_daily_losses(
            session,
            plant_id=plant_id,
            observation_date=target_date,
        )
        loss_operation.add_result(
            inserted=loss_taxonomy.inserted,
            updated=loss_taxonomy.updated,
            unchanged=loss_taxonomy.unchanged,
            skipped=loss_taxonomy.skipped,
        )
    with observe_operation(
        logger,
        "daily_pipeline.alert_dispatch",
        **operation_fields,
    ) as alert_operation:
        if expected_daily_production_kwh is None:
            alerts = AlertPipelineResult(
                plant_id=plant_id,
                executive_available=False,
                anomaly_available=False,
                metrics=AlertPipelineMetrics(
                    evaluated=0,
                    sent=0,
                    skipped=0,
                    failed=0,
                    duplicates=0,
                    below_minimum_severity=0,
                ),
                job=AlertJobSummary(evaluated=0, sent=0, skipped=0, failed=0, results=()),
                outcome="skipped",
                unavailable_reason=ALERTS_SKIPPED_NO_EXPECTATION_REASON,
            )
            logger.info(
                "daily_pipeline_alert_dispatch_skipped",
                extra={
                    "plant_id": str(plant_id),
                    "target_date": target_date.isoformat(),
                    "reason": ALERTS_SKIPPED_NO_EXPECTATION_REASON,
                },
            )
        else:
            alerts = await run_operational_alert_pipeline(
                session,
                plant_id=plant_id,
                provider=alert_provider,
                destination_ref=alert_destination_ref,
                expected_daily_production_kwh=expected_daily_production_kwh,
                expected_cycle_production_kwh=expected_cycle_production_kwh,
                anomaly_days=anomaly_days,
                minimum_severity=minimum_severity,
                outbox_max_attempts=outbox_max_attempts,
            )
        alert_operation.add_result(
            evaluated=alerts.metrics.evaluated,
            sent=alerts.metrics.sent,
            skipped=alerts.metrics.skipped,
            failed=alerts.metrics.failed,
            outcome=alerts.outcome,
        )
    logger.info(
        "daily_energy_pipeline_completed",
        extra={
            "plant_id": str(plant_id),
            "target_date": target_date.isoformat(),
            "climate_received": climate.received,
            "solar_projected": (
                climate.solar_projection.inserted + climate.solar_projection.updated
            ),
            "solar_skipped": climate.solar_projection.skipped,
            "performance_calculated": performance.inserted + performance.updated,
            "performance_skipped": performance.skipped,
            "seasonal_baseline_calculated": (
                seasonal_baseline.inserted + seasonal_baseline.updated
            ),
            "seasonal_baseline_skipped": seasonal_baseline.skipped,
            "loss_assessments_calculated": (
                loss_taxonomy.inserted + loss_taxonomy.updated
            ),
            "loss_taxonomy_skipped": loss_taxonomy.skipped,
            "alerts_evaluated": alerts.metrics.evaluated,
            "alerts_sent": alerts.metrics.sent,
            "alerts_failed": alerts.metrics.failed,
            "alerts_outcome": alerts.outcome,
        },
    )
    return DailyEnergyPipelineResult(
        plant_id=plant_id,
        target_date=target_date,
        climate=climate,
        performance=performance,
        seasonal_baseline=seasonal_baseline,
        loss_taxonomy=loss_taxonomy,
        alerts=alerts,
    )
