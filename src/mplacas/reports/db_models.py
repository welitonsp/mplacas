from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, LargeBinary, String, Text, UniqueConstraint, func
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


class ReportExportTask(Base):
    """Tarefa de exportação assíncrona de relatório mensal.

    Máquina de estados: pending → processing → completed | failed.
    Quando ``artifact_url`` é None, o conteúdo fica em ``artifact_bytes``
    e o endpoint /download o serve diretamente. Quando GCS está configurado,
    ``artifact_url`` contém a URL assinada e ``artifact_bytes`` é None.
    """

    __tablename__ = "report_export_tasks"
    __table_args__ = (
        Index("ix_report_export_tasks_status_created", "status", "created_at"),
        Index("ix_report_export_tasks_plant_month", "plant_id", "reference_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reference_month: Mapped[str] = mapped_column(String(7), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    artifact_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    artifact_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    artifact_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
