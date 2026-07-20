from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.billing.models import UtilityBill
from mplacas.db.models import Plant


class UtilityBillRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending(
        self,
        bill: UtilityBill,
        *,
        source_text: str,
        plant_id: uuid.UUID,
    ) -> UtilityBillRecord:
        bill.validate()
        if await self._session.get(Plant, plant_id) is None:
            raise ValueError("plant not found")
        source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        existing = await self._session.scalar(
            select(UtilityBillRecord).where(UtilityBillRecord.source_hash == source_hash)
        )
        if existing is not None:
            if existing.plant_id != plant_id:
                raise ValueError("bill source is already associated with another plant")
            return existing
        record = UtilityBillRecord(
            plant_id=plant_id,
            distributor=bill.distributor,
            reference_month=bill.reference_month,
            cycle_start=bill.cycle_start,
            cycle_end=bill.cycle_end,
            billed_days=bill.billed_days,
            imported_kwh=bill.imported_kwh,
            injected_kwh=bill.injected_kwh,
            compensated_kwh=bill.compensated_kwh,
            credit_balance_kwh=bill.credit_balance_kwh,
            total_amount_brl=bill.total_amount_brl,
            public_lighting_brl=bill.public_lighting_brl,
            generation_cycle_kwh=bill.generation_cycle_kwh,
            status=BillStatus.PENDING_REVIEW,
            source_hash=source_hash,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(
        self,
        record_id: uuid.UUID,
        *,
        plant_id: uuid.UUID,
    ) -> UtilityBillRecord | None:
        record = await self._session.get(UtilityBillRecord, record_id)
        if record is None or record.plant_id != plant_id:
            return None
        return record

    async def list_pending(
        self,
        limit: int = 20,
        *,
        plant_id: uuid.UUID,
    ) -> list[UtilityBillRecord]:
        statement = select(UtilityBillRecord).where(
            UtilityBillRecord.status == BillStatus.PENDING_REVIEW,
            UtilityBillRecord.plant_id == plant_id,
        )
        result = await self._session.execute(
            statement.order_by(desc(UtilityBillRecord.created_at)).limit(
                max(1, min(limit, 100))
            )
        )
        return list(result.scalars())

    async def confirm(self, record: UtilityBillRecord) -> UtilityBillRecord:
        if record.status is not BillStatus.PENDING_REVIEW:
            raise ValueError("only pending bills can be confirmed")
        record.status = BillStatus.CONFIRMED
        record.reviewed_at = datetime.now(UTC)
        await self._session.flush()
        return record

    async def reject(self, record: UtilityBillRecord) -> UtilityBillRecord:
        if record.status is not BillStatus.PENDING_REVIEW:
            raise ValueError("only pending bills can be rejected")
        record.status = BillStatus.REJECTED
        record.reviewed_at = datetime.now(UTC)
        await self._session.flush()
        return record
