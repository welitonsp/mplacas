from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base


class PipelineExecutionStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class PipelineExecutionRecord(Base):
    __tablename__ = "pipeline_executions"
    __table_args__ = (UniqueConstraint("plant_id", "target_date", name="uq_pipeline_execution_plant_date"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plants.id", ondelete="CASCADE"), index=True)
    target_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[PipelineExecutionStatus] = mapped_column(
        Enum(PipelineExecutionStatus), default=PipelineExecutionStatus.RUNNING, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    stage: Mapped[str] = mapped_column(String(40), default="STARTED")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
