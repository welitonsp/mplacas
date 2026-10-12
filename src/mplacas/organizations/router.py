"""HTTP layer for ``/organizations``.

Owns the session, tenant context, audit events, commit/rollback and status
codes. Organization rules live in ``organizations.service``; invitation rules
in ``organizations.invitation_service``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

from mplacas.audit.repository import AuditEventRepository
from mplacas.core.config import get_settings
from mplacas.core.tenancy import AdminPrincipal, OrgAdminPrincipal, PlatformPrincipal
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_principal_context
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_db_models import UserInvitationRecord
from mplacas.organizations.invitation_service import InvitationError, InvitationService
from mplacas.organizations.schemas import (
    InvitationCreateRequest,
    OrganizationCreateRequest,
    OrganizationUpdateRequest,
)
from mplacas.organizations.service import (
    DefaultPlantNotFoundError,
    OrganizationNotFoundError,
    OrganizationService,
    SlugInUseError,
    TelegramChatAlreadyLinkedError,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _organization_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization not found")


def _organization_view(record: OrganizationRecord) -> dict[str, object]:
    return {
        "id": str(record.id),
        "name": record.name,
        "slug": record.slug,
        "active": record.active,
        "created_at": record.created_at,
        "telegram_chat_id": record.telegram_chat_id,
        "telegram_allowed_user_id": record.telegram_allowed_user_id,
        "default_plant_id": str(record.default_plant_id)
        if record.default_plant_id is not None
        else None,
    }


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


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    request: Request,
    payload: OrganizationCreateRequest,
    principal: PlatformPrincipal,
) -> dict[str, object]:
    settings = get_settings()
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        try:
            (
                organization,
                invitation,
                token,
            ) = await OrganizationService(session).create_with_bootstrap_admin(
                payload,
                invitation_ttl_seconds=settings.auth_invitation_ttl_seconds,
            )
        except SlugInUseError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="slug is already in use",
            ) from None
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
            organization_id=organization.id,
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
        await set_principal_context(session, principal)
        records = await OrganizationService(session).list_visible(
            principal_organization_id=principal.organization_id
        )
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
        await set_principal_context(session, principal)
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
            organization_id=organization_id,
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
        await set_principal_context(session, principal)
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
        await set_principal_context(session, principal)
        revoked = await InvitationService(session).revoke(
            invitation_id=invitation_id,
            organization_id=organization_id,
        )
        if not revoked:
            # Either the invitation does not exist, or it belongs to another
            # organization: 404 either way, so the response never reveals
            # whether an invitation with that id exists for another tenant
            # (same convention as ``OrganizationService.get_visible``).
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="invitation not found",
            )

        record = await session.get(UserInvitationRecord, invitation_id)
        assert record is not None

        await AuditEventRepository(session).record(
            request,
            organization_id=organization_id,
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
        await set_principal_context(session, principal)
        try:
            record = await OrganizationService(session).get_visible(
                organization_id, principal_organization_id=principal.organization_id
            )
        except OrganizationNotFoundError:
            raise _organization_not_found() from None
    return _organization_view(record)


@router.patch("/{organization_id}")
async def update_organization(
    request: Request,
    organization_id: uuid.UUID,
    payload: OrganizationUpdateRequest,
    principal: AdminPrincipal,
) -> dict[str, object]:
    """Partially update an organization's Telegram linkage.

    ``AdminPrincipal`` (not ``OrgAdminPrincipal``) plus ``get_visible``,
    same as ``get_organization`` above: this lets an organization's own admin
    self-configure its Telegram linkage while also letting the platform
    (static operational key, ``organization_id is None``) edit any
    organization for support/operations — the same "platform sees/edits any,
    tenant only its own" split already implemented by ``get_visible``, so
    no new dependency is needed.
    """
    fields_set = payload.model_fields_set
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        service = OrganizationService(session)
        try:
            record = await service.get_visible(
                organization_id, principal_organization_id=principal.organization_id
            )
        except OrganizationNotFoundError:
            raise _organization_not_found() from None

        try:
            await service.update(record, payload)
        except DefaultPlantNotFoundError:
            # Plant does not exist, or belongs to another organization: 404
            # either way, so the response never reveals whether a plant with
            # that id exists elsewhere. Discard the fields already mutated.
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="plant not found",
            ) from None
        except TelegramChatAlreadyLinkedError as exc:
            # telegram_chat_id is unique across organizations: surface a
            # conflict rather than a 500 when it is already linked elsewhere.
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="telegram_chat_id is already linked to another organization",
            ) from exc

        await AuditEventRepository(session).record(
            request,
            organization_id=record.id,
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
        await set_principal_context(session, principal)
        try:
            record, revoked_count = await OrganizationService(session).deactivate(
                organization_id, now=datetime.now(timezone.utc)
            )
        except OrganizationNotFoundError:
            raise _organization_not_found() from None

        await AuditEventRepository(session).record(
            request,
            organization_id=organization_id,
            action="organizations.deactivate",
            resource_type="organization",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details={"slug": record.slug, "revoked_session_count": revoked_count},
        )
        await session.commit()
    return _organization_view(record)


__all__ = ["router"]
