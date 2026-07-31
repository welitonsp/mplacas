from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base


class UserInvitationRecord(Base):
    """Convite pendente para um usuário se juntar a uma organização.

    Modelado como tabela própria (não como ``operational_users`` com um estado
    "pendente") para evitar ambiguidade semântica em toda query de usuário
    operacional. O token de convite nunca é persistido em claro — apenas seu
    hash SHA-256, seguindo o mesmo padrão já usado para refresh tokens
    (``auth.session_service.hash_refresh_token``) e segredos de credenciais
    (``credentials.service.hash_secret``).
    """

    __tablename__ = "user_invitations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    username: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("operational_users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    accepted_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("operational_users.id"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
