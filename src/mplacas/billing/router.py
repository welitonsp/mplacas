from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from mplacas.audit.repository import AuditEventRepository
from mplacas.billing.parser import BillParseError, parse_equatorial_bill_text
from mplacas.billing.repository import UtilityBillRepository
from mplacas.core.config import get_settings
from mplacas.core.tenancy import AdminPlant, AdminPrincipal, resolve_admin_plant_scope
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_principal_context
from mplacas.reports.snapshot import materialize_monthly_report_snapshot

router = APIRouter(
    prefix="/billing",
    tags=["billing"],
)


class BillTextIntake(BaseModel):
    plant_id: uuid.UUID | None = None
    text: str = Field(min_length=20)


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
async def intake_bill_text(
    request: Request, payload: BillTextIntake, principal: AdminPrincipal
) -> dict[str, object]:
    # plant_id is carried in the request body (not a query param), so it
    # cannot be resolved via the AdminPlant dependency directly — reuse the
    # same organization-scoped resolve+validate logic explicitly instead.
    # Resolved before parsing the (untrusted) bill text so a cross-tenant
    # request is rejected without ever processing its payload.
    scoped = await resolve_admin_plant_scope(principal, payload.plant_id)
    plant_id = scoped.plant_id

    settings = get_settings()
    if len(payload.text.encode("utf-8")) > settings.bill_text_max_bytes:
        raise HTTPException(status_code=413, detail="bill text exceeds configured size limit")
    try:
        bill = parse_equatorial_bill_text(payload.text)
    except BillParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
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
    scoped: AdminPlant,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        records = await UtilityBillRepository(session).list_pending(
            limit=limit,
            plant_id=scoped.plant_id,
        )
    return {"count": len(records), "items": [_serialize(record) for record in records]}


@router.post("/{bill_id}/confirm")
async def confirm_bill(
    request: Request,
    bill_id: uuid.UUID,
    principal: AdminPrincipal,
) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        repository = UtilityBillRepository(session)
        record = await repository.get_by_id(bill_id)
        if record is None:
            raise HTTPException(status_code=404, detail="bill not found for plant")
        # The plant is already on the bill row (ADR-069 § E.2 opção 5) — no
        # plant_id is inferred or accepted from the caller, so a caller with
        # a restricted PlantScope (or a different organization entirely)
        # cannot confirm a bill outside its own scope. 404, not 403: same
        # "do not reveal cross-tenant existence" convention used by
        # resolve_read_plant / resolve_admin_plant_scope.
        principal.require_plant_access(record.plant_id)
        try:
            await repository.confirm(record)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        report_snapshot = await materialize_monthly_report_snapshot(
            session,
            bill_id=record.id,
            plant_id=record.plant_id,
        )
        await AuditEventRepository(session).record(
            request,
            action="billing.confirm",
            resource_type="utility_bill",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details={
                "plant_id": str(record.plant_id),
                "reference_month": record.reference_month,
                "report_snapshot_id": str(report_snapshot.id),
                "report_snapshot_sha256": report_snapshot.payload_sha256,
            },
        )
        await session.commit()
        await session.refresh(record)
    return {
        "status": "confirmed",
        "bill": _serialize(record),
        "report_snapshot": {
            "id": str(report_snapshot.id),
            "sha256": report_snapshot.payload_sha256,
            "schema_version": report_snapshot.report.schema_version,
            "calculation_version": report_snapshot.report.calculation_version,
        },
    }


@router.post("/{bill_id}/reject")
async def reject_bill(
    request: Request,
    bill_id: uuid.UUID,
    principal: AdminPrincipal,
) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        repository = UtilityBillRepository(session)
        record = await repository.get_by_id(bill_id)
        if record is None:
            raise HTTPException(status_code=404, detail="bill not found for plant")
        # Same "derive plant from the record" rationale as confirm_bill above.
        principal.require_plant_access(record.plant_id)
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
