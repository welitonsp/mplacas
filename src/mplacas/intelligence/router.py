from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from mplacas.core.security import require_operations_key
from mplacas.db.session import SessionFactory
from mplacas.intelligence.cycle_service import EnergyCycleNotFoundError, analyze_persisted_cycle

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
