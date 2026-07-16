from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.audit.repository import AuditEventRepository
from mplacas.billing.parser import BillParseError, parse_equatorial_bill_text
from mplacas.billing.repository import UtilityBillRepository
from mplacas.core.config import get_settings
from mplacas.core.security import require_operations_key
from mplacas.db.models import Plant
from mplacas.db.session import SessionFactory

router = APIRouter(
    prefix="/billing",
    tags=["billing"],
    dependencies=[Depends(require_operations_key)],
)


class BillTextIntake(BaseModel):
    plant_id: uuid.UUID | None = None
    text: str = Field(min_length=20)


async def _resolve_plant_scope(
    session: AsyncSession,
    requested: uuid.UUID | None,
) -> uuid.UUID:
    if requested is not None:
        if await session.get(Plant, requested) is None:
            raise HTTPException(status_code=404, detail="plant not found")
        return requested
    plant_ids = list((await session.execute(select(Plant.id).limit(2))).scalars())
    if len(plant_ids) == 1:
        return plant_ids[0]
    if len(plant_ids) > 1:
        raise HTTPException(
            status_code=409,
            detail="plant_id is required when more than one plant exists",
        )
    raise HTTPException(
        status_code=409,
        detail="plant_id is required when no plant can be inferred",
    )


def _serialize(record) -> dict[str, object]:
    return {
        "id": str(record.id),
        "plant_id": str(record.plant_id),
        "distributor": record.distributor,
        "reference_month": record.reference_month,
        "cycle_start": record.cycle_start,
        "cycle_end": record.cycle_end,
        "billed_days": record.billed_days,
        "imported_kwh": str(record.imported_kwh),
        "injected_kwh": str(record.injected_kwh),
        "compensated_kwh": str(record.compensated_kwh),
        "credit_balance_kwh": str(record.credit_balance_kwh),
        "total_amount_brl": str(record.total_amount_brl),
        "public_lighting_brl": str(record.public_lighting_brl),
        "status": record.status.value,
        "created_at": record.created_at,
        "reviewed_at": record.reviewed_at,
    }


@router.post("/intake-text", status_code=status.HTTP_202_ACCEPTED)
async def intake_bill_text(request: Request, payload: BillTextIntake) -> dict[str, object]:
    settings = get_settings()
    if len(payload.text.encode("utf-8")) > settings.bill_text_max_bytes:
        raise HTTPException(status_code=413, detail="bill text exceeds configured size limit")
    try:
        bill = parse_equatorial_bill_text(payload.text)
    except BillParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async with SessionFactory() as session:
        plant_id = await _resolve_plant_scope(session, payload.plant_id)
        repository = UtilityBillRepository(session)
        try:
            record = await repository.create_pending(
                bill,
                plant_id=plant_id,
                source_text=payload.text,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await AuditEventRepository(session).record(
            request,
            action="billing.intake_text",
            resource_type="utility_bill",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details={
                "plant_id": str(record.plant_id),
                "reference_month": record.reference_month,
                "status": record.status.value,
            },
        )
        await session.commit()
        await session.refresh(record)
    return {"status": "pending_review", "bill": _serialize(record)}


@router.get("/pending")
async def pending_bills(
    plant_id: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    async with SessionFactory() as session:
        resolved = await _resolve_plant_scope(session, plant_id)
        records = await UtilityBillRepository(session).list_pending(
            limit=limit,
            plant_id=resolved,
        )
    return {"count": len(records), "items": [_serialize(record) for record in records]}


@router.post("/{bill_id}/confirm")
async def confirm_bill(
    request: Request,
    bill_id: uuid.UUID,
    plant_id: uuid.UUID | None = None,
) -> dict[str, object]:
    async with SessionFactory() as session:
        resolved = await _resolve_plant_scope(session, plant_id)
        repository = UtilityBillRepository(session)
        record = await repository.get(bill_id, plant_id=resolved)
        if record is None:
            raise HTTPException(status_code=404, detail="bill not found for plant")
        try:
            await repository.confirm(record)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await AuditEventRepository(session).record(
            request,
            action="billing.confirm",
            resource_type="utility_bill",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details={
                "plant_id": str(record.plant_id),
                "reference_month": record.reference_month,
            },
        )
        await session.commit()
        await session.refresh(record)
    return {"status": "confirmed", "bill": _serialize(record)}


@router.post("/{bill_id}/reject")
async def reject_bill(
    request: Request,
    bill_id: uuid.UUID,
    plant_id: uuid.UUID | None = None,
) -> dict[str, object]:
    async with SessionFactory() as session:
        resolved = await _resolve_plant_scope(session, plant_id)
        repository = UtilityBillRepository(session)
        record = await repository.get(bill_id, plant_id=resolved)
        if record is None:
            raise HTTPException(status_code=404, detail="bill not found for plant")
        try:
            await repository.reject(record)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await AuditEventRepository(session).record(
            request,
            action="billing.reject",
            resource_type="utility_bill",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details={
                "plant_id": str(record.plant_id),
                "reference_month": record.reference_month,
            },
        )
        await session.commit()
        await session.refresh(record)
    return {"status": "rejected", "bill": _serialize(record)}
