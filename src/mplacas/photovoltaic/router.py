"""Read-only HTTP surface for the photovoltaic modeling chain (ADR-065).

Thin router: every handler opens a session, applies tenant context, delegates
to `read_service.py` for queries and `serialization.py` for shaping the
response, then closes. No calculation happens here — that stays the
exclusive responsibility of the daily pipeline (ADR-046).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from mplacas.core.tenancy import ReadPlant
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_principal_context
from mplacas.photovoltaic.read_service import (
    InvalidPerformanceWindowError,
    PhotovoltaicBaselineNotFoundError,
    PhotovoltaicLossAssessmentNotFoundError,
    PhotovoltaicPerformanceNotFoundError,
    get_latest_baseline,
    get_latest_losses,
    get_latest_performance,
    get_performance_series,
    get_summary,
)
from mplacas.photovoltaic.serialization import (
    LOSS_UNITS,
    serialize_baseline,
    serialize_loss_assessment,
    serialize_performance,
)

router = APIRouter(
    prefix="/photovoltaic",
    tags=["photovoltaic"],
)


@router.get("/performance/latest")
async def latest_performance(scoped: ReadPlant) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        try:
            record = await get_latest_performance(session, plant_id=scoped.plant_id)
        except PhotovoltaicPerformanceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return serialize_performance(record)


@router.get("/performance")
async def performance_series(
    scoped: ReadPlant,
    start_date: date = Query(...),
    end_date: date = Query(...),
) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        try:
            records = await get_performance_series(
                session,
                plant_id=scoped.plant_id,
                start_date=start_date,
                end_date=end_date,
            )
        except InvalidPerformanceWindowError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    items = [serialize_performance(record) for record in records]
    units = items[0]["units"] if items else None
    return {
        "plant_id": str(scoped.plant_id),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "count": len(items),
        "units": units,
        "items": items,
    }


@router.get("/baseline/latest")
async def latest_baseline(scoped: ReadPlant) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        try:
            record = await get_latest_baseline(session, plant_id=scoped.plant_id)
        except PhotovoltaicBaselineNotFoundError as exc:
            detail = f"no photovoltaic baseline result for this plant: {exc.reason}"
            if exc.reference_complete_on is not None:
                detail = f"{detail} (reference_complete_on={exc.reference_complete_on.isoformat()})"
            raise HTTPException(status_code=404, detail=detail) from exc
    return serialize_baseline(record)


@router.get("/losses/latest")
async def latest_losses(scoped: ReadPlant) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        try:
            records = await get_latest_losses(session, plant_id=scoped.plant_id)
        except PhotovoltaicLossAssessmentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "plant_id": str(scoped.plant_id),
        "observation_date": records[0].observation_date.isoformat(),
        "units": dict(LOSS_UNITS),
        "items": [serialize_loss_assessment(record) for record in records],
    }


@router.get("/summary")
async def summary(scoped: ReadPlant) -> dict[str, object]:
    """Composed dashboard read. Always 200 when the caller has plant access.

    Deliberate exception to the 404 rule used by the `/…/latest` routes
    (ADR-065 section 5): a dashboard whose degradation card does not exist
    yet is not a failed request.
    """
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        result = await get_summary(session, plant_id=scoped.plant_id)
    return {
        "plant_id": str(result.plant_id),
        "performance": (
            serialize_performance(result.performance)
            if result.performance is not None
            else None
        ),
        "performance_unavailable_reason": result.performance_unavailable_reason,
        "baseline": (
            serialize_baseline(result.baseline) if result.baseline is not None else None
        ),
        "baseline_unavailable_reason": result.baseline_unavailable_reason,
        "reference_complete_on": (
            result.reference_complete_on.isoformat()
            if result.reference_complete_on is not None
            else None
        ),
        "losses": (
            [serialize_loss_assessment(record) for record in result.losses]
            if result.losses is not None
            else None
        ),
        "losses_unavailable_reason": result.losses_unavailable_reason,
        "expected_daily_production_kwh": (
            str(result.expected_production.expected_daily_production_kwh)
            if result.expected_production is not None
            else None
        ),
        "expected_daily_production_model_version": (
            result.expected_production.model_version
            if result.expected_production is not None
            else None
        ),
        "expected_daily_production_nature": (
            result.expected_production.nature
            if result.expected_production is not None
            else None
        ),
        "expected_daily_production_unavailable_reason": (
            result.expected_production_unavailable_reason
        ),
    }
