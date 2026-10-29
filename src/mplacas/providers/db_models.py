from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base


class ProviderAccountRecord(Base):
    """Conexão de uma usina com a conta do fabricante do inversor (ADR-091).

    Login e senha ficam juntos em ``ciphertext`` (AES-256-GCM, ``core.secret_box``),
    amarrados por AAD a ``plant_id`` e ``provider``. ``login_hint`` é só para
    a tela reconhecer a conta; ``account_fingerprint`` impede a mesma conta em
    duas usinas sem guardar o login. Conexão removida perde o texto cifrado.
    """

    __tablename__ = "provider_accounts"
    __table_args__ = (
        UniqueConstraint("plant_id", name="uq_provider_accounts_plant"),
        UniqueConstraint(
            "provider",
            "account_fingerprint",
            name="uq_provider_accounts_provider_fingerprint",
        ),
        CheckConstraint(
            "key_version IS NULL OR key_version >= 1", name="ck_provider_accounts_key_version"
        ),
        CheckConstraint(
            "(active AND ciphertext IS NOT NULL AND key_version IS NOT NULL "
            "AND account_fingerprint IS NOT NULL) "
            "OR (NOT active AND ciphertext IS NULL AND key_version IS NULL "
            "AND account_fingerprint IS NULL)",
            name="ck_provider_accounts_secret_only_when_active",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plants.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    login_hint: Mapped[str] = mapped_column(String(120), nullable=False)
    account_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    key_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)

    def __repr__(self) -> str:
        return (
            f"ProviderAccountRecord(id={self.id}, plant_id={self.plant_id}, "
            f"provider={self.provider}, active={self.active})"
        )
