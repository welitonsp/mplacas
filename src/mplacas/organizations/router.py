from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.audit.repository import AuditEventRepository
from mplacas.auth.session_service import AuthSessionService
from mplacas.core.config import get_settings
from mplacas.core.principal import OperationsRole
from mplacas.core.tenancy import AdminPrincipal, PlatformPrincipal
from mplacas.db.session import SessionFactory
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_service import InvitationError, InvitationService

router = APIRouter(prefix="/organizations", tags=["organizations"])

_SLUG_PATTERN = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=80, pattern=_SLUG_PATTERN)
    admin_username: str = Field(min_length=1, max_length=80)


def _organization_view(record: OrganizationRecord) -> dict[str, object]:
    return {
        "id": str(record.id),
        "name": record.name,
        "slug": record.slug,
        "active": record.active,
        "created_at": record.created_at,
        "telegram_chat_id": record.telegram_chat_id,
    }


async def _get_own_or_404(
    session: AsyncSession,
    organization_id: uuid.UUID,
    principal_organization_id: uuid.UUID | None,
) -> OrganizationRecord:
    """Fetch ``organization_id``, hiding its existence from non-owning callers.

    A platform principal (``principal_organization_id is None``) may fetch any
    organization. A tenant principal may only fetch its own organization; any
    other id (whether it exists or not) is reported as 404, not 403, so the
    response never reveals whether an organization with that id exists.
    """
    if (
        principal_organization_id is not None
        and organization_id != principal_organization_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization not found")
    record = await session.get(OrganizationRecord, organization_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization not found")
    return record


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    request: Request,
    payload: OrganizationCreateRequest,
    principal: PlatformPrincipal,
) -> dict[str, object]:
    settings = get_settings()
    async with SessionFactory() as session:
        existing = await session.scalar(
            select(OrganizationRecord).where(OrganizationRecord.slug == payload.slug)
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="slug is already in use",
            )

        organization = OrganizationRecord(
            name=payload.name,
            slug=payload.slug,
            active=True,
        )
        session.add(organization)
        await session.flush()

        try:
            invitation, token = await InvitationService(session).create(
                organization_id=organization.id,
                username=payload.admin_username,
                role=OperationsRole.ADMIN,
                created_by_user_id=None,
                ttl_seconds=settings.auth_invitation_ttl_seconds,
            )
        except InvitationError as exc:
            # Neither the organization nor the invitation is committed: the
            # session is discarded without a commit() call, so both inserts
            # above are rolled back together.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        await AuditEventRepository(session).record(
            request,
            action="organizations.create",
            resource_type="organization",
            resource_id=str(organization.id),
            outcome="SUCCEEDED",
            details={"slug": organization.slug},
        )
        await session.commit()

    view = _organization_view(organization)
    view["bootstrap_invitation"] = {
        "id": str(invitation.id),
        "username": invitation.username,
        "role": invitation.role,
        "expires_at": invitation.expires_at,
        "token": token,
        "token_notice": "store this token now; it is not retrievable again",
    }
    return view


@router.get("")
async def list_organizations(principal: AdminPrincipal) -> dict[str, object]:
    async with SessionFactory() as session:
        statement = select(OrganizationRecord).order_by(OrganizationRecord.created_at)
        if principal.organization_id is not None:
            statement = statement.where(
                OrganizationRecord.id == principal.organization_id
            )
        records = list(await session.scalars(statement))
    return {
        "count": len(records),
        "items": [_organization_view(record) for record in records],
    }


@router.get("/{organization_id}")
async def get_organization(
    organization_id: uuid.UUID,
    principal: AdminPrincipal,
) -> dict[str, object]:
    async with SessionFactory() as session:
        record = await _get_own_or_404(
            session, organization_id, principal.organization_id
        )
    return _organization_view(record)


@router.post("/{organization_id}/deactivate")
async def deactivate_organization(
    request: Request,
    organization_id: uuid.UUID,
    principal: PlatformPrincipal,
) -> dict[str, object]:
    async with SessionFactory() as session:
        record = await session.get(OrganizationRecord, organization_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="organization not found",
            )
        if record.active:
            record.active = False
            record.deactivated_at = datetime.now(timezone.utc)
            await session.flush()

        revoked_count = await AuthSessionService(session).revoke_all_for_organization(
            organization_id=organization_id
        )

        await AuditEventRepository(session).record(
            request,
            action="organizations.deactivate",
            resource_type="organization",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details={"slug": record.slug, "revoked_session_count": revoked_count},
        )
        await session.commit()
    return _organization_view(record)


__all__ = ["router"]
