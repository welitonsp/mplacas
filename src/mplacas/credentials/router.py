from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.audit.repository import AuditEventRepository
from mplacas.core.config import get_settings
from mplacas.core.security import (
    OperationsPrincipal,
    OperationsRole,
    require_operations_key,
)
from mplacas.credentials.db_models import ApiCredentialRecord, OperationalUserRecord
from mplacas.credentials.service import CredentialError, CredentialService, UserService
from mplacas.db.session import SessionFactory
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord

router = APIRouter(
    prefix="/operations/credentials",
    tags=["operational"],
)


class CredentialCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role: OperationsRole
    plant_ids: list[uuid.UUID] | None = None
    user_id: uuid.UUID | None = None
    expires_at: datetime | None = None


class UserCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


async def _resolve_organization_id(
    session: AsyncSession,
    principal: OperationsPrincipal,
) -> uuid.UUID:
    """Derive the organization from the principal, falling back to a bootstrap default.

    Static environment API keys are intentionally not tenant-bound. They can bootstrap the
    initial single-tenant organization without accepting organization IDs from request bodies.
    """
    if principal.organization_id is not None:
        return principal.organization_id

    default = await session.get(OrganizationRecord, DEFAULT_ORGANIZATION_ID)
    if default is not None:
        return default.id

    result = await session.scalars(
        select(OrganizationRecord)
        .where(OrganizationRecord.active.is_(True))
        .order_by(OrganizationRecord.created_at)
        .limit(1)
    )
    existing = result.first()
    if existing is not None:
        return existing.id

    record = OrganizationRecord(
        id=DEFAULT_ORGANIZATION_ID,
        name="Default",
        slug="default",
        active=True,
    )
    session.add(record)
    await session.flush()
    return record.id


def _user_view(record: OperationalUserRecord) -> dict[str, object]:
    return {
        "id": str(record.id),
        "organization_id": str(record.organization_id),
        "name": record.name,
        "active": record.active,
        "created_at": record.created_at,
        "deactivated_at": record.deactivated_at,
    }


def _public_view(record: ApiCredentialRecord) -> dict[str, object]:
    return {
        "id": str(record.id),
        "organization_id": str(record.organization_id),
        "name": record.name,
        "role": record.role,
        "plant_ids": record.plant_ids,
        "active": record.active,
        "created_at": record.created_at,
        "revoked_at": record.revoked_at,
        "user_id": str(record.user_id) if record.user_id else None,
        "expires_at": record.expires_at,
    }


def _pepper() -> str:
    cfg = get_settings()
    if cfg.credential_pepper is None:
        return ""
    return cfg.credential_pepper.get_secret_value()


def _organization_details(record) -> dict[str, str]:
    return {
        "name": record.name,
        "organization_id": str(record.organization_id),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_credential(
    request: Request,
    payload: CredentialCreateRequest,
    principal: Annotated[OperationsPrincipal, Depends(require_operations_key)],
) -> dict[str, object]:
    principal.require_unrestricted_access()
    async with SessionFactory() as session:
        organization_id = await _resolve_organization_id(session, principal)
        service = CredentialService(session, pepper=_pepper())
        try:
            record, secret = await service.create(
                name=payload.name,
                role=payload.role,
                organization_id=organization_id,
                plant_ids=(
                    frozenset(payload.plant_ids) if payload.plant_ids is not None else None
                ),
                user_id=payload.user_id,
                expires_at=payload.expires_at,
            )
        except CredentialError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        await AuditEventRepository(session).record(
            request,
            action="credentials.create",
            resource_type="api_credential",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details={
                **_organization_details(record),
                "role": record.role,
                "plant_count": len(record.plant_ids or []),
            },
        )
        await session.commit()
    view = _public_view(record)
    view["secret"] = secret
    view["secret_notice"] = "store this secret now; it is not retrievable again"
    return view


@router.get("")
async def list_credentials(
    principal: Annotated[OperationsPrincipal, Depends(require_operations_key)],
) -> dict[str, object]:
    principal.require_unrestricted_access()
    async with SessionFactory() as session:
        records = await CredentialService(session).list_credentials(
            organization_id=principal.organization_id
        )
    return {
        "count": len(records),
        "items": [_public_view(record) for record in records],
    }


@router.post("/{credential_id}/revoke")
async def revoke_credential(
    request: Request,
    credential_id: uuid.UUID,
    principal: Annotated[OperationsPrincipal, Depends(require_operations_key)],
) -> dict[str, object]:
    principal.require_unrestricted_access()
    async with SessionFactory() as session:
        service = CredentialService(session, pepper=_pepper())
        try:
            record = await service.revoke(credential_id)
        except CredentialError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        if (
            principal.organization_id is not None
            and record.organization_id != principal.organization_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="credential not found",
            )
        await AuditEventRepository(session).record(
            request,
            action="credentials.revoke",
            resource_type="api_credential",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details=_organization_details(record),
        )
        await session.commit()
    return _public_view(record)


users_router = APIRouter(
    prefix="/operations/users",
    tags=["operational"],
)


@users_router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    payload: UserCreateRequest,
    principal: Annotated[OperationsPrincipal, Depends(require_operations_key)],
) -> dict[str, object]:
    principal.require_unrestricted_access()
    async with SessionFactory() as session:
        organization_id = await _resolve_organization_id(session, principal)
        try:
            record = await UserService(session).create(
                name=payload.name,
                organization_id=organization_id,
            )
        except CredentialError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        await AuditEventRepository(session).record(
            request,
            action="users.create",
            resource_type="operational_user",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details=_organization_details(record),
        )
        await session.commit()
    return _user_view(record)


@users_router.get("")
async def list_users(
    principal: Annotated[OperationsPrincipal, Depends(require_operations_key)],
) -> dict[str, object]:
    principal.require_unrestricted_access()
    async with SessionFactory() as session:
        records = await UserService(session).list_users(
            organization_id=principal.organization_id
        )
    return {
        "count": len(records),
        "items": [_user_view(record) for record in records],
    }


@users_router.post("/{user_id}/deactivate")
async def deactivate_user(
    request: Request,
    user_id: uuid.UUID,
    principal: Annotated[OperationsPrincipal, Depends(require_operations_key)],
) -> dict[str, object]:
    principal.require_unrestricted_access()
    async with SessionFactory() as session:
        try:
            record = await UserService(session).deactivate(user_id)
        except CredentialError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        if (
            principal.organization_id is not None
            and record.organization_id != principal.organization_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="operational user not found",
            )
        await AuditEventRepository(session).record(
            request,
            action="users.deactivate",
            resource_type="operational_user",
            resource_id=str(record.id),
            outcome="SUCCEEDED",
            details=_organization_details(record),
        )
        await session.commit()
    return _user_view(record)
