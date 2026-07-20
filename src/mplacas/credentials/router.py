from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from mplacas.audit.repository import AuditEventRepository
from mplacas.core.security import (
    OperationsPrincipal,
    OperationsRole,
    require_operations_key,
)
from mplacas.credentials.db_models import ApiCredentialRecord
from mplacas.credentials.service import CredentialError, CredentialService
from mplacas.db.session import SessionFactory

router = APIRouter(
    prefix="/operations/credentials",
    tags=["operational"],
)


class CredentialCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role: OperationsRole
    plant_ids: list[uuid.UUID] | None = None


def _public_view(record: ApiCredentialRecord) -> dict[str, object]:
    return {
        "id": str(record.id),
        "name": record.name,
        "role": record.role,
        "plant_ids": record.plant_ids,
        "active": record.active,
        "created_at": record.created_at,
        "revoked_at": record.revoked_at,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_credential(
    request: Request,
    payload: CredentialCreateRequest,
    principal: Annotated[OperationsPrincipal, Depends(require_operations_key)],
) -> dict[str, object]:
    principal.require_unrestricted_access()
    async with SessionFactory() as session:
        service = CredentialService(session)
        try:
            record, secret = await service.create(
                name=payload.name,
                role=payload.role,
                plant_ids=(
                    frozenset(payload.plant_ids) if payload.plant_ids is not None else None
                ),
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
            outcome="success",
            details={
                "name": record.name,
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
        records = await CredentialService(session).list_credentials()
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
        service = CredentialService(session)
        try:
            record = await service.revoke(credential_id)
        except CredentialError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        await AuditEventRepository(session).record(
            request,
            action="credentials.revoke",
            resource_type="api_credential",
            resource_id=str(record.id),
            outcome="success",
            details={"name": record.name},
        )
        await session.commit()
    return _public_view(record)
