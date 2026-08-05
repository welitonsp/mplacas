from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base

DEFAULT_ORGANIZATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class OrganizationRecord(Base):
    """Tenant raiz do sistema multitenancy."""

    __tablename__ = "organizations"
    __table_args__ = (UniqueConstraint("slug", name="uq_organizations_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, nullable=True, index=True
    )
    telegram_allowed_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    default_plant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "plants.id",
            ondelete="SET NULL",
            name="fk_organizations_default_plant_id",
        ),
        nullable=True,
    )
