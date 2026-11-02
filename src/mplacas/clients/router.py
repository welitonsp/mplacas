"""Clientes do dono: criar a organização do cliente e o convite (ADR-093).

Só o operador da plataforma (chave de operação ou ADMIN da organização
default) usa estas rotas. As consultas rodam em contexto de plataforma — a
organização do cliente não é a do operador —, sempre depois da autorização.
O token do convite volta uma única vez, na resposta; nunca vai para log nem
auditoria.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.audit.db_models import AuditEventRecord
from mplacas.audit.repository import AuditEventRepository
from mplacas.core.config import get_settings
from mplacas.core.security import OperationsRole
from mplacas.core.tenancy import PlatformOperator
from mplacas.credentials.db_models import OperationalUserRecord
from mplacas.db.models import Plant
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_platform_context
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.organizations.invitation_db_models import (
    PURPOSE_INVITE,
    PURPOSE_RESET,
    UserInvitationRecord,
)
from mplacas.organizations.invitation_service import InvitationError, InvitationService
from mplacas.organizations.schemas import OrganizationCreateRequest
from mplacas.organizations.service import OrganizationService, SlugInUseError
from mplacas.providers.db_models import ProviderAccountRecord

router = APIRouter(prefix="/platform/clients", tags=["platform"])

_MAX_SLUG = 80


class ClientCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    admin_username: str = Field(min_length=3, max_length=80)


class ClientInviteRequest(BaseModel):
    admin_username: str | None = Field(default=None, min_length=3, max_length=80)


def slugify(name: str) -> str:
    """``"Usina do Rogério"`` → ``"usina-do-rogerio"``; vazio vira ``"cliente"``."""
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    return (slug or "cliente")[:_MAX_SLUG].strip("-") or "cliente"


async def _free_slug(session: AsyncSession, base: str) -> str:
    existing = set(
        await session.scalars(
            select(OrganizationRecord.slug).where(OrganizationRecord.slug.like(f"{base}%"))
        )
    )
    if base not in existing:
        return base
    for suffix in range(2, 1000):
        candidate = f"{base[: _MAX_SLUG - len(str(suffix)) - 1]}-{suffix}"
        if candidate not in existing:
            return candidate
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="client_slug_exhausted")


def _invitation_view(record: UserInvitationRecord, token: str) -> dict[str, object]:
    return {
        "username": record.username,
        "expires_at": record.expires_at,
        "token": token,
        "token_notice": "envie o link só ao cliente; ele não pode ser recuperado depois",
    }


def _counts(rows) -> dict[uuid.UUID, int]:
    return {row[0]: int(row[1]) for row in rows}


def _pending(record: UserInvitationRecord, now: datetime) -> bool:
    expires = (
        record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=UTC)
    )
    return record.accepted_at is None and record.revoked_at is None and expires > now


@router.get("")
async def list_clients(principal: PlatformOperator) -> dict[str, object]:
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        await set_platform_context(session)
        organizations = list(
            await session.scalars(
                select(OrganizationRecord)
                .where(OrganizationRecord.id != DEFAULT_ORGANIZATION_ID)
                .order_by(OrganizationRecord.created_at.desc())
            )
        )
        ids = [org.id for org in organizations]
        plants: dict[uuid.UUID, int] = _counts(
            (
                await session.execute(
                    select(Plant.organization_id, func.count(Plant.id))
                    .where(Plant.organization_id.in_(ids))
                    .group_by(Plant.organization_id)
                )
            ).all()
        )
        connections: dict[uuid.UUID, int] = _counts(
            (
                await session.execute(
                    select(Plant.organization_id, func.count(ProviderAccountRecord.id))
                    .join(ProviderAccountRecord, ProviderAccountRecord.plant_id == Plant.id)
                    .where(Plant.organization_id.in_(ids), ProviderAccountRecord.active.is_(True))
                    .group_by(Plant.organization_id)
                )
            ).all()
        )
        users: dict[uuid.UUID, int] = _counts(
            (
                await session.execute(
                    select(
                        OperationalUserRecord.organization_id, func.count(OperationalUserRecord.id)
                    )
                    .where(
                        OperationalUserRecord.organization_id.in_(ids),
                        OperationalUserRecord.active.is_(True),
                    )
                    .group_by(OperationalUserRecord.organization_id)
                )
            ).all()
        )
        invitations = list(
            await session.scalars(
                select(UserInvitationRecord)
                .where(
                    UserInvitationRecord.organization_id.in_(ids),
                    UserInvitationRecord.purpose == PURPOSE_INVITE,
                )
                .order_by(UserInvitationRecord.created_at.desc())
            )
        )
        accounts = await _accounts_by_org(session, ids)
    latest: dict[uuid.UUID, UserInvitationRecord] = {}
    for record in invitations:
        latest.setdefault(record.organization_id, record)
    items = []
    for org in organizations:
        last = latest.get(org.id)
        items.append(
            {
                "organization_id": str(org.id),
                "name": org.name,
                "slug": org.slug,
                "active": org.active,
                "created_at": org.created_at,
                "users": int(users.get(org.id, 0)),
                "plants": int(plants.get(org.id, 0)),
                "connections": int(connections.get(org.id, 0)),
                "admin_username": last.username if last else None,
                "invitation_pending_until": (
                    last.expires_at if last and _pending(last, now) else None
                ),
                "stage": _stage(
                    active=org.active,
                    users=int(users.get(org.id, 0)),
                    account=accounts.get(org.id),
                    invitation_pending=bool(last and _pending(last, now)),
                ),
                "last_success_at": (
                    accounts[org.id].last_success_at if org.id in accounts else None
                ),
            }
        )
    return {"items": items}


# Etapas do cliente (ADR-095), na ordem do funil. Decididas aqui, nunca na tela.
STAGES = (
    "CONVIDADO",
    "CONVITE_VENCIDO",
    "ENTROU",
    "USINA_CONECTADA",
    "RECEBENDO_DADOS",
    "COM_FALHA",
    "DESATIVADO",
)


def _stage(
    *,
    active: bool,
    users: int,
    account: ProviderAccountRecord | None,
    invitation_pending: bool,
) -> str:
    if not active:
        return "DESATIVADO"
    if account is not None:
        failing = account.last_failure_at is not None and (
            account.last_success_at is None or account.last_failure_at > account.last_success_at
        )
        if failing:
            return "COM_FALHA"
        return "RECEBENDO_DADOS" if account.last_success_at else "USINA_CONECTADA"
    if users > 0:
        return "ENTROU"
    return "CONVIDADO" if invitation_pending else "CONVITE_VENCIDO"


async def _accounts_by_org(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, ProviderAccountRecord]:
    """Conexão ativa mais recente de cada organização."""
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(Plant.organization_id, ProviderAccountRecord)
            .join(ProviderAccountRecord, ProviderAccountRecord.plant_id == Plant.id)
            .where(Plant.organization_id.in_(ids), ProviderAccountRecord.active.is_(True))
            .order_by(ProviderAccountRecord.created_at)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_client(
    request: Request,
    response: Response,
    payload: ClientCreateRequest,
    principal: PlatformOperator,
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    async with SessionFactory() as session:
        await set_platform_context(session)
        slug = await _free_slug(session, slugify(payload.name))
        try:
            organization, invitation, token = await OrganizationService(
                session
            ).create_with_bootstrap_admin(
                OrganizationCreateRequest(
                    name=payload.name.strip(),
                    slug=slug,
                    admin_username=payload.admin_username.strip(),
                ),
                invitation_ttl_seconds=settings.auth_invitation_ttl_seconds,
            )
        except (SlugInUseError, IntegrityError):
            # IntegrityError: corrida entre dois cadastros com o mesmo nome
            # (ex.: clique duplo) — o segundo perde no índice único do slug.
            raise HTTPException(status.HTTP_409_CONFLICT, "client_slug_in_use") from None
        except InvitationError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "client_admin_username_invalid"
            ) from None
        await AuditEventRepository(session).record(
            request,
            organization_id=organization.id,
            action="platform.client_created",
            resource_type="organization",
            resource_id=str(organization.id),
            outcome="SUCCEEDED",
            details={"slug": organization.slug},
        )
        await session.commit()
    return {
        "organization_id": str(organization.id),
        "name": organization.name,
        "slug": organization.slug,
        "invitation": _invitation_view(invitation, token),
    }


@router.post("/{organization_id}/invitation", status_code=status.HTTP_201_CREATED)
async def reinvite_client(
    request: Request,
    response: Response,
    organization_id: uuid.UUID,
    payload: ClientInviteRequest,
    principal: PlatformOperator,
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    async with SessionFactory() as session:
        await set_platform_context(session)
        # trava a organização: dois reenvios simultâneos não deixam dois convites vivos
        organization = await session.get(OrganizationRecord, organization_id, with_for_update=True)
        if (
            organization is None
            or organization.id == DEFAULT_ORGANIZATION_ID
            or not organization.active
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "client_not_found")
        service = InvitationService(session)
        admin_invitations = [
            record
            for record in await service.list(organization_id=organization.id)
            if record.role == OperationsRole.ADMIN.value and record.purpose == PURPOSE_INVITE
        ]
        # service.list vem do mais antigo ao mais novo: o último é o convite vigente
        latest_admin = admin_invitations[-1] if admin_invitations else None
        username = payload.admin_username or (latest_admin.username if latest_admin else None)
        if not username:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "client_admin_username_invalid"
            )
        now = datetime.now(UTC)
        for record in admin_invitations:
            # só os convites de ADMIN pendentes; convites que o próprio cliente
            # fez para outras pessoas ficam como estão
            if _pending(record, now):
                await service.revoke(invitation_id=record.id, organization_id=organization.id)
        try:
            invitation, token = await service.create(
                organization_id=organization.id,
                username=username,
                role=OperationsRole.ADMIN,
                created_by_user_id=None,
                ttl_seconds=settings.auth_invitation_ttl_seconds,
            )
        except InvitationError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "client_admin_username_invalid"
            ) from None
        await AuditEventRepository(session).record(
            request,
            organization_id=organization.id,
            action="platform.client_invited",
            resource_type="organization",
            resource_id=str(organization.id),
            outcome="SUCCEEDED",
        )
        await session.commit()
    return {
        "organization_id": str(organization.id),
        "invitation": _invitation_view(invitation, token),
    }


# --- Ficha do cliente (ADR-095) ---------------------------------------------

# O histórico mostra só ações conhecidas e só campos seguros dos detalhes:
# nunca token, senha, login ou nome de usuário de outra pessoa.
_ACTIVITY_ACTIONS = {
    "platform.client_created",
    "platform.client_invited",
    "platform.client_access_reset",
    "platform.client_deactivated",
    "platform.client_reactivated",
    "invitations.accept",
    "invitations.access_reset",
    "plant.connect_previewed",
    "plant.created_from_connection",
    "provider_account.saved",
    "provider_account.profile_refreshed",
    "provider_account.verify_failed",
    "provider_account.removed",
}
_SAFE_DETAIL_KEYS = ("provider", "reason", "devices_found", "auto_filled")
_ACTIVITY_LIMIT = 50


def _safe_details(details: object) -> dict[str, object]:
    if not isinstance(details, dict):
        return {}
    return {key: details[key] for key in _SAFE_DETAIL_KEYS if key in details}


async def _client_or_404(
    session: AsyncSession, organization_id: uuid.UUID, *, for_update: bool = False
) -> OrganizationRecord:
    organization = await session.get(
        OrganizationRecord, organization_id, with_for_update=for_update
    )
    if organization is None or organization.id == DEFAULT_ORGANIZATION_ID:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "client_not_found")
    return organization


@router.get("/{organization_id}")
async def get_client(organization_id: uuid.UUID, principal: PlatformOperator) -> dict[str, object]:
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        await set_platform_context(session)
        organization = await _client_or_404(session, organization_id)
        users = list(
            await session.scalars(
                select(OperationalUserRecord)
                .where(OperationalUserRecord.organization_id == organization.id)
                .order_by(OperationalUserRecord.created_at)
            )
        )
        plants = list(
            await session.scalars(
                select(Plant).where(Plant.organization_id == organization.id).order_by(Plant.name)
            )
        )
        account = (await _accounts_by_org(session, [organization.id])).get(organization.id)
        invitations = list(
            await session.scalars(
                select(UserInvitationRecord)
                .where(UserInvitationRecord.organization_id == organization.id)
                .order_by(UserInvitationRecord.created_at.desc())
            )
        )
        events = list(
            await session.scalars(
                select(AuditEventRecord)
                .where(
                    AuditEventRecord.organization_id == organization.id,
                    AuditEventRecord.action.in_(sorted(_ACTIVITY_ACTIONS)),
                )
                .order_by(AuditEventRecord.created_at.desc())
                .limit(_ACTIVITY_LIMIT)
            )
        )
    invite = next((r for r in invitations if r.purpose == PURPOSE_INVITE), None)
    pending = [r for r in invitations if _pending(r, now)]
    active_users = [u for u in users if u.active]
    return {
        "organization_id": str(organization.id),
        "name": organization.name,
        "active": organization.active,
        "created_at": organization.created_at,
        "stage": _stage(
            active=organization.active,
            users=len(active_users),
            account=account,
            invitation_pending=bool(invite and _pending(invite, now)),
        ),
        "admin_username": active_users[0].name
        if active_users
        else (invite.username if invite else None),
        "users": [
            {"username": u.name, "role": u.role, "active": u.active, "created_at": u.created_at}
            for u in users
        ],
        "plants": [
            {
                "plant_id": str(plant.id),
                "name": plant.name,
                "installed_power_kwp": plant.installed_power_kwp,
                "city_known": plant.latitude is not None,
            }
            for plant in plants
        ],
        "connection": (
            {
                "provider": account.provider,
                "connected_at": account.rotated_at or account.created_at,
                "last_success_at": account.last_success_at,
                "last_failure_at": account.last_failure_at,
                "last_failure_code": account.last_failure_code,
            }
            if account
            else None
        ),
        "pending_link": (
            {"purpose": pending[0].purpose, "expires_at": pending[0].expires_at}
            if pending
            else None
        ),
        "activity": [
            {
                "action": event.action,
                "outcome": event.outcome,
                "at": event.created_at,
                "details": _safe_details(event.details),
            }
            for event in events
        ],
    }


@router.post("/{organization_id}/access-reset", status_code=status.HTTP_201_CREATED)
async def reset_client_access(
    request: Request, response: Response, organization_id: uuid.UUID, principal: PlatformOperator
) -> dict[str, object]:
    """Link de uso único para o cliente criar uma senha nova (ADR-095).

    Só para quem já entrou (para quem não entrou, é "Novo convite"). Revoga os
    links pendentes da organização e, ao ser usado, encerra as sessões antigas.
    """
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    async with SessionFactory() as session:
        await set_platform_context(session)
        organization = await _client_or_404(session, organization_id, for_update=True)
        if not organization.active:
            raise HTTPException(status.HTTP_409_CONFLICT, "client_inactive")
        user = await session.scalar(
            select(OperationalUserRecord)
            .where(
                OperationalUserRecord.organization_id == organization.id,
                OperationalUserRecord.active.is_(True),
                OperationalUserRecord.role == OperationsRole.ADMIN.value,
            )
            .order_by(OperationalUserRecord.created_at)
        )
        if user is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "client_has_no_user")
        service = InvitationService(session)
        now = datetime.now(UTC)
        for record in await service.list(organization_id=organization.id):
            if record.purpose == PURPOSE_RESET and _pending(record, now):
                await service.revoke(invitation_id=record.id, organization_id=organization.id)
        invitation, token = await service.create(
            organization_id=organization.id,
            username=user.name,
            role=OperationsRole(user.role),
            created_by_user_id=None,
            ttl_seconds=settings.auth_invitation_ttl_seconds,
            purpose=PURPOSE_RESET,
        )
        await AuditEventRepository(session).record(
            request,
            organization_id=organization.id,
            action="platform.client_access_reset",
            resource_type="organization",
            resource_id=str(organization.id),
            outcome="SUCCEEDED",
        )
        await session.commit()
    return {
        "organization_id": str(organization.id),
        "invitation": _invitation_view(invitation, token),
    }


async def _set_client_active(
    request: Request, organization_id: uuid.UUID, *, active: bool
) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_platform_context(session)
        organization = await _client_or_404(session, organization_id, for_update=True)
        if active:
            organization.active = True
            organization.deactivated_at = None
            revoked = 0
        else:
            organization, revoked = await OrganizationService(session).deactivate(
                organization.id, now=datetime.now(UTC)
            )
        await AuditEventRepository(session).record(
            request,
            organization_id=organization.id,
            action="platform.client_reactivated" if active else "platform.client_deactivated",
            resource_type="organization",
            resource_id=str(organization.id),
            outcome="SUCCEEDED",
            details={} if active else {"sessions_revoked": revoked},
        )
        await session.commit()
    return {"organization_id": str(organization.id), "active": active}


@router.post("/{organization_id}/deactivate")
async def deactivate_client(
    request: Request, organization_id: uuid.UUID, principal: PlatformOperator
) -> dict[str, object]:
    """Bloqueia o acesso sem apagar nada: sessões encerradas, login recusado."""
    return await _set_client_active(request, organization_id, active=False)


@router.post("/{organization_id}/reactivate")
async def reactivate_client(
    request: Request, organization_id: uuid.UUID, principal: PlatformOperator
) -> dict[str, object]:
    return await _set_client_active(request, organization_id, active=True)
