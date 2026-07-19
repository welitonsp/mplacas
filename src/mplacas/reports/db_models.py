from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base


class MonthlyReportSnapshotRecord(Base):
    __tablename__ = "monthly_report_snapshots"
    __table_args__ = (
        UniqueConstraint("bill_id", name="uq_monthly_report_snapshots_bill"),
        Index(
            "ix_monthly_report_snapshots_plant_reference",
            "plant_id",
            "reference_month",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("utility_bills.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reference_month: Mapped[str] = mapped_column(String(7), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
