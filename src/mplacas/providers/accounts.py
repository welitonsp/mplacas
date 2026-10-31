"""Conexões das usinas com as contas dos fabricantes de inversor (ADR-091).

O serviço é o único lugar que cifra ou decifra a credencial do fabricante.
Nada aqui registra login, senha ou texto cifrado em log, exceção ou ``repr``.
A verificação na conta do fabricante (entrar e listar inversores antes de
salvar) fica com a rota de ADMIN (fase 5); este módulo só guarda e devolve.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.core.secret_box import SealedSecret, SecretBox, SecretBoxError
from mplacas.db.models import Plant
from mplacas.providers.db_models import ProviderAccountRecord

NEPVIEWER = "NEPVIEWER"
GROWATT = "GROWATT"
SUPPORTED_PROVIDERS = frozenset({NEPVIEWER, GROWATT})
_MAX_LOGIN = 254
_MAX_PASSWORD = 256
_MAX_FAILURE_CODE = 80


class ProviderAccountError(ValueError):
    """Erro de domínio. Mensagens nunca contêm login ou senha."""


class ProviderAccountConflictError(ProviderAccountError):
    """A mesma conta do fabricante já está ligada a outra usina."""


class ProviderAccountNotFoundError(ProviderAccountError):
    """Usina sem conexão ativa (ou usina inexistente)."""


@dataclass(frozen=True, slots=True)
class ProviderLogin:
    """Login e senha em texto claro, só em memória e pelo menor tempo possível."""

    login: str
    password: str = field(repr=False)

    def __repr__(self) -> str:
        return f"ProviderLogin(login={mask_login(self.login)!r}, password=<hidden>)"


def normalize_login(login: str) -> str:
    return login.strip()


def mask_login(login: str) -> str:
    """``cliente@example.com`` → ``cl***@example.com``; ``usuario123`` → ``us***23``."""
    value = normalize_login(login)
    if not value:
        return "***"
    local, at, domain = value.partition("@")
    if at:
        return f"{local[:2]}***@{domain}"
    if len(value) <= 4:
        return f"{value[:1]}***"
    return f"{value[:2]}***{value[-2:]}"


def secret_context(plant_id: uuid.UUID, provider: str) -> str:
    return f"provider_account:{plant_id}:{provider}"


def _fingerprint_value(login: str) -> str:
    return normalize_login(login).casefold()


def _fingerprint(box: SecretBox, provider: str, login: str) -> str:
    return box.fingerprint(_fingerprint_value(login), purpose=provider)


def _validate(provider: str, credentials: ProviderLogin) -> None:
    if provider not in SUPPORTED_PROVIDERS:
        raise ProviderAccountError("unsupported provider")
    login = normalize_login(credentials.login)
    if not login or len(login) > _MAX_LOGIN:
        raise ProviderAccountError("provider login is required")
    if not credentials.password or len(credentials.password) > _MAX_PASSWORD:
        raise ProviderAccountError("provider password is required")


def _seal(
    box: SecretBox, plant_id: uuid.UUID, provider: str, credentials: ProviderLogin
) -> SealedSecret:
    payload = json.dumps(
        {"login": normalize_login(credentials.login), "password": credentials.password},
        separators=(",", ":"),
    ).encode()
    return box.seal(payload, context=secret_context(plant_id, provider))


class ProviderAccountService:
    def __init__(self, session: AsyncSession, box: SecretBox | None) -> None:
        """``box`` pode faltar só para operações que não cifram (desligar, ler estado)."""
        self._session = session
        self._box_or_none = box

    @property
    def _box(self) -> SecretBox:
        if self._box_or_none is None:
            raise ProviderAccountError("provider secret keys are required for this operation")
        return self._box_or_none

    async def get(
        self, plant_id: uuid.UUID, *, for_update: bool = False
    ) -> ProviderAccountRecord | None:
        statement = select(ProviderAccountRecord).where(ProviderAccountRecord.plant_id == plant_id)
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def list_active(self, *, for_update: bool = False) -> list[ProviderAccountRecord]:
        statement = (
            select(ProviderAccountRecord)
            .join(Plant, Plant.id == ProviderAccountRecord.plant_id)
            .where(ProviderAccountRecord.active.is_(True))
            .order_by(Plant.name, Plant.id)
        )
        if for_update:
            # Trava só as linhas de provider_accounts: a rotação não pode
            # regravar a senha antiga por cima de um save concorrente.
            statement = statement.with_for_update(of=ProviderAccountRecord)
        result = await self._session.scalars(statement)
        return list(result)

    async def save(
        self,
        *,
        plant_id: uuid.UUID,
        provider: str,
        credentials: ProviderLogin,
        now: datetime | None = None,
    ) -> ProviderAccountRecord:
        """Cria ou substitui a conexão da usina. Recusa a conta de outra usina."""
        _validate(provider, credentials)
        plant = await self._session.get(Plant, plant_id)
        if plant is None:
            raise ProviderAccountNotFoundError("plant not found")
        fingerprint = _fingerprint(self._box, provider, credentials.login)
        candidates = self._box.fingerprint_candidates(
            _fingerprint_value(credentials.login), purpose=provider
        )
        owners = set(
            await self._session.scalars(
                select(ProviderAccountRecord.plant_id).where(
                    ProviderAccountRecord.provider == provider,
                    ProviderAccountRecord.account_fingerprint.in_(sorted(candidates)),
                )
            )
        )
        if owners - {plant_id}:
            raise ProviderAccountConflictError(
                "this provider account is already connected to another plant"
            )
        sealed = _seal(self._box, plant_id, provider, credentials)
        current = now or datetime.now(UTC)
        record = await self.get(plant_id, for_update=True)
        if record is None:
            record = ProviderAccountRecord(plant_id=plant_id)
            self._session.add(record)
        else:
            record.rotated_at = current
        record.provider = provider
        record.login_hint = mask_login(credentials.login)
        record.account_fingerprint = fingerprint
        record.ciphertext = sealed.ciphertext
        record.key_version = sealed.key_version
        record.active = True
        record.deactivated_at = None
        record.last_failure_at = None
        record.last_failure_code = None
        await self._flush_or_conflict()
        return record

    async def _flush_or_conflict(self) -> None:
        """Converte a corrida perdida (unique) em erro de domínio, sem parâmetros."""
        try:
            async with self._session.begin_nested():
                await self._session.flush()
        except IntegrityError:
            raise ProviderAccountConflictError(
                "this plant or provider account was connected concurrently"
            ) from None

    async def deactivate(
        self, plant_id: uuid.UUID, *, now: datetime | None = None
    ) -> ProviderAccountRecord:
        """Desliga a conexão e apaga o texto cifrado; o registro fica para histórico."""
        record = await self.get(plant_id, for_update=True)
        if record is None or not record.active:
            raise ProviderAccountNotFoundError("plant has no active provider account")
        record.active = False
        record.ciphertext = None
        record.key_version = None
        record.account_fingerprint = None
        record.deactivated_at = now or datetime.now(UTC)
        await self._session.flush()
        return record

    def open(self, record: ProviderAccountRecord) -> ProviderLogin:
        """Decifra a credencial de uma conexão ativa."""
        if not record.active or record.ciphertext is None or record.key_version is None:
            raise ProviderAccountNotFoundError("plant has no active provider account")
        try:
            raw = self._box.open(
                SealedSecret(record.ciphertext, record.key_version),
                context=secret_context(record.plant_id, record.provider),
            )
            payload = json.loads(raw)
            return ProviderLogin(login=payload["login"], password=payload["password"])
        except (SecretBoxError, ValueError, KeyError, TypeError):
            raise ProviderAccountError("provider account could not be decrypted") from None

    async def record_success(
        self, record: ProviderAccountRecord, *, now: datetime | None = None
    ) -> None:
        record.last_success_at = now or datetime.now(UTC)
        record.last_failure_at = None
        record.last_failure_code = None
        await self._session.flush()

    async def record_failure(
        self, record: ProviderAccountRecord, *, code: str, now: datetime | None = None
    ) -> None:
        """``code`` é o nome da classe do erro, nunca a mensagem do fabricante."""
        record.last_failure_at = now or datetime.now(UTC)
        record.last_failure_code = code[:_MAX_FAILURE_CODE]
        await self._session.flush()

    async def rotate_all(self, *, now: datetime | None = None) -> int:
        """Recifra com a chave atual e recalcula as impressões. Devolve quantas mudaram."""
        current = now or datetime.now(UTC)
        changed = 0
        for record in await self.list_active(for_update=True):
            try:
                credentials = self.open(record)
            except ProviderAccountError:
                # plant_id não é segredo e diz ao operador qual usina refazer.
                raise ProviderAccountError(
                    f"provider account of plant {record.plant_id} could not be decrypted"
                ) from None
            fingerprint = _fingerprint(self._box, record.provider, credentials.login)
            if (
                record.key_version == self._box.current_version
                and record.account_fingerprint == fingerprint
            ):
                continue
            sealed = _seal(self._box, record.plant_id, record.provider, credentials)
            record.ciphertext = sealed.ciphertext
            record.key_version = sealed.key_version
            record.account_fingerprint = fingerprint
            record.rotated_at = current
            changed += 1
        await self._flush_or_conflict()
        return changed
