from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base


class AlertDeliveryRecord(Base):
    __tablename__ = "alert_delivery_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(40))
    destination_ref: Mapped[str] = mapped_column(String(128))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
