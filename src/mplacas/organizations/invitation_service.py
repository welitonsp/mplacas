from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.core.principal import OperationsRole
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_db_models import UserInvitationRecord

_SECRET_BYTES = 32
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvitationError(ValueError):
    """Erro de domínio nas operações de convite."""


class InvitationConsumeError(ValueError):
    """Erro único para todo convite que não pode ser consumido.

    Deliberadamente não diferencia "expirado" de "revogado" de "já aceito" de
    "não encontrado" na mensagem pública, para não vazar informação sobre o
    estado do convite a quem apenas possui (ou adivinhou) um token. A razão
    específica é logada internamente pelo chamador quando necessário.
    """


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_invitation_token() -> str:
    return secrets.token_urlsafe(_SECRET_BYTES)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_email_like(value: str) -> bool:
    return bool(_EMAIL_PATTERN.match(value))


class InvitationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        organization_id: uuid.UUID,
        username: str,
        role: OperationsRole,
        created_by_user_id: uuid.UUID | None,
        ttl_seconds: int,
    ) -> tuple[UserInvitationRecord, str]:
        """Cria um convite e devolve o registro e o token em texto claro.

        O token em claro é devolvido apenas aqui, no momento da criação — só o
        hash SHA-256 é persistido.
        """
        normalized_username = username.strip()
        if not normalized_username:
            raise InvitationError("username is required")
        if not _is_email_like(normalized_username):
            raise InvitationError("username must look like an email address")

        token = generate_invitation_token()
        record = UserInvitationRecord(
            organization_id=organization_id,
            username=normalized_username,
            role=role.value,
            token_hash=hash_invitation_token(token),
            created_by_user_id=created_by_user_id,
            expires_at=_utc_now() + timedelta(seconds=ttl_seconds),
        )
        self._session.add(record)
        await self._session.flush()
        return record, token

    async def list(
        self,
        *,
        organization_id: uuid.UUID,
    ) -> list[UserInvitationRecord]:
        result = await self._session.scalars(
            select(UserInvitationRecord)
            .where(UserInvitationRecord.organization_id == organization_id)
            .order_by(UserInvitationRecord.created_at)
        )
        return list(result)

    async def revoke(
        self,
        *,
        invitation_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> bool:
        record = await self._session.scalar(
            select(UserInvitationRecord).where(
                UserInvitationRecord.id == invitation_id,
                UserInvitationRecord.organization_id == organization_id,
            )
        )
        if record is None:
            return False
        if record.revoked_at is None:
            record.revoked_at = _utc_now()
            await self._session.flush()
        return True

    async def consume(self, *, token: str) -> UserInvitationRecord:
        """Resolve um token de convite ainda válido para consumo.

        Não marca o convite como aceito — isso é responsabilidade de quem
        chama este método (ver :meth:`mark_accepted`), para não marcar como
        aceito antes de confirmar que a criação do usuário teve sucesso.
        """
        record = await self._session.scalar(
            select(UserInvitationRecord)
            .join(
                OrganizationRecord,
                UserInvitationRecord.organization_id == OrganizationRecord.id,
            )
            .where(UserInvitationRecord.token_hash == hash_invitation_token(token))
        )
        if record is None:
            raise InvitationConsumeError("invitation cannot be consumed")

        organization = await self._session.get(
            OrganizationRecord, record.organization_id
        )
        if organization is None or not organization.active:
            raise InvitationConsumeError("invitation cannot be consumed")
        if record.revoked_at is not None:
            raise InvitationConsumeError("invitation cannot be consumed")
        if record.accepted_at is not None:
            raise InvitationConsumeError("invitation cannot be consumed")
        if _as_utc(record.expires_at) <= _utc_now():
            raise InvitationConsumeError("invitation cannot be consumed")
        return record

    async def mark_accepted(
        self,
        *,
        invitation_id: uuid.UUID,
        accepted_user_id: uuid.UUID,
    ) -> bool:
        """Marca o convite como aceito com um UPDATE condicional.

        A cláusula ``WHERE accepted_at IS NULL`` protege contra corrida: se
        duas chamadas concorrentes tentarem aceitar o mesmo convite, apenas a
        primeira altera uma linha (``rowcount == 1``); a segunda encontra
        ``accepted_at`` já preenchido e não altera nada.
        """
        result = await self._session.execute(
            update(UserInvitationRecord)
            .where(
                UserInvitationRecord.id == invitation_id,
                UserInvitationRecord.accepted_at.is_(None),
            )
            .values(accepted_at=_utc_now(), accepted_user_id=accepted_user_id)
        )
        await self._session.flush()
        rowcount = result.rowcount if isinstance(result, CursorResult) else 0
        return bool(rowcount)
