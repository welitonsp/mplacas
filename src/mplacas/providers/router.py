"""Conexão da usina com o fabricante do inversor, pela API (ADR-091, fase 5).

- ``GET`` mostra só o estado (nunca login completo nem senha) a quem lê a usina.
- ``PUT`` (ADMIN da organização) confere a conta no fabricante antes de
  guardar: senha errada nunca é salva. A senha só entra; nunca volta.
- ``DELETE`` (ADMIN) desliga e apaga o texto cifrado.
- ``POST /plants/connect`` (ADMIN, organização ainda sem usina): primeira
  conexão do cliente — confere a conta, **cria a usina** e a preenche com o
  que a marca informa (ADR-093 § 7).

Ao conectar, campos vazios da usina são preenchidos com o cadastro da marca
(``plants.autofill``); o que o dono informou nunca é sobrescrito.

Usina de outra organização responde 404 (convenção de ``core.tenancy``).
Nenhuma resposta, log ou evento de auditoria contém login ou senha.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select

from mplacas.audit.db_models import AuditEventRecord
from mplacas.audit.repository import AuditEventRepository
from mplacas.core.secret_box import SecretBox, SecretBoxError, secret_box_from_settings
from mplacas.core.principal import OperationsPrincipal
from mplacas.core.tenancy import AdminPlantPath, AdminPrincipal, ReadPlantPath
from mplacas.db.models import Device, Plant
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_platform_context, set_principal_context
from mplacas.providers.accounts import (
    NEPVIEWER,
    ProviderAccountConflictError,
    ProviderAccountError,
    ProviderAccountNotFoundError,
    ProviderAccountService,
    ProviderLogin,
    SUPPORTED_PROVIDERS,
)
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.plants.autofill import fill_plant_from_profile, locate_profile
from mplacas.providers.base import (
    PlantProfile,
    ProviderError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from mplacas.providers.db_models import ProviderAccountRecord
from mplacas.providers.factory import build_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plants", tags=["plants"])

_MAX_LOGIN = 254
_MAX_PASSWORD = 256

ConnectionStatus = Literal["SEM_CONEXAO", "CONECTADA", "FALHA"]


# O corpo do PUT é lido à mão, não por um modelo pydantic: o 422 padrão do
# FastAPI repete o valor recebido (``input``) em erros de tipo, campo faltando
# ou campo a mais — e um ``passwd`` digitado errado devolveria a senha.
_MAX_BODY_BYTES = 4096
_SUPPORTED = SUPPORTED_PROVIDERS
# Teto de conferências de login por usina (sucesso ou recusa), para a rota não
# virar um testador de senhas da NEPViewer.
VERIFY_LIMIT = 5
VERIFY_WINDOW = timedelta(minutes=10)
_VERIFY_ACTIONS = (
    "provider_account.saved",
    "provider_account.verify_failed",
    "plant.created_from_connection",
)


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


@dataclass(frozen=True, slots=True)
class ProviderInspection:
    """O que a conferência da conta trouxe: aparelhos e o cadastro da usina."""

    serials: list[str]
    profile: PlantProfile | None = field(default=None)


Verifier = Callable[[str, ProviderLogin], Awaitable[ProviderInspection]]


async def verify_with_provider(provider: str, credentials: ProviderLogin) -> ProviderInspection:
    """Entra na conta da marca, lista os aparelhos e lê o cadastro da usina.

    Uma sessão só (um login, sem retry): a Growatt bloqueia por excesso de
    logins. NEPViewer devolve números de série de inversores; Growatt, as
    usinas da conta (``GW-PLANT-<id>``, ADR-092). O cadastro é melhor esforço:
    se falhar, a conexão segue sem ele.
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise ProviderAccountError("unsupported provider")
    client = build_client(provider, account=credentials.login, password=credentials.password)
    try:
        devices = await client.list_devices()
        try:
            profile = await client.plant_profile()
        except Exception as exc:  # noqa: BLE001 — cadastro é bônus; nunca derruba a conexão
            logger.info(
                "provider_plant_profile_unavailable",
                extra={"provider": provider, "error_code": type(exc).__name__},
            )
            profile = None
    finally:
        await client.aclose()
    return ProviderInspection([device.serial_number for device in devices], profile)


# Ponto de troca para testes: nunca chama o fabricante real fora de produção.
verify_provider_account: Verifier = verify_with_provider


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

    async def refuse(reason: str) -> None:
        await _audit_refusal(request, scoped.principal, "plant", scoped.plant_id, provider, reason)

    inspection = await _inspect(provider, credentials, refuse)
    serials = inspection.serials

    if await _inverter_in_another_plant(provider, serials, scoped.plant_id):
        await refuse("provider_inverter_in_another_plant")
        raise _error(status.HTTP_409_CONFLICT, "provider_inverter_in_another_plant")
    profile = await locate_profile(inspection.profile)  # rede fora da transação

    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        service = ProviderAccountService(session, box)
        try:
            record = await service.save(
                plant_id=scoped.plant_id, provider=provider, credentials=credentials
            )
        except ProviderAccountConflictError:
            await session.rollback()
            await refuse("provider_account_in_use")
            raise _error(status.HTTP_409_CONFLICT, "provider_account_in_use") from None
        except ProviderAccountNotFoundError:
            raise _error(status.HTTP_404_NOT_FOUND, "plant not found") from None
        except ProviderAccountError:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_account_invalid"
            ) from None
        await service.record_success(record)
        plant = await session.get(Plant, scoped.plant_id)
        filled = fill_plant_from_profile(plant, profile) if plant is not None else {}
        await AuditEventRepository(session).record(
            request,
            action="provider_account.saved",
            resource_type="plant",
            resource_id=str(scoped.plant_id),
            outcome="SUCCEEDED",
            details={
                "provider": record.provider,
                "devices_found": len(serials),
                "auto_filled": sorted(filled),
            },
        )
        view = _view(record, devices_found=len(serials))
        await session.commit()
    logger.info(
        "provider_account_saved",
        extra={"plant_id": str(scoped.plant_id), "devices_found": len(serials)},
    )
    return view


class FirstConnectionResult(BaseModel):
    plant_id: uuid.UUID
    plant_name: str
    connection: ProviderAccountView
    # campo → "BRAND" (veio da marca) ou "ESTIMATE" (estimado); a tela pede conferência
    auto_filled: dict[str, str]


DEFAULT_PLANT_NAME = "Minha usina"


@router.post(
    "/connect",
    response_model=FirstConnectionResult,
    status_code=status.HTTP_201_CREATED,
)
async def connect_first_plant(
    request: Request, principal: AdminPrincipal
) -> FirstConnectionResult:
    """Primeira conexão do cliente: a usina nasce da conta da marca (ADR-093 § 7).

    Só para organização que ainda não tem usina — depois disso, a conexão é
    trocada pela rota da própria usina. O teto de conferências conta por
    organização, como o da usina conta por usina.
    """
    organization_id = principal.organization_id
    if organization_id is None:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "organization_required")
    # Escopo de usina não se aplica aqui: todo principal de organização carrega
    # o escopo "usinas da organização", que é vazio enquanto ela não tem usina —
    # e a rota só roda nesse caso, então não há usina fora do escopo a proteger.
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > _MAX_BODY_BYTES:
        raise _error(status.HTTP_413_CONTENT_TOO_LARGE, "provider_account_body_too_large")
    provider, credentials = _parse_body(await request.body())
    box = _box()
    if await _organization_has_plant(principal):
        raise _error(status.HTTP_409_CONFLICT, "plant_already_exists")
    await _enforce_verify_limit(organization_id, resource_type="organization")

    async def refuse(reason: str) -> None:
        await _audit_refusal(
            request, principal, "organization", organization_id, provider, reason
        )

    inspection = await _inspect(provider, credentials, refuse)
    if await _inverter_in_another_plant(provider, inspection.serials, None):
        await refuse("provider_inverter_in_another_plant")
        raise _error(status.HTTP_409_CONFLICT, "provider_inverter_in_another_plant")
    profile = await locate_profile(inspection.profile)  # rede antes de travar a organização

    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        organization = await session.get(
            OrganizationRecord, organization_id, with_for_update=True
        )
        if organization is None:
            raise _error(status.HTTP_404_NOT_FOUND, "organization_not_found")
        # rechecagem com a organização travada: dois cliques não criam duas usinas
        if await session.scalar(
            select(Plant.id).where(Plant.organization_id == organization_id).limit(1)
        ):
            raise _error(status.HTTP_409_CONFLICT, "plant_already_exists")
        plant = Plant(organization_id=organization_id, name=DEFAULT_PLANT_NAME)
        session.add(plant)
        await session.flush()
        filled = fill_plant_from_profile(plant, profile, set_name=True)
        if organization.default_plant_id is None:
            organization.default_plant_id = plant.id
        service = ProviderAccountService(session, box)
        try:
            record = await service.save(
                plant_id=plant.id, provider=provider, credentials=credentials
            )
        except ProviderAccountConflictError:
            await session.rollback()
            await refuse("provider_account_in_use")
            raise _error(status.HTTP_409_CONFLICT, "provider_account_in_use") from None
        except ProviderAccountError:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_account_invalid"
            ) from None
        await service.record_success(record)
        audit = AuditEventRepository(session)
        await audit.record(
            request,
            action="plant.created_from_connection",
            resource_type="organization",
            resource_id=str(organization_id),
            outcome="SUCCEEDED",
            details={
                "plant_id": str(plant.id),
                "provider": provider,
                "auto_filled": sorted(filled),
            },
        )
        await audit.record(
            request,
            action="provider_account.saved",
            resource_type="plant",
            resource_id=str(plant.id),
            outcome="SUCCEEDED",
            details={"provider": provider, "devices_found": len(inspection.serials)},
        )
        result = FirstConnectionResult(
            plant_id=plant.id,
            plant_name=plant.name,
            connection=_view(record, devices_found=len(inspection.serials)),
            auto_filled=dict(plant.auto_filled or {}),
        )
        await session.commit()
    logger.info(
        "plant_created_from_connection",
        extra={"plant_id": str(result.plant_id), "auto_filled": sorted(result.auto_filled)},
    )
    return result


async def _organization_has_plant(principal: OperationsPrincipal) -> bool:
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        found = await session.scalar(
            select(Plant.id).where(Plant.organization_id == principal.organization_id).limit(1)
        )
    return found is not None


async def _inspect(
    provider: str,
    credentials: ProviderLogin,
    refuse: Callable[[str], Awaitable[None]],
) -> ProviderInspection:
    try:
        return await verify_provider_account(provider, credentials)
    except ProviderRateLimitedError:
        # A marca bloqueou por excesso de logins (Growatt 507): esperar, não insistir.
        await refuse("provider_rate_limited")
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_rate_limited") from None
    except ProviderUnavailableError:
        await refuse("provider_unavailable")
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_unavailable") from None
    except ProviderError:
        # Senha errada volta como envelope de erro (não 401), na NEPViewer e na Growatt;
        # auth e formato inesperado viram o mesmo "login recusado", sem
        # repetir a mensagem do fabricante.
        await refuse("provider_login_failed")
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_login_failed") from None


async def _enforce_verify_limit(
    plant_id: uuid.UUID, *, resource_type: str = "plant"
) -> None:
    since = datetime.now(UTC) - VERIFY_WINDOW
    async with SessionFactory() as session:
        await set_platform_context(session)
        attempts = await session.scalar(
            select(func.count())
            .select_from(AuditEventRecord)
            .where(
                AuditEventRecord.action.in_(_VERIFY_ACTIONS),
                AuditEventRecord.resource_type == resource_type,
                AuditEventRecord.resource_id == str(plant_id),
                AuditEventRecord.created_at >= since,
            )
        )
    if (attempts or 0) >= VERIFY_LIMIT:
        raise _error(status.HTTP_429_TOO_MANY_REQUESTS, "provider_verify_rate_limited")


async def _inverter_in_another_plant(
    provider: str, serials: list[str], plant_id: uuid.UUID | None
) -> bool:
    """Confere em todas as organizações (contexto de plataforma), não só na do
    chamador: o RLS de ``devices`` esconderia o inversor de outro cliente. Só
    devolve sim/não; nada do outro cliente sai daqui."""
    if not serials:
        return False
    async with SessionFactory() as session:
        await set_platform_context(session)
        query = select(Device.id).where(
            Device.provider == provider, Device.serial_number.in_(serials)
        )
        if plant_id is not None:
            query = query.where(Device.plant_id != plant_id)
        taken = await session.scalar(query.limit(1))
    return taken is not None


async def _audit_refusal(
    request: Request,
    principal: OperationsPrincipal,
    resource_type: str,
    resource_id: uuid.UUID,
    provider: str,
    reason: str,
) -> None:
    """Recusa também vai para a auditoria (sem login nem senha) e conta no teto."""
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        await AuditEventRepository(session).record(
            request,
            action="provider_account.verify_failed",
            resource_type=resource_type,
            resource_id=str(resource_id),
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
