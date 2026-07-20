from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.core.authorization import UNRESTRICTED_PLANT_SCOPE, PlantScope
from mplacas.core.security import OperationsPrincipal, OperationsRole
from mplacas.credentials.db_models import ApiCredentialRecord, OperationalUserRecord

_SECRET_BYTES = 32


class CredentialError(ValueError):
    """Erro de domínio nas operações de credenciais."""


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_secret() -> str:
    return secrets.token_urlsafe(_SECRET_BYTES)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, name: str) -> OperationalUserRecord:
        normalized_name = name.strip()
        if not normalized_name:
            raise CredentialError("user name is required")
        existing = await self._session.scalar(
            select(OperationalUserRecord).where(
                OperationalUserRecord.name == normalized_name
            )
        )
        if existing is not None:
            raise CredentialError("user name is already in use")
        record = OperationalUserRecord(name=normalized_name, active=True)
        self._session.add(record)
        await self._session.flush()
        return record

    async def deactivate(self, user_id: uuid.UUID) -> OperationalUserRecord:
        """Desativa o usuário; todas as suas credenciais param de autenticar."""
        record = await self._session.get(OperationalUserRecord, user_id)
        if record is None:
            raise CredentialError("operational user not found")
        if record.active:
            record.active = False
            record.deactivated_at = datetime.now(timezone.utc)
            await self._session.flush()
        return record

    async def list_users(self) -> list[OperationalUserRecord]:
        result = await self._session.scalars(
            select(OperationalUserRecord).order_by(OperationalUserRecord.created_at)
        )
        return list(result)


class CredentialService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        name: str,
        role: OperationsRole,
        plant_ids: frozenset[uuid.UUID] | None = None,
        user_id: uuid.UUID | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[ApiCredentialRecord, str]:
        """Cria uma credencial e devolve o segredo em texto claro uma única vez."""
        normalized_name = name.strip()
        if not normalized_name:
            raise CredentialError("credential name is required")
        if plant_ids is not None and not plant_ids:
            raise CredentialError("a restricted credential must contain at least one plant")
        if plant_ids is not None and role is OperationsRole.ADMIN:
            raise CredentialError("admin credentials cannot be plant-restricted")
        if expires_at is not None:
            expires_at = _as_utc(expires_at)
            if expires_at <= datetime.now(timezone.utc):
                raise CredentialError("credential expiration must be in the future")
        if user_id is not None:
            user = await self._session.get(OperationalUserRecord, user_id)
            if user is None:
                raise CredentialError("operational user not found")
            if not user.active:
                raise CredentialError("operational user is deactivated")
        existing = await self._session.scalar(
            select(ApiCredentialRecord).where(ApiCredentialRecord.name == normalized_name)
        )
        if existing is not None:
            raise CredentialError("credential name is already in use")

        secret = generate_secret()
        record = ApiCredentialRecord(
            name=normalized_name,
            role=role.value,
            key_hash=hash_secret(secret),
            plant_ids=(
                sorted(str(plant_id) for plant_id in plant_ids)
                if plant_ids is not None
                else None
            ),
            active=True,
            user_id=user_id,
            expires_at=expires_at,
        )
        self._session.add(record)
        await self._session.flush()
        return record, secret

    async def revoke(self, credential_id: uuid.UUID) -> ApiCredentialRecord:
        record = await self._session.get(ApiCredentialRecord, credential_id)
        if record is None:
            raise CredentialError("credential not found")
        if record.active:
            record.active = False
            record.revoked_at = datetime.now(timezone.utc)
            await self._session.flush()
        return record

    async def list_credentials(self) -> list[ApiCredentialRecord]:
        result = await self._session.scalars(
            select(ApiCredentialRecord).order_by(ApiCredentialRecord.created_at)
        )
        return list(result)

    async def resolve(self, secret: str) -> OperationsPrincipal | None:
        """Resolve um segredo apresentado em um principal, ou ``None``.

        Somente credenciais ativas autenticam. O segredo nunca é registrado;
        a busca ocorre exclusivamente pelo hash.
        """
        if not secret:
            return None
        record = await self._session.scalar(
            select(ApiCredentialRecord).where(
                ApiCredentialRecord.key_hash == hash_secret(secret),
                ApiCredentialRecord.active.is_(True),
            )
        )
        if record is None:
            return None
        if record.expires_at is not None and _as_utc(record.expires_at) <= datetime.now(
            timezone.utc
        ):
            return None
        if record.user is not None and not record.user.active:
            return None
        scope = (
            PlantScope.restricted(uuid.UUID(item) for item in record.plant_ids)
            if record.plant_ids is not None
            else UNRESTRICTED_PLANT_SCOPE
        )
        return OperationsPrincipal(
            role=OperationsRole(record.role),
            credential_id=f"credential:{record.id}",
            plant_scope=scope,
        )
