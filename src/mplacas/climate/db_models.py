from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base


class DailyClimateObservationRecord(Base):
    __tablename__ = "daily_climate_observations"
    __table_args__ = (UniqueConstraint("plant_id", "observation_date", "source"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plants.id", ondelete="CASCADE"))
    observation_date: Mapped[date] = mapped_column(Date)
    irradiation_kwh_m2: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    cloud_cover_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    precipitation_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="MANUAL")
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
