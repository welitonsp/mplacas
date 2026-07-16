from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base


class AuditEventRecord(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_action_created_at", "action", "created_at"),
        Index("ix_audit_events_resource", "resource_type", "resource_id"),
        Index("ix_audit_events_actor", "actor_role", "actor_credential_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_type: Mapped[str] = mapped_column(String(80), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    outcome: Mapped[str] = mapped_column(String(40), index=True)
    actor_role: Mapped[str] = mapped_column(String(40))
    actor_credential_id: Mapped[str] = mapped_column(String(128))
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
