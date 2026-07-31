from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.audit.repository import AuditEventRepository
from mplacas.auth.session_service import AuthSessionService
from mplacas.core.config import get_settings
from mplacas.core.principal import OperationsRole
from mplacas.core.tenancy import AdminPrincipal, OrgAdminPrincipal, PlatformPrincipal
from mplacas.db.session import SessionFactory
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_db_models import UserInvitationRecord
from mplacas.organizations.invitation_service import InvitationError, InvitationService

router = APIRouter(prefix="/organizations", tags=["organizations"])

_SLUG_PATTERN = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=80, pattern=_SLUG_PATTERN)
    admin_username: str = Field(min_length=1, max_length=80)


class InvitationCreateRequest(BaseModel):
    # Deliberately no ``organization_id`` field: it is always derived from
    # ``principal.organization_id`` (see ``create_invitation``), never
    # accepted from the request body, following the same convention as
    # ``credentials.router._resolve_organization_id``.
    username: str = Field(min_length=1, max_length=80)
    role: OperationsRole


def _organization_view(record: OrganizationRecord) -> dict[str, object]:
    return {
        "id": str(record.id),
        "name": record.name,
        "slug": record.slug,
        "active": record.active,
        "created_at": record.created_at,
        "telegram_chat_id": record.telegram_chat_id,
        "telegram_allowed_user_id": record.telegram_allowed_user_id,
    }


class OrganizationUpdateRequest(BaseModel):
    """Partial update for an organization's Telegram linkage.

    Only ``telegram_chat_id`` and ``telegram_allowed_user_id`` are editable
    here (name/slug/active are out of scope for this endpoint). A field
    omitted from the request body is left untouched; a field sent explicitly
    as ``null`` clears (unlinks) the corresponding column. Both fields default
    to ``None``, and ``model_fields_set`` (Pydantic's own tracking of which
    fields were present in the parsed payload) is what distinguishes
    "omitted" from "sent as null" in ``update_organization`` below — not the
    field's value itself.
    """

    telegram_chat_id: int | None = None
    telegram_allowed_user_id: int | None = None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _invitation_status(record: UserInvitationRecord) -> str:
    """Derive a display status for an invitation, never persisted as a column.

    Precedence when more than one condition holds at once: ``ACCEPTED`` beats
    everything else (an invitation that was consumed is settled, regardless of
    ``revoked_at``/``expires_at`` afterwards); otherwise ``REVOKED`` beats
    ``EXPIRED`` (an admin's explicit revoke is the more specific, more recent
    signal than the invitation simply having aged out).
    """
    if record.accepted_at is not None:
        return "ACCEPTED"
    if record.revoked_at is not None:
        return "REVOKED"
    if _as_utc(record.expires_at) <= datetime.now(timezone.utc):
        return "EXPIRED"
    return "PENDING"


def _invitation_view(record: UserInvitationRecord) -> dict[str, object]:
    """Render an invitation for API responses.

    Never includes ``token`` or ``token_hash``: the plaintext token is only
    ever returned once, at creation time, by ``create_invitation`` itself
    (added to the dict there, not here), and the hash is never exposed.
    """
    return {
        "id": str(record.id),
        "username": record.username,
        "role": record.role,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
        "accepted_at": record.accepted_at,
        "revoked_at": record.revoked_at,
        "status": _invitation_status(record),
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


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    request: Request,
    payload: InvitationCreateRequest,
    principal: OrgAdminPrincipal,
) -> dict[str, object]:
    # ``require_organization_admin`` (behind ``OrgAdminPrincipal``) guarantees
    # ``organization_id`` is set; ``organization_id`` is never accepted from
    # the request body (see ``InvitationCreateRequest``).
    organization_id = principal.organization_id
    assert organization_id is not None

    settings = get_settings()
    async with SessionFactory() as session:
        try:
            invitation, token = await InvitationService(session).create(
                organization_id=organization_id,
                username=payload.username,
                role=payload.role,
                created_by_user_id=None,
                ttl_seconds=settings.auth_invitation_ttl_seconds,
            )
        except InvitationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        await AuditEventRepository(session).record(
            request,
            action="invitations.create",
            resource_type="user_invitation",
            resource_id=str(invitation.id),
            outcome="SUCCEEDED",
            details={"username": invitation.username, "role": invitation.role},
        )
        await session.commit()

    view = _invitation_view(invitation)
    view["token"] = token
    view["token_notice"] = "store this token now; it is not retrievable again"
    return view


@router.get("/invitations")
async def list_invitations(principal: OrgAdminPrincipal) -> dict[str, object]:
    organization_id = principal.organization_id
    assert organization_id is not None

    async with SessionFactory() as session:
        records = await InvitationService(session).list(organization_id=organization_id)
    return {
        "count": len(records),
        "items": [_invitation_view(record) for record in records],
    }


@router.post("/invitations/{invitation_id}/revoke")
async def revoke_invitation(
    request: Request,
    invitation_id: uuid.UUID,
    principal: OrgAdminPrincipal,
) -> dict[str, object]:
    organization_id = principal.organization_id
    assert organization_id is not None

    async with SessionFactory() as session:
        revoked = await InvitationService(session).revoke(
            invitation_id=invitation_id,
            organization_id=organization_id,
        )
        if not revoked:
            # Either the invitation does not exist, or it belongs to another
            # organization: 404 either way, so the response never reveals
            # whether an invitation with that id exists for another tenant
            # (same convention as ``_get_own_or_404`` above).
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="invitation not found",
            )

        record = await session.get(UserInvitationRecord, invitation_id)
        assert record is not None

        await AuditEventRepository(session).record(
            request,
            action="invitations.revoke",
            resource_type="user_invitation",
            resource_id=str(invitation_id),
            outcome="SUCCEEDED",
            details={"username": record.username},
        )
        await session.commit()

    return _invitation_view(record)


# ---------------------------------------------------------------------------
# ``/{organization_id}`` routes: registered after the ``/invitations`` routes
# above. FastAPI/Starlette matches routes in registration order and, absent
# an explicit ``:uuid`` path converter, compiles ``{organization_id}`` to a
# generic ``[^/]+`` regex — so if this route were registered first, a request
# to ``/organizations/invitations`` would match here instead, with
# ``organization_id="invitations"`` failing UUID validation (422) rather than
# reaching the invitations routes.
# ---------------------------------------------------------------------------


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


@router.patch("/{organization_id}")
async def update_organization(
    request: Request,
    organization_id: uuid.UUID,
    payload: OrganizationUpdateRequest,
    principal: AdminPrincipal,
) -> dict[str, object]:
    """Partially update an organization's Telegram linkage.

    ``AdminPrincipal`` (not ``OrgAdminPrincipal``) plus ``_get_own_or_404``,
    same as ``get_organization`` above: this lets an organization's own admin
    self-configure its Telegram linkage while also letting the platform
    (static operational key, ``organization_id is None``) edit any
    organization for support/operations — the same "platform sees/edits any,
    tenant only its own" split already implemented by ``_get_own_or_404``, so
    no new dependency is needed.
    """
    fields_set = payload.model_fields_set
    async with SessionFactory() as session:
        record = await _get_own_or_404(
            session, organization_id, principal.organization_id
        )

        if "telegram_chat_id" in fields_set:
            record.telegram_chat_id = payload.telegram_chat_id
        if "telegram_allowed_user_id" in fields_set:
            record.telegram_allowed_user_id = payload.telegram_allowed_user_id
        try:
            await session.flush()
        except IntegrityError as exc:
            # telegram_chat_id is unique across organizations: surface a
            # conflict rather than a 500 when it is already linked elsewhere.
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="telegram_chat_id is already linked to another organization",
            ) from exc

        await AuditEventRepository(session).record(
            request,
            action="organizations.update",
            resource_type="organization",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details={"fields_updated": sorted(fields_set)},
        )
        await session.commit()

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
