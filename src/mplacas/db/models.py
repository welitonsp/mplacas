from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date, DateTime, Enum, ForeignKey, Index, Numeric, String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mplacas.db.base import Base


class DataStatus(str, enum.Enum):
    PROVISIONAL = "PROVISIONAL"
    CONSOLIDATED = "CONSOLIDATED"
    INCOMPLETE = "INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


class Plant(Base):
    __tablename__ = "plants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), default="America/Sao_Paulo")
    installed_power_kwp: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    devices: Mapped[list[Device]] = relationship(
        back_populates="plant", cascade="all, delete-orphan"
    )


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("provider", "serial_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plants.id", ondelete="CASCADE"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(40), default="NEPVIEWER")
    serial_number: Mapped[str] = mapped_column(String(120))
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    plant: Mapped[Plant] = relationship(back_populates="devices")
    daily_energy: Mapped[list[DailyEnergy]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class DailyEnergy(Base):
    __tablename__ = "daily_energy"
    __table_args__ = (
        UniqueConstraint("device_id", "production_date"),
        Index("ix_daily_energy_date_device", "production_date", "device_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    production_date: Mapped[date] = mapped_column(Date)
    energy_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    status: Mapped[DataStatus] = mapped_column(Enum(DataStatus), default=DataStatus.PROVISIONAL)
    source: Mapped[str] = mapped_column(String(40), default="NEPVIEWER_V2")
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    device: Mapped[Device] = relationship(back_populates="daily_energy")
    versions: Mapped[list[DailyEnergyVersion]] = relationship(
        back_populates="daily_energy", cascade="all, delete-orphan"
    )


class DailyEnergyVersion(Base):
    __tablename__ = "daily_energy_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    daily_energy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_energy.id", ondelete="CASCADE"),
        index=True,
    )
    energy_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    status: Mapped[DataStatus] = mapped_column(Enum(DataStatus))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    daily_energy: Mapped[DailyEnergy] = relationship(back_populates="versions")
