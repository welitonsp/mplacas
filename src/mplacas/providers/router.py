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

import enum
import json
import re
import secrets
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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
    GROWATT,
    GROWATT_TOKEN,
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
from mplacas.plants.schemas import ModuleTechnology
from mplacas.providers.connect_ticket import ConnectTicketError, issue_ticket, open_ticket
from mplacas.providers.base import (
    PlantProfile,
    ProviderAuthError,
    ProviderBlockedError,
    ProviderError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from mplacas.providers.db_models import ProviderAccountRecord
from mplacas.core.config import get_settings
from mplacas.providers.factory import ENERGY_SOURCES, build_client
from mplacas.providers.growatt.openapi import GrowattOpenApiClient
from mplacas.services.collection import CollectionPlantError, SolarCollectionService

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
    "plant.connect_previewed",
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
    if provider == GROWATT_TOKEN:
        # Só o token (no campo da senha). O login é derivado depois da
        # conferência (``_token_login``), nunca vem do token.
        token = password.strip() if isinstance(password, str) else ""
        # Token da OpenAPI: ASCII visível, sem espaço interno nem quebra de linha
        # (um caractere estranho viraria erro de codificação no cabeçalho).
        if not token or len(token) > _MAX_PASSWORD or not _TOKEN_CHARS.fullmatch(token):
            raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_token_invalid")
        return provider, ProviderLogin(login=TOKEN_LOGIN_PENDING, password=token)
    if not isinstance(login, str) or not login.strip() or len(login.strip()) > _MAX_LOGIN:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_login_invalid")
    if not isinstance(password, str) or not password or len(password) > _MAX_PASSWORD:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_password_invalid")
    return provider, ProviderLogin(login=login.strip(), password=password)


TOKEN_LOGIN_PENDING = "growatt-token"
_TOKEN_CHARS = re.compile(r"[!-~]+")


def _token_login(credentials: ProviderLogin) -> ProviderLogin:
    """Login de uma conexão por token (ADR-094): identificador aleatório, nunca o token.

    O token não passa por hash nenhum (nem para impressão digital). A mesma
    usina Growatt em duas usinas do MPlacas é barrada pelos aparelhos
    ``GW-PLANT-<id>`` (``_inverter_in_another_plant``), que conferem senha e
    token juntos. Na tela aparece mascarado ("to***3f").
    """
    return ProviderLogin(login=f"token-{secrets.token_hex(8)}", password=credentials.password)


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
    if provider == GROWATT_TOKEN:
        credentials = _token_login(credentials)
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
    if provider == GROWATT_TOKEN:
        credentials = _token_login(credentials)
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


# --- Assistente de primeiro acesso (ADR-096): prévia → revisar → salvar ----

_DRAFT_FIELDS = (
    "name",
    "installed_power_kwp",
    "latitude",
    "longitude",
    "array_tilt_degrees",
    "array_azimuth_degrees",
    "module_technology",
)
# Campo do rascunho → chave de ``plants.auto_filled`` (``plants.autofill``).
_ORIGIN_KEYS = {
    "name": "name",
    "installed_power_kwp": "dc_capacity_kwp",
    "latitude": "location",
    "longitude": "location",
    "array_tilt_degrees": "array_tilt_degrees",
    "array_azimuth_degrees": "array_azimuth_degrees",
    "module_technology": "module_technology",
}


class PlantDraft(BaseModel):
    """A usina montada na prévia, ainda não salva. Valores como texto."""

    name: str
    installed_power_kwp: str | None
    latitude: str | None
    longitude: str | None
    city: str | None
    array_tilt_degrees: str | None
    array_azimuth_degrees: str | None
    module_technology: str | None


class ConnectPreview(BaseModel):
    provider: str
    devices_found: int
    plant: PlantDraft
    # campo → "BRAND" (veio da marca) | "ESTIMATE" (estimado)
    origins: dict[str, str]
    ticket: str
    expires_at: datetime


class PlantConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def _location_pair(self) -> PlantConfirmation:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude go together")
        return self
    installed_power_kwp: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, max_digits=9, decimal_places=6)
    longitude: Decimal | None = Field(
        default=None, ge=-180, le=180, max_digits=9, decimal_places=6
    )
    array_tilt_degrees: Decimal | None = Field(
        default=None, ge=0, le=90, max_digits=5, decimal_places=2
    )
    array_azimuth_degrees: Decimal | None = Field(
        default=None, ge=0, lt=360, max_digits=5, decimal_places=2
    )
    module_technology: ModuleTechnology | None = None


class ConnectConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Sem limites aqui de propósito: erro de validação do pydantic repete o
    # valor recebido; tamanho e formato do bilhete são conferidos em open_ticket.
    ticket: str
    plant: PlantConfirmation


def _text(value: object, places: str | None = None) -> str | None:
    """Rascunho como texto, já no formato que a confirmação aceita (casas)."""
    if value is None:
        return None
    if places is not None and isinstance(value, Decimal):
        return str(value.quantize(Decimal(places)))
    return str(value)


@router.post("/connect/preview", response_model=ConnectPreview)
async def preview_first_plant(
    request: Request, response: Response, principal: AdminPrincipal
) -> ConnectPreview:
    """Passo 2 do assistente: confere a conta, lê a usina na marca e monta o
    rascunho — sem salvar nada. Devolve o bilhete cifrado para o passo 3."""
    response.headers["Cache-Control"] = "no-store"
    organization_id = principal.organization_id
    if organization_id is None:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "organization_required")
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > _MAX_BODY_BYTES:
        raise _error(status.HTTP_413_CONTENT_TOO_LARGE, "provider_account_body_too_large")
    provider, credentials = _parse_body(await request.body())
    box = _box()
    if await _organization_has_plant(principal):
        raise _error(status.HTTP_409_CONFLICT, "plant_already_exists")
    await _enforce_verify_limit(organization_id, resource_type="organization")

    async def refuse(reason: str) -> None:
        await _audit_refusal(request, principal, "organization", organization_id, provider, reason)

    inspection = await _inspect(provider, credentials, refuse)
    if provider == GROWATT_TOKEN:
        credentials = _token_login(credentials)
    if await _inverter_in_another_plant(provider, inspection.serials, None):
        await refuse("provider_inverter_in_another_plant")
        raise _error(status.HTTP_409_CONFLICT, "provider_inverter_in_another_plant")
    profile = await locate_profile(inspection.profile)

    # Rascunho numa usina que nunca vai para o banco (só para aplicar as regras).
    draft_plant = Plant(organization_id=organization_id, name=DEFAULT_PLANT_NAME)
    filled = fill_plant_from_profile(draft_plant, profile, set_name=True)
    draft = PlantDraft(
        name=(draft_plant.name or DEFAULT_PLANT_NAME)[:120],
        installed_power_kwp=_text(draft_plant.installed_power_kwp, "0.001"),
        latitude=_text(draft_plant.latitude, "0.000001"),
        longitude=_text(draft_plant.longitude, "0.000001"),
        city=profile.city if profile else None,
        array_tilt_degrees=_text(draft_plant.array_tilt_degrees, "0.01"),
        array_azimuth_degrees=_text(draft_plant.array_azimuth_degrees, "0.01"),
        module_technology=draft_plant.module_technology,
    )
    values = {field: getattr(draft, field) for field in _DRAFT_FIELDS}
    try:
        ticket, expires_at = issue_ticket(
            box,
            organization_id=organization_id,
            holder=principal.credential_id,
            provider=provider,
        credentials=credentials,
            serials=inspection.serials,
            draft=values,
            origins=filled,
        )
    except ConnectTicketError:
        # Conta com aparelhos demais para caber no bilhete: falha clara na prévia.
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "provider_account_too_large") from None
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        await AuditEventRepository(session).record(
            request,
            action="plant.connect_previewed",
            resource_type="organization",
            resource_id=str(organization_id),
            outcome="SUCCEEDED",
            details={"provider": provider, "devices_found": len(inspection.serials)},
        )
        await session.commit()
    return ConnectPreview(
        provider=provider,
        devices_found=len(inspection.serials),
        plant=draft,
        origins=filled,
        ticket=ticket,
        expires_at=expires_at,
    )


def _same(value: object, drafted: str | None) -> bool:
    if value is None or drafted is None:
        return value is None and drafted is None
    if isinstance(value, Decimal):
        try:
            return value == Decimal(drafted)
        except ArithmeticError:
            return False
    if isinstance(value, enum.Enum):
        return str(value.value) == drafted
    return str(value) == drafted


@router.post(
    "/connect/confirm",
    response_model=FirstConnectionResult,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_first_plant(
    request: Request, payload: ConnectConfirmation, principal: AdminPrincipal
) -> FirstConnectionResult:
    """Passo 3 do assistente: "Salvar usina" com o que o cliente revisou.

    Abre o bilhete (sem consultar a marca de novo), cria a usina com os valores
    confirmados e guarda a conexão. Campo que o cliente mudou deixa de ser
    "automático"; o que ele manteve guarda a origem (marca ou estimativa).
    """
    organization_id = principal.organization_id
    if organization_id is None:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "organization_required")
    box = _box()

    async def refuse(provider: str, reason: str) -> None:
        await _audit_refusal(request, principal, "organization", organization_id, provider, reason)

    try:
        ticket = open_ticket(
            box, payload.ticket, organization_id=organization_id, holder=principal.credential_id
        )
    except ConnectTicketError:
        # Vencido, adulterado ou de outra pessoa: fica na auditoria (sem o bilhete).
        await refuse("unknown", "connect_ticket_invalid")
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "connect_ticket_invalid") from None
    if await _inverter_in_another_plant(ticket.provider, ticket.serials, None):
        await refuse(ticket.provider, "provider_inverter_in_another_plant")
        raise _error(status.HTTP_409_CONFLICT, "provider_inverter_in_another_plant")
    confirmed = payload.plant
    origins: dict[str, str] = {}
    for field_name in _DRAFT_FIELDS:
        key = _ORIGIN_KEYS[field_name]
        origin = ticket.origins.get(key)
        if origin and _same(getattr(confirmed, field_name), ticket.draft.get(field_name)):
            origins.setdefault(key, origin)
        elif origin:
            origins[key] = ""  # mudado pelo cliente: o valor é dele
    auto_filled = {key: origin for key, origin in origins.items() if origin}

    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        organization = await session.get(
            OrganizationRecord, organization_id, with_for_update=True
        )
        if organization is None:
            raise _error(status.HTTP_404_NOT_FOUND, "organization_not_found")
        if await session.scalar(
            select(Plant.id).where(Plant.organization_id == organization_id).limit(1)
        ):
            raise _error(status.HTTP_409_CONFLICT, "plant_already_exists")
        plant = Plant(
            organization_id=organization_id,
            name=confirmed.name,
            installed_power_kwp=confirmed.installed_power_kwp,
            latitude=confirmed.latitude,
            longitude=confirmed.longitude,
            array_tilt_degrees=confirmed.array_tilt_degrees,
            array_azimuth_degrees=confirmed.array_azimuth_degrees,
            module_technology=(
                confirmed.module_technology.value if confirmed.module_technology else None
            ),
            auto_filled=auto_filled or None,
        )
        session.add(plant)
        await session.flush()
        if organization.default_plant_id is None:
            organization.default_plant_id = plant.id
        service = ProviderAccountService(session, box)
        try:
            record = await service.save(
                plant_id=plant.id, provider=ticket.provider, credentials=ticket.credentials
            )
        except ProviderAccountConflictError:
            await session.rollback()
            await refuse(ticket.provider, "provider_account_in_use")
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
                "provider": ticket.provider,
                "auto_filled": sorted(auto_filled),
                "edited_by_owner": sorted(key for key, origin in origins.items() if not origin),
            },
        )
        await audit.record(
            request,
            action="provider_account.saved",
            resource_type="plant",
            resource_id=str(plant.id),
            outcome="SUCCEEDED",
            details={"provider": ticket.provider, "devices_found": len(ticket.serials)},
        )
        result = FirstConnectionResult(
            plant_id=plant.id,
            plant_name=plant.name,
            connection=_view(record, devices_found=len(ticket.serials)),
            auto_filled=auto_filled,
        )
        await session.commit()
    logger.info(
        "plant_created_from_connection",
        extra={"plant_id": str(result.plant_id), "auto_filled": sorted(auto_filled)},
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
    except ProviderBlockedError:
        # Login recusado antes de olhar a senha (Growatt 403): não é a senha.
        await refuse("provider_login_blocked")
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_login_blocked") from None
    except ProviderUnavailableError:
        await refuse("provider_unavailable")
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_unavailable") from None
    except ProviderError as exc:
        if provider == GROWATT_TOKEN and not isinstance(exc, ProviderAuthError):
            # OpenAPI respondeu fora do formato (ou erro de sistema): não é o
            # token — não mandar o cliente gerar outro à toa.
            await refuse("provider_unavailable")
            raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_unavailable") from None
        # Senha errada volta como envelope de erro (não 401), na NEPViewer e na Growatt;
        # auth e formato inesperado viram o mesmo "login recusado", sem
        # repetir a mensagem do fabricante.
        reason = "provider_token_failed" if provider == GROWATT_TOKEN else "provider_login_failed"
        await refuse(reason)
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, reason) from None


# "Buscar dados na marca" tem teto próprio: cliques no botão não podem
# bloquear a troca de senha nem a conexão (que contam em ``_VERIFY_ACTIONS``).
REFRESH_LIMIT = 3
_REFRESH_ACTIONS = ("provider_account.profile_refreshed",)


async def _enforce_verify_limit(
    plant_id: uuid.UUID,
    *,
    resource_type: str = "plant",
    actions: tuple[str, ...] = _VERIFY_ACTIONS,
    limit: int = VERIFY_LIMIT,
) -> None:
    since = datetime.now(UTC) - VERIFY_WINDOW
    async with SessionFactory() as session:
        await set_platform_context(session)
        attempts = await session.scalar(
            select(func.count())
            .select_from(AuditEventRecord)
            .where(
                AuditEventRecord.action.in_(actions),
                AuditEventRecord.resource_type == resource_type,
                AuditEventRecord.resource_id == str(plant_id),
                AuditEventRecord.created_at >= since,
            )
        )
    if (attempts or 0) >= limit:
        raise _error(status.HTTP_429_TOO_MANY_REQUESTS, "provider_verify_rate_limited")


_GROWATT_FAMILY = {GROWATT, GROWATT_TOKEN}


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
        # As duas formas de conectar a Growatt (senha e token) leem as mesmas
        # usinas (``GW-PLANT-<id>``): conferem juntas.
        family = _GROWATT_FAMILY if provider in _GROWATT_FAMILY else {provider}
        query = select(Device.id).where(
            Device.provider.in_(sorted(family)), Device.serial_number.in_(serials)
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
    *,
    action: str = "provider_account.verify_failed",
) -> None:
    """Recusa também vai para a auditoria (sem login nem senha) e conta no teto."""
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        await AuditEventRepository(session).record(
            request,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            outcome="FAILED",
            details={"provider": provider, "reason": reason},
        )
        await session.commit()


class ProfileRefreshResult(BaseModel):
    # campo → "BRAND" | "ESTIMATE" preenchido agora; vazio = nada novo
    auto_filled: dict[str, str]
    plant_name: str


@router.post("/{plant_id}/provider-account/refresh-profile", response_model=ProfileRefreshResult)
async def refresh_plant_profile(request: Request, scoped: AdminPlantPath) -> ProfileRefreshResult:
    """Relê o cadastro da usina na marca e preenche os campos vazios (ADR-094).

    Usa a conexão já guardada (nada é digitado de novo). Mesmas regras da
    conexão: nunca sobrescreve o que o dono informou; o nome só é trocado se
    ainda for o padrão "Minha usina". Conta no mesmo teto de conferências.
    """
    box = _box()
    await _enforce_verify_limit(scoped.plant_id, actions=_REFRESH_ACTIONS, limit=REFRESH_LIMIT)
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        record = await ProviderAccountService(session, box).get(scoped.plant_id)
        if record is None or not record.active:
            raise _error(status.HTTP_404_NOT_FOUND, "provider_account_not_found")
        provider = record.provider
        try:
            credentials = ProviderAccountService(session, box).open(record)
        except ProviderAccountError:
            # Chave do cofre trocada sem rotação, ou texto cifrado danificado.
            raise _error(
                status.HTTP_503_SERVICE_UNAVAILABLE, "provider_account_unreadable"
            ) from None

    async def refuse(reason: str) -> None:
        await _audit_refusal(request, scoped.principal, "plant", scoped.plant_id, provider, reason)

    client = build_client(provider, account=credentials.login, password=credentials.password)
    try:
        profile = await client.plant_profile()
    except ProviderRateLimitedError:
        await refuse("provider_rate_limited")
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_rate_limited") from None
    except ProviderBlockedError:
        # bloqueio da marca não é senha errada: mesmo código da conexão
        await refuse("provider_login_blocked")
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_login_blocked") from None
    except ProviderAuthError:
        reason = "provider_token_failed" if provider == GROWATT_TOKEN else "provider_login_failed"
        await refuse(reason)
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, reason) from None
    except ProviderError:
        await refuse("provider_unavailable")
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_unavailable") from None
    finally:
        await client.aclose()
    profile = await locate_profile(profile)  # rede fora da transação

    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        plant = await session.get(Plant, scoped.plant_id)
        if plant is None:
            raise _error(status.HTTP_404_NOT_FOUND, "plant not found")
        filled = fill_plant_from_profile(
            plant, profile, set_name=plant.name == DEFAULT_PLANT_NAME
        )
        # O que a marca trouxe (sim/não por campo) e o que foi preenchido —
        # para diagnosticar "não mostrou dados" sem registrar valores.
        logger.info(
            "provider_profile_refreshed",
            extra={
                "plant_id": str(scoped.plant_id),
                "provider": provider,
                "profile_has": {
                    "name": bool(profile and profile.name),
                    "power": bool(profile and profile.installed_power_kwp is not None),
                    "location": bool(profile and profile.latitude is not None),
                    "city": bool(profile and profile.city),
                },
                "plant_already_had": {
                    "power": (
                        plant.installed_power_kwp is not None and "dc_capacity_kwp" not in filled
                    ),
                    "location": plant.latitude is not None and "location" not in filled,
                },
                "auto_filled": sorted(filled),
            },
        )
        await AuditEventRepository(session).record(
            request,
            action="provider_account.profile_refreshed",
            resource_type="plant",
            resource_id=str(scoped.plant_id),
            outcome="SUCCEEDED",
            details={"provider": provider, "auto_filled": sorted(filled)},
        )
        result = ProfileRefreshResult(auto_filled=filled, plant_name=plant.name)
        await session.commit()
    return result


async def _log_token_probe(login: str, token: str, plant_id: uuid.UUID) -> None:
    """Registra quais leituras o token Growatt alcança, sem conteúdo (ADR-094).

    O token lista as usinas mas a produção vem com 10011; este mapa mostra por
    onde é possível ler. Nunca falha a requisição original.
    """
    probe_client = build_client(GROWATT_TOKEN, account=login, password=token)
    try:
        if not isinstance(probe_client, GrowattOpenApiClient):
            return
        result = await probe_client.probe()
    except Exception as exc:  # diagnóstico nunca derruba a resposta
        result = {"probe": type(exc).__name__}
    finally:
        await probe_client.aclose()
    logger.info("growatt_token_probe", extra={"plant_id": str(plant_id), "probe": result})


HISTORY_DAYS = 90
HISTORY_LIMIT = 2
# Teto separado do da conexão: uma marca fora do ar não impede trocar a senha
# (e vice-versa). O teto conta o início da importação, gravado ANTES de chamar a marca: duas
# abas ou um clique duplo não passam juntos pelo teto enquanto a primeira
# ainda está lendo os 90 dias.
_HISTORY_ACTIONS = ("provider_account.history_import_started",)


class HistoryImportResult(BaseModel):
    start_date: date
    end_date: date
    # dias com produção recebidos da marca e quantos mudaram no banco
    days_received: int
    days_changed: int


@router.post("/{plant_id}/provider-account/import-history", response_model=HistoryImportResult)
async def import_production_history(
    request: Request, scoped: AdminPlantPath
) -> HistoryImportResult:
    """Importa a produção dos últimos 90 dias da marca (ADR-097).

    Logo depois de conectar, o painel já mostra produção — sem esperar a
    coleta da madrugada. Idempotente (reimportar só atualiza os dias); usa a
    conexão guardada; teto próprio de 2 importações a cada 10 minutos.
    """
    box = _box()
    await _enforce_verify_limit(scoped.plant_id, actions=_HISTORY_ACTIONS, limit=HISTORY_LIMIT)
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        record = await ProviderAccountService(session, box).get(scoped.plant_id)
        if record is None or not record.active:
            raise _error(status.HTTP_404_NOT_FOUND, "provider_account_not_found")
        provider = record.provider
        try:
            credentials = ProviderAccountService(session, box).open(record)
        except ProviderAccountError:
            raise _error(
                status.HTTP_503_SERVICE_UNAVAILABLE, "provider_account_unreadable"
            ) from None

    async def refuse(reason: str) -> None:
        await _audit_refusal(
            request,
            scoped.principal,
            "plant",
            scoped.plant_id,
            provider,
            reason,
            action="provider_account.history_import_failed",
        )

    end = datetime.now(ZoneInfo(get_settings().timezone)).date() - timedelta(days=1)
    start = end - timedelta(days=HISTORY_DAYS - 1)
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        await AuditEventRepository(session).record(
            request,
            action="provider_account.history_import_started",
            resource_type="plant",
            resource_id=str(scoped.plant_id),
            outcome="SUCCEEDED",
            details={"provider": provider},
        )
        await session.commit()
    client = build_client(provider, account=credentials.login, password=credentials.password)
    try:
        # Mesmo contexto da coleta diária (collection/job.py): a usina já foi
        # autorizada acima (ADMIN da organização) e a checagem de inversor em
        # outra usina precisa enxergar todas as organizações.
        async with SessionFactory() as session:
            await set_platform_context(session)
            result = await SolarCollectionService(
                session,
                client,
                provider_name=provider,
                energy_source=ENERGY_SOURCES[provider],
            ).collect(plant_id=scoped.plant_id, start=start, end=end, consolidate_through=end)
    except CollectionPlantError:
        await refuse("provider_inverter_in_another_plant")
        raise _error(status.HTTP_409_CONFLICT, "provider_inverter_in_another_plant") from None
    except ProviderRateLimitedError:
        await refuse("provider_rate_limited")
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_rate_limited") from None
    except ProviderBlockedError:
        # bloqueio da marca não é senha errada: mesmo código da conexão
        await refuse("provider_login_blocked")
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_login_blocked") from None
    except ProviderAuthError:
        reason = "provider_token_failed" if provider == GROWATT_TOKEN else "provider_login_failed"
        if provider == GROWATT_TOKEN:
            await _log_token_probe(credentials.login, credentials.password, scoped.plant_id)
        await refuse(reason)
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, reason) from None
    except ProviderError:
        await refuse("provider_unavailable")
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "provider_unavailable") from None
    except Exception as exc:
        # ex.: a coleta diária gravando o mesmo dia ao mesmo tempo. Sempre
        # auditado; o log leva só o tipo do erro, nunca dado da conexão.
        logger.warning(
            "provider_history_import_error",
            extra={"plant_id": str(scoped.plant_id), "error_code": type(exc).__name__},
        )
        await refuse("history_import_error")
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "history_import_error") from None
    finally:
        await client.aclose()

    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        await AuditEventRepository(session).record(
            request,
            action="provider_account.history_imported",
            resource_type="plant",
            resource_id=str(scoped.plant_id),
            outcome="SUCCEEDED",
            details={
                "provider": provider,
                "days_received": result.records_received,
                "days_changed": result.records_changed,
            },
        )
        await session.commit()
    logger.info(
        "provider_history_imported",
        extra={
            "plant_id": str(scoped.plant_id),
            "provider": provider,
            "days_received": result.records_received,
            "days_changed": result.records_changed,
        },
    )
    return HistoryImportResult(
        start_date=start,
        end_date=end,
        days_received=result.records_received,
        days_changed=result.records_changed,
    )


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
