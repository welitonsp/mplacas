from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base


class AlertDeliveryRecord(Base):
    __tablename__ = "alert_delivery_records"
    __table_args__ = (
        UniqueConstraint(
            "plant_id",
            "fingerprint",
            name="uq_alert_delivery_records_plant_fingerprint",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(40))
    destination_ref: Mapped[str] = mapped_column(String(128))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
