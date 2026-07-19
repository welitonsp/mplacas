from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.billing.models import UtilityBill
from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE


@dataclass(frozen=True, slots=True)
class ConfirmedBill:
    """Immutable billing-domain view exposed to read consumers."""

    id: uuid.UUID
    plant_id: uuid.UUID
    bill: UtilityBill


def _to_confirmed_bill(record: UtilityBillRecord) -> ConfirmedBill:
    return ConfirmedBill(
        id=record.id,
        plant_id=record.plant_id,
        bill=UtilityBill(
            distributor=record.distributor,
            reference_month=record.reference_month,
            cycle_start=record.cycle_start,
            cycle_end=record.cycle_end,
            billed_days=record.billed_days,
            imported_kwh=record.imported_kwh,
            injected_kwh=record.injected_kwh,
            compensated_kwh=record.compensated_kwh,
            credit_balance_kwh=record.credit_balance_kwh,
            total_amount_brl=record.total_amount_brl,
            public_lighting_brl=record.public_lighting_brl,
        ),
    )


class ConfirmedBillReadRepository:
    """Single read boundary for plant-scoped confirmed utility bills."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
    ) -> None:
        self._session = session
        self._plant_scope = plant_scope

    async def by_id(
        self,
        bill_id: uuid.UUID,
        *,
        plant_id: uuid.UUID,
    ) -> ConfirmedBill | None:
        if not self._plant_scope.allows(plant_id):
            return None
        record = await self._session.scalar(
            select(UtilityBillRecord).where(
                UtilityBillRecord.id == bill_id,
                UtilityBillRecord.plant_id == plant_id,
                UtilityBillRecord.status == BillStatus.CONFIRMED,
            )
        )
        return _to_confirmed_bill(record) if record is not None else None

    async def latest(self, *, plant_id: uuid.UUID) -> ConfirmedBill | None:
        records = await self._latest(plant_id=plant_id, limit=1)
        return records[0] if records else None

    async def two_latest(self, *, plant_id: uuid.UUID) -> tuple[ConfirmedBill, ...]:
        return await self._latest(plant_id=plant_id, limit=2)

    async def _latest(
        self,
        *,
        plant_id: uuid.UUID,
        limit: int,
    ) -> tuple[ConfirmedBill, ...]:
        if not self._plant_scope.allows(plant_id):
            return ()
        records = (
            await self._session.execute(
                select(UtilityBillRecord)
                .where(
                    UtilityBillRecord.plant_id == plant_id,
                    UtilityBillRecord.status == BillStatus.CONFIRMED,
                )
                .order_by(
                    desc(UtilityBillRecord.cycle_end),
                    desc(UtilityBillRecord.created_at),
                )
                .limit(limit)
            )
        ).scalars()
        return tuple(_to_confirmed_bill(record) for record in records)
