from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from mplacas.core.security import require_operations_key
from mplacas.db.session import SessionFactory
from mplacas.intelligence.anomaly_service import (
    AnomalyDataNotFoundError,
    analyze_recent_persisted_anomalies,
)
from mplacas.intelligence.cycle_service import EnergyCycleNotFoundError, analyze_persisted_cycle
from mplacas.intelligence.executive_service import build_executive_dashboard
from mplacas.intelligence.history_service import (
    EnergyHistoryNotFoundError,
    compare_latest_confirmed_cycles,
)

router = APIRouter(
    prefix="/energy",
    tags=["energy"],
    dependencies=[Depends(require_operations_key)],
)


def _serialize(result) -> dict[str, object]:
    intelligence = result.intelligence
    reconciliation = intelligence.reconciliation
    return {
        "bill_id": str(result.bill_id),
        "plant_id": str(result.plant_id),
        "reference_month": result.reference_month,
        "quality": {
            "missing_days": result.quality.missing_days,
            "provisional_days": result.quality.provisional_days,
            "incomplete_days": result.quality.incomplete_days,
            "unavailable_days": result.quality.unavailable_days,
        },
        "indicators": {
            "cycle_production_kwh": str(reconciliation.cycle_production_kwh),
            "imported_kwh": str(reconciliation.imported_kwh),
            "injected_kwh": str(reconciliation.injected_kwh),
            "estimated_self_consumption_kwh": str(reconciliation.estimated_self_consumption_kwh),
            "estimated_total_consumption_kwh": str(reconciliation.estimated_total_consumption_kwh),
            "self_consumption_rate_percent": str(reconciliation.self_consumption_rate_percent),
            "self_sufficiency_rate_percent": str(reconciliation.self_sufficiency_rate_percent),
            "grid_dependency_rate_percent": str(intelligence.grid_dependency_rate_percent),
            "exported_generation_rate_percent": str(intelligence.exported_generation_rate_percent),
            "credit_coverage_rate_percent": str(intelligence.credit_coverage_rate_percent),
            "bill_energy_component_brl": str(intelligence.bill_energy_component_brl),
            "health_score": intelligence.health_score,
        },
        "diagnostics": [
            {
                "code": item.code,
                "severity": item.severity.value,
                "message": item.message,
                "recommended_action": item.recommended_action,
            }
            for item in intelligence.diagnostics
        ],
    }


def _serialize_metric(metric) -> dict[str, object]:
    return {
        "absolute_delta": str(metric.absolute_delta),
        "percent_delta": str(metric.percent_delta) if metric.percent_delta is not None else None,
        "direction": metric.direction.value,
    }


def _serialize_trend(result) -> dict[str, object]:
    comparison = result.comparison
    return {
        "plant_id": str(result.plant_id),
        "current_reference_month": comparison.current_reference_month,
        "previous_reference_month": comparison.previous_reference_month,
        "metrics": {
            "production": _serialize_metric(comparison.production),
            "total_consumption": _serialize_metric(comparison.total_consumption),
            "imported_energy": _serialize_metric(comparison.imported_energy),
            "self_sufficiency_delta_points": str(comparison.self_sufficiency_delta_points),
            "health_score_delta": comparison.health_score_delta,
        },
        "diagnostics": [
            {
                "code": item.code,
                "severity": item.severity,
                "message": item.message,
                "recommended_action": item.recommended_action,
            }
            for item in result.diagnostics
        ],
    }


def _serialize_executive(result) -> dict[str, object]:
    return {
        "plant_id": str(result.plant_id),
        "status": result.status.value,
        "headline": result.headline,
        "priority_actions": list(result.priority_actions),
        "current_cycle": _serialize(result.current_cycle),
        "trend": _serialize_trend(result.trend) if result.trend is not None else None,
    }


def _serialize_anomalies(result) -> dict[str, object]:
    return {
        "plant_id": str(result.plant_id),
        "period": {
            "start_date": result.start_date.isoformat(),
            "end_date": result.end_date.isoformat(),
        },
        "days_analyzed": result.days_analyzed,
        "current_streak_days": result.current_streak_days,
        "worst_level": result.worst_level.value,
        "daily": [
            {
                "date": item.observation_date.isoformat(),
                "actual_production_kwh": str(item.actual_production_kwh),
                "expected_production_kwh": str(item.expected_production_kwh),
                "irradiation_kwh_m2": (
                    str(item.irradiation_kwh_m2) if item.irradiation_kwh_m2 is not None else None
                ),
                "level": item.assessment.level.value,
                "deviation_kwh": (
                    str(item.assessment.deviation_kwh)
                    if item.assessment.deviation_kwh is not None
                    else None
                ),
                "deviation_percent": (
                    str(item.assessment.deviation_percent)
                    if item.assessment.deviation_percent is not None
                    else None
                ),
                "diagnostics": [
                    {
                        "code": diagnostic.code,
                        "level": diagnostic.level.value,
                        "message": diagnostic.message,
                        "recommended_action": diagnostic.recommended_action,
                    }
                    for diagnostic in item.assessment.diagnostics
                ],
            }
            for item in result.daily
        ],
    }


@router.get("/cycles/{bill_id}")
async def energy_cycle_summary(
    bill_id: uuid.UUID,
    plant_id: uuid.UUID = Query(...),
    expected_production_kwh: Decimal | None = Query(default=None, ge=0),
) -> dict[str, object]:
    async with SessionFactory() as session:
        try:
            result = await analyze_persisted_cycle(
                session,
                bill_id=bill_id,
                plant_id=plant_id,
                expected_production_kwh=expected_production_kwh,
            )
        except EnergyCycleNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize(result)


@router.get("/trends/latest")
async def latest_energy_trend(
    plant_id: uuid.UUID = Query(...),
    stable_tolerance_percent: Decimal = Query(default=Decimal("2.0"), ge=0, le=100),
) -> dict[str, object]:
    async with SessionFactory() as session:
        try:
            result = await compare_latest_confirmed_cycles(
                session,
                plant_id=plant_id,
                stable_tolerance_percent=stable_tolerance_percent,
            )
        except (EnergyHistoryNotFoundError, EnergyCycleNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_trend(result)


@router.get("/executive/latest")
async def latest_executive_dashboard(
    plant_id: uuid.UUID = Query(...),
    expected_production_kwh: Decimal | None = Query(default=None, ge=0),
    stable_tolerance_percent: Decimal = Query(default=Decimal("2.0"), ge=0, le=100),
) -> dict[str, object]:
    async with SessionFactory() as session:
        try:
            result = await build_executive_dashboard(
                session,
                plant_id=plant_id,
                expected_production_kwh=expected_production_kwh,
                stable_tolerance_percent=stable_tolerance_percent,
            )
        except EnergyCycleNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_executive(result)


@router.get("/anomalies/latest")
async def latest_energy_anomalies(
    plant_id: uuid.UUID = Query(...),
    expected_daily_production_kwh: Decimal = Query(..., gt=0),
    days: int = Query(default=7, ge=1, le=90),
) -> dict[str, object]:
    async with SessionFactory() as session:
        try:
            result = await analyze_recent_persisted_anomalies(
                session,
                plant_id=plant_id,
                expected_daily_production_kwh=expected_daily_production_kwh,
                days=days,
            )
        except AnomalyDataNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_anomalies(result)
