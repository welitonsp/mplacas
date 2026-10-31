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

from mplacas.audit.repository import AuditEventRepository
from mplacas.core.config import get_settings
from mplacas.core.security import OperationsRole
from mplacas.core.tenancy import PlatformOperator
from mplacas.credentials.db_models import OperationalUserRecord
from mplacas.db.models import Plant
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_platform_context
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.organizations.invitation_db_models import UserInvitationRecord
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
                .where(UserInvitationRecord.organization_id.in_(ids))
                .order_by(UserInvitationRecord.created_at.desc())
            )
        )
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
            }
        )
    return {"items": items}


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
        organization = await session.get(
            OrganizationRecord, organization_id, with_for_update=True
        )
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
            if record.role == OperationsRole.ADMIN.value
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
