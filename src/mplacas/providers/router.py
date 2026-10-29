"""Conexão da usina com o fabricante do inversor, pela API (ADR-091, fase 5).

- ``GET`` mostra só o estado (nunca login completo nem senha) a quem lê a usina.
- ``PUT`` (ADMIN da organização) confere a conta no fabricante antes de
  guardar: senha errada nunca é salva. A senha só entra; nunca volta.
- ``DELETE`` (ADMIN) desliga e apaga o texto cifrado.

Usina de outra organização responde 404 (convenção de ``core.tenancy``).
Nenhuma resposta, log ou evento de auditoria contém login ou senha.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select

from mplacas.audit.db_models import AuditEventRecord
from mplacas.audit.repository import AuditEventRepository
from mplacas.core.config import get_settings
from mplacas.core.secret_box import SecretBox, SecretBoxError, secret_box_from_settings
from mplacas.core.tenancy import AdminPlantPath, ReadPlantPath, ScopedPlant
from mplacas.db.models import Device
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_platform_context, set_principal_context
from mplacas.providers.accounts import (
    NEPVIEWER,
    ProviderAccountConflictError,
    ProviderAccountError,
    ProviderAccountNotFoundError,
    ProviderAccountService,
    ProviderLogin,
)
from mplacas.providers.base import ProviderError, ProviderUnavailableError
from mplacas.providers.db_models import ProviderAccountRecord
from mplacas.providers.nepviewer.client import NepViewerClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plants", tags=["plants"])

_MAX_LOGIN = 254
_MAX_PASSWORD = 256

ConnectionStatus = Literal["SEM_CONEXAO", "CONECTADA", "FALHA"]


# O corpo do PUT é lido à mão, não por um modelo pydantic: o 422 padrão do
# FastAPI repete o valor recebido (``input``) em erros de tipo, campo faltando
# ou campo a mais — e um ``passwd`` digitado errado devolveria a senha.
_MAX_BODY_BYTES = 4096
_SUPPORTED = frozenset({NEPVIEWER})
# Teto de conferências de login por usina (sucesso ou recusa), para a rota não
# virar um testador de senhas da NEPViewer.
VERIFY_LIMIT = 5
VERIFY_WINDOW = timedelta(minutes=10)
_VERIFY_ACTIONS = ("provider_account.saved", "provider_account.verify_failed")


def _parse_body(raw: bytes) -> tuple[str, ProviderLogin]:
    if len(raw) > _MAX_BODY_BYTES:
        raise _error(status.HTTP_413_CONTENT_TOO_LARGE, "provider_account_body_too_large")
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_account_invalid") from None
    if not isinstance(body, dict) or set(body) - {"provider", "login", "password"}:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_account_invalid")
    provider = body.get("provider", NEPVIEWER)
    if provider not in _SUPPORTED:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_unsupported")
    login = body.get("login")
    password = body.get("password")
    if not isinstance(login, str) or not login.strip() or len(login.strip()) > _MAX_LOGIN:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_login_invalid")
    if not isinstance(password, str) or not password or len(password) > _MAX_PASSWORD:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_password_invalid")
    return provider, ProviderLogin(login=login.strip(), password=password)


class ProviderAccountView(BaseModel):
    status: ConnectionStatus
    provider: str | None = None
    login_hint: str | None = None
    connected_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    devices_found: int | None = None


Verifier = Callable[[str, ProviderLogin], Awaitable[list[str]]]


async def verify_nepviewer(provider: str, credentials: ProviderLogin) -> list[str]:
    """Entra na conta e lista os números de série dos inversores (uma tentativa)."""
    if provider != NEPVIEWER:
        raise ProviderAccountError("unsupported provider")
    settings = get_settings()
    async with NepViewerClient(
        account=credentials.login,
        password=credentials.password,
        base_url=str(settings.nep_base_url),
        timeout_seconds=settings.request_timeout_seconds,
    ) as client:
        devices = await client.list_devices()
    return [device.serial_number for device in devices]


# Ponto de troca para testes: nunca chama a NEPViewer real fora de produção.
verify_provider_account: Verifier = verify_nepviewer


def _view(
    record: ProviderAccountRecord | None, *, devices_found: int | None = None
) -> ProviderAccountView:
    if record is None or not record.active:
        return ProviderAccountView(status="SEM_CONEXAO")
    failing = record.last_failure_at is not None and (
        record.last_success_at is None or record.last_failure_at > record.last_success_at
    )
    return ProviderAccountView(
        status="FALHA" if failing else "CONECTADA",
        provider=record.provider,
        login_hint=record.login_hint,
        connected_at=record.rotated_at or record.created_at,
        last_success_at=record.last_success_at,
        last_failure_at=record.last_failure_at,
        devices_found=devices_found,
    )


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _box() -> SecretBox:
    try:
        return secret_box_from_settings()
    except SecretBoxError:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "provider_secret_keys_not_configured"
        ) from None


@router.get("/{plant_id}/provider-account", response_model=ProviderAccountView)
async def get_provider_account(scoped: ReadPlantPath) -> ProviderAccountView:
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        record = await session.scalar(
            select(ProviderAccountRecord).where(ProviderAccountRecord.plant_id == scoped.plant_id)
        )
        return _view(record)


@router.put("/{plant_id}/provider-account", response_model=ProviderAccountView)
async def put_provider_account(request: Request, scoped: AdminPlantPath) -> ProviderAccountView:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > _MAX_BODY_BYTES:
        # Recusa antes de ler: o corpo grande nem chega à memória.
        raise _error(status.HTTP_413_CONTENT_TOO_LARGE, "provider_account_body_too_large")
    provider, credentials = _parse_body(await request.body())
    box = _box()
    await _enforce_verify_limit(scoped.plant_id)

    try:
        serials = await verify_provider_account(provider, credentials)
    except ProviderUnavailableError:
        await _audit_refusal(request, scoped, provider, "provider_unavailable")
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_unavailable") from None
    except ProviderError:
        # Senha errada na NEPViewer volta como envelope de erro (não 401);
        # auth e formato inesperado viram o mesmo "login recusado", sem
        # repetir a mensagem do fabricante.
        await _audit_refusal(request, scoped, provider, "provider_login_failed")
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_login_failed") from None

    if await _inverter_in_another_plant(provider, serials, scoped.plant_id):
        await _audit_refusal(request, scoped, provider, "provider_inverter_in_another_plant")
        raise _error(status.HTTP_409_CONFLICT, "provider_inverter_in_another_plant")

    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        service = ProviderAccountService(session, box)
        try:
            record = await service.save(
                plant_id=scoped.plant_id, provider=provider, credentials=credentials
            )
        except ProviderAccountConflictError:
            await session.rollback()
            await _audit_refusal(request, scoped, provider, "provider_account_in_use")
            raise _error(status.HTTP_409_CONFLICT, "provider_account_in_use") from None
        except ProviderAccountNotFoundError:
            raise _error(status.HTTP_404_NOT_FOUND, "plant not found") from None
        except ProviderAccountError:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_account_invalid"
            ) from None
        await service.record_success(record)
        await AuditEventRepository(session).record(
            request,
            action="provider_account.saved",
            resource_type="plant",
            resource_id=str(scoped.plant_id),
            outcome="SUCCEEDED",
            details={"provider": record.provider, "devices_found": len(serials)},
        )
        view = _view(record, devices_found=len(serials))
        await session.commit()
    logger.info(
        "provider_account_saved",
        extra={"plant_id": str(scoped.plant_id), "devices_found": len(serials)},
    )
    return view


async def _enforce_verify_limit(plant_id: uuid.UUID) -> None:
    since = datetime.now(UTC) - VERIFY_WINDOW
    async with SessionFactory() as session:
        await set_platform_context(session)
        attempts = await session.scalar(
            select(func.count())
            .select_from(AuditEventRecord)
            .where(
                AuditEventRecord.action.in_(_VERIFY_ACTIONS),
                AuditEventRecord.resource_type == "plant",
                AuditEventRecord.resource_id == str(plant_id),
                AuditEventRecord.created_at >= since,
            )
        )
    if (attempts or 0) >= VERIFY_LIMIT:
        raise _error(status.HTTP_429_TOO_MANY_REQUESTS, "provider_verify_rate_limited")


async def _inverter_in_another_plant(
    provider: str, serials: list[str], plant_id: uuid.UUID
) -> bool:
    """Confere em todas as organizações (contexto de plataforma), não só na do
    chamador: o RLS de ``devices`` esconderia o inversor de outro cliente. Só
    devolve sim/não; nada do outro cliente sai daqui."""
    if not serials:
        return False
    async with SessionFactory() as session:
        await set_platform_context(session)
        taken = await session.scalar(
            select(Device.id)
            .where(
                Device.provider == provider,
                Device.serial_number.in_(serials),
                Device.plant_id != plant_id,
            )
            .limit(1)
        )
    return taken is not None


async def _audit_refusal(request: Request, scoped: ScopedPlant, provider: str, reason: str) -> None:
    """Recusa também vai para a auditoria (sem login nem senha) e conta no teto."""
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        await AuditEventRepository(session).record(
            request,
            action="provider_account.verify_failed",
            resource_type="plant",
            resource_id=str(scoped.plant_id),
            outcome="FAILED",
            details={"provider": provider, "reason": reason},
        )
        await session.commit()


@router.delete(
    "/{plant_id}/provider-account",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_provider_account(request: Request, scoped: AdminPlantPath) -> Response:
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        try:
            # Desligar não cifra nem decifra: funciona mesmo sem a chave.
            await ProviderAccountService(session, None).deactivate(scoped.plant_id)
        except ProviderAccountNotFoundError:
            raise _error(status.HTTP_404_NOT_FOUND, "provider_account_not_found") from None
        await AuditEventRepository(session).record(
            request,
            action="provider_account.removed",
            resource_type="plant",
            resource_id=str(scoped.plant_id),
            outcome="SUCCEEDED",
        )
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
