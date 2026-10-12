"""Domain operations on organizations, independent of the HTTP layer.

The router owns the transaction boundary (session, tenant context, audit
event, commit/rollback) and the HTTP status codes; this service owns the
queries and rules, and raises domain errors instead of ``HTTPException``.

Tenant-hiding convention, kept from the router: whenever a caller asks for an
organization (or a plant) it may not see, the error is the same "not found"
it would get if the id did not exist at all, so responses never reveal
whether a record exists for another tenant.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.auth.session_service import AuthSessionService
from mplacas.core.principal import OperationsRole
from mplacas.db.models import Plant
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_db_models import UserInvitationRecord
from mplacas.organizations.invitation_service import InvitationService
from mplacas.organizations.schemas import (
    OrganizationCreateRequest,
    OrganizationUpdateRequest,
)


class OrganizationNotFoundError(LookupError):
    """Missing, or not visible to the caller (indistinguishable on purpose)."""


class SlugInUseError(ValueError):
    """Another organization already uses this slug."""


class DefaultPlantNotFoundError(LookupError):
    """The requested default plant is missing or belongs to another organization."""


class TelegramChatAlreadyLinkedError(ValueError):
    """``telegram_chat_id`` is unique across organizations and already taken."""


class OrganizationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_with_bootstrap_admin(
        self,
        payload: OrganizationCreateRequest,
        *,
        invitation_ttl_seconds: int,
    ) -> tuple[OrganizationRecord, UserInvitationRecord, str]:
        """Create an active organization plus the ADMIN invitation that bootstraps it.

        Raises ``SlugInUseError``, or lets ``InvitationError`` propagate. Nothing
        is committed: if the invitation fails, the caller discards the session
        and both inserts are rolled back together.
        """
        existing = await self._session.scalar(
            select(OrganizationRecord).where(OrganizationRecord.slug == payload.slug)
        )
        if existing is not None:
            raise SlugInUseError(payload.slug)

        organization = OrganizationRecord(
            name=payload.name,
            slug=payload.slug,
            active=True,
        )
        self._session.add(organization)
        await self._session.flush()

        invitation, token = await InvitationService(self._session).create(
            organization_id=organization.id,
            username=payload.admin_username,
            role=OperationsRole.ADMIN,
            created_by_user_id=None,
            ttl_seconds=invitation_ttl_seconds,
        )
        return organization, invitation, token

    async def list_visible(
        self, *, principal_organization_id: uuid.UUID | None
    ) -> list[OrganizationRecord]:
        """Every organization for the platform, only its own for a tenant."""
        statement = select(OrganizationRecord).order_by(OrganizationRecord.created_at)
        if principal_organization_id is not None:
            statement = statement.where(OrganizationRecord.id == principal_organization_id)
        return list(await self._session.scalars(statement))

    async def get_visible(
        self,
        organization_id: uuid.UUID,
        *,
        principal_organization_id: uuid.UUID | None,
    ) -> OrganizationRecord:
        """Fetch ``organization_id``, hiding its existence from non-owning callers.

        A platform principal (``principal_organization_id is None``) may fetch
        any organization. A tenant principal may only fetch its own; any other
        id — whether it exists or not — raises the same
        ``OrganizationNotFoundError``, and is never even queried.
        """
        if (
            principal_organization_id is not None
            and organization_id != principal_organization_id
        ):
            raise OrganizationNotFoundError(organization_id)
        record = await self._session.get(OrganizationRecord, organization_id)
        if record is None:
            raise OrganizationNotFoundError(organization_id)
        return record

    async def update(
        self, record: OrganizationRecord, payload: OrganizationUpdateRequest
    ) -> None:
        """Apply only the fields present in the payload, then flush.

        Raises ``DefaultPlantNotFoundError`` when ``default_plant_id`` is not a
        plant of *this* organization, and ``TelegramChatAlreadyLinkedError``
        when the flush hits the unique ``telegram_chat_id`` constraint. In both
        cases fields may already be mutated: the caller must roll back.
        """
        fields_set = payload.model_fields_set
        if "telegram_chat_id" in fields_set:
            record.telegram_chat_id = payload.telegram_chat_id
        if "telegram_allowed_user_id" in fields_set:
            record.telegram_allowed_user_id = payload.telegram_allowed_user_id
        if "default_plant_id" in fields_set:
            if payload.default_plant_id is not None:
                plant = await self._session.scalar(
                    select(Plant.id).where(
                        Plant.id == payload.default_plant_id,
                        Plant.organization_id == record.id,
                    )
                )
                if plant is None:
                    raise DefaultPlantNotFoundError(payload.default_plant_id)
            record.default_plant_id = payload.default_plant_id
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise TelegramChatAlreadyLinkedError(payload.telegram_chat_id) from exc

    async def deactivate(
        self, organization_id: uuid.UUID, *, now: datetime
    ) -> tuple[OrganizationRecord, int]:
        """Deactivate (idempotently) and revoke every session of the organization.

        Returns the record and how many sessions were revoked. Sessions are
        revoked even when the organization was already inactive.
        """
        record = await self._session.get(OrganizationRecord, organization_id)
        if record is None:
            raise OrganizationNotFoundError(organization_id)
        if record.active:
            record.active = False
            record.deactivated_at = now
            await self._session.flush()

        revoked_count = await AuthSessionService(self._session).revoke_all_for_organization(
            organization_id=organization_id
        )
        return record, revoked_count
