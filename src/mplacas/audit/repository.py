from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.audit.db_models import AuditEventRecord


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


def _actor(request: Request) -> tuple[str, str]:
    principal = getattr(request.state, "operations_principal", None)
    if principal is None:
        return "UNKNOWN", "unknown"
    return principal.role.value, principal.credential_id


def _organization_id(request: Request) -> uuid.UUID | None:
    principal = getattr(request.state, "operations_principal", None)
    value = getattr(principal, "organization_id", None)
    return value if isinstance(value, uuid.UUID) else None


class AuditEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        request: Request,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None,
        outcome: str,
        details: dict[str, Any] | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> AuditEventRecord:
        actor_role, actor_credential_id = _actor(request)
        event = AuditEventRecord(
            organization_id=organization_id or _organization_id(request),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            actor_role=actor_role,
            actor_credential_id=actor_credential_id,
            request_id=_request_id(request),
            details=details or {},
        )
        self._session.add(event)
        await self._session.flush()
        return event
