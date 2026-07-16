from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base


class BillStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class UtilityBillRecord(Base):
    __tablename__ = "utility_bills"
    __table_args__ = (
        UniqueConstraint(
            "plant_id",
            "distributor",
            "reference_month",
            "cycle_start",
            "cycle_end",
            name="uq_utility_bills_plant_cycle",
        ),
        Index(
            "ix_utility_bills_plant_status_cycle",
            "plant_id",
            "status",
            "cycle_end",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plants.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    distributor: Mapped[str] = mapped_column(String(60), index=True)
    reference_month: Mapped[str] = mapped_column(String(7), index=True)
    cycle_start: Mapped[date] = mapped_column(Date)
    cycle_end: Mapped[date] = mapped_column(Date)
    billed_days: Mapped[int]
    imported_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    injected_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    compensated_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    credit_balance_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    total_amount_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    public_lighting_brl: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0")
    )
    status: Mapped[BillStatus] = mapped_column(
        Enum(BillStatus), default=BillStatus.PENDING_REVIEW, index=True
    )
    source_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
