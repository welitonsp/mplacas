from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.billing.db_models import BillStatus
from mplacas.billing.models import UtilityBill
from mplacas.billing.repository import UtilityBillRepository
from mplacas.db.base import Base


@pytest.mark.asyncio
async def test_bill_requires_human_confirmation_and_is_idempotent() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bill = UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month="2026-06",
        cycle_start=date(2026, 5, 18),
        cycle_end=date(2026, 6, 16),
        billed_days=30,
        imported_kwh=Decimal("278"),
        injected_kwh=Decimal("182"),
        compensated_kwh=Decimal("278"),
        credit_balance_kwh=Decimal("63.98"),
        total_amount_brl=Decimal("80.21"),
        public_lighting_brl=Decimal("30.21"),
    )
    async with factory() as session:
        repository = UtilityBillRepository(session)
        first = await repository.create_pending(bill, source_text="synthetic bill text")
        second = await repository.create_pending(bill, source_text="synthetic bill text")
        assert first.id == second.id
        assert first.status is BillStatus.PENDING_REVIEW
        await repository.confirm(first)
        assert first.status is BillStatus.CONFIRMED
        assert first.reviewed_at is not None
        with pytest.raises(ValueError, match="only pending"):
            await repository.reject(first)
        await session.commit()
    await engine.dispose()
