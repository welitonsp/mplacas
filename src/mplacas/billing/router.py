from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from mplacas.billing.parser import BillParseError, parse_equatorial_bill_text
from mplacas.billing.repository import UtilityBillRepository
from mplacas.core.config import get_settings
from mplacas.core.security import require_operations_key
from mplacas.db.session import SessionFactory

router = APIRouter(
    prefix="/billing",
    tags=["billing"],
    dependencies=[Depends(require_operations_key)],
)


class BillTextIntake(BaseModel):
    text: str = Field(min_length=20)


def _serialize(record) -> dict[str, object]:
    return {
        "id": str(record.id),
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
async def intake_bill_text(payload: BillTextIntake) -> dict[str, object]:
    settings = get_settings()
    if len(payload.text.encode("utf-8")) > settings.bill_text_max_bytes:
        raise HTTPException(status_code=413, detail="bill text exceeds configured size limit")
    try:
        bill = parse_equatorial_bill_text(payload.text)
    except BillParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async with SessionFactory() as session:
        repository = UtilityBillRepository(session)
        record = await repository.create_pending(bill, source_text=payload.text)
        await session.commit()
        await session.refresh(record)
    return {"status": "pending_review", "bill": _serialize(record)}


@router.get("/pending")
async def pending_bills(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
    async with SessionFactory() as session:
        records = await UtilityBillRepository(session).list_pending(limit)
    return {"count": len(records), "items": [_serialize(record) for record in records]}


@router.post("/{bill_id}/confirm")
async def confirm_bill(bill_id: uuid.UUID) -> dict[str, object]:
    async with SessionFactory() as session:
        repository = UtilityBillRepository(session)
        record = await repository.get(bill_id)
        if record is None:
            raise HTTPException(status_code=404, detail="bill not found")
        try:
            await repository.confirm(record)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await session.commit()
        await session.refresh(record)
    return {"status": "confirmed", "bill": _serialize(record)}


@router.post("/{bill_id}/reject")
async def reject_bill(bill_id: uuid.UUID) -> dict[str, object]:
    async with SessionFactory() as session:
        repository = UtilityBillRepository(session)
        record = await repository.get(bill_id)
        if record is None:
            raise HTTPException(status_code=404, detail="bill not found")
        try:
            await repository.reject(record)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await session.commit()
        await session.refresh(record)
    return {"status": "rejected", "bill": _serialize(record)}
