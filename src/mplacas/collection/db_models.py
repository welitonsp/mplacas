from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base


class CollectionTaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CollectionTaskRecord(Base):
    """Tarefa de coleta por usina, processada por workers.

    Segue a mesma mecânica de claim atômico e backoff do outbox de eventos,
    aplicada à coleta desacoplada do ciclo do job diário. A unicidade de
    ``deduplication_key`` garante idempotência ao reenfileirar a mesma
    (usina, tipo, data-alvo).
    """

    __tablename__ = "collection_tasks"
    __table_args__ = (
        Index(
            "ix_collection_tasks_claimable",
            "task_type",
            "status",
            "available_at",
            "created_at",
        ),
        Index("ix_collection_tasks_plant_created", "plant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_date: Mapped[str] = mapped_column(String(10), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )
    status: Mapped[CollectionTaskStatus] = mapped_column(
        Enum(CollectionTaskStatus),
        nullable=False,
        default=CollectionTaskStatus.PENDING,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
