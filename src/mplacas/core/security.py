from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Header, HTTPException, Request, status

from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE
from mplacas.core.config import get_settings


class OperationsRole(StrEnum):
    ADMIN = "ADMIN"
    READ = "READ"


@dataclass(frozen=True, slots=True)
class OperationsPrincipal:
    role: OperationsRole
    credential_id: str
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE

    def can_read(self) -> bool:
        return self.role in {OperationsRole.ADMIN, OperationsRole.READ}

    def can_admin(self) -> bool:
        return self.role is OperationsRole.ADMIN

    def require_plant_access(self, plant_id: uuid.UUID) -> None:
        if not self.plant_scope.allows(plant_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="plant not found",
            )

    def require_unrestricted_access(self) -> None:
        if self.plant_scope.is_restricted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="operational credential is restricted to plant resources",
            )


def validate_operations_key(provided: str | None, configured: str | None) -> None:
    """Fail closed when the operational API key is absent or invalid."""
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="operational authentication is not configured",
        )
    if provided is None or not hmac.compare_digest(provided, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid operational credential",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def _secret_value(secret) -> str | None:
    return secret.get_secret_value() if secret else None


def _credential_id(*, role: OperationsRole, secret: str) -> str:
    fingerprint = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]
    return f"operations:{role.value.lower()}:{fingerprint}"


def authenticate_operations_key(
    provided: str | None,
    *,
    admin_key: str | None,
    read_key: str | None = None,
    read_plant_ids: frozenset[uuid.UUID] | None = None,
    require_admin: bool = False,
) -> OperationsPrincipal:
    if not admin_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="operational authentication is not configured",
        )
    if provided is not None and hmac.compare_digest(provided, admin_key):
        return OperationsPrincipal(
            role=OperationsRole.ADMIN,
            credential_id=_credential_id(role=OperationsRole.ADMIN, secret=admin_key),
        )
    if (
        not require_admin
        and read_key
        and provided is not None
        and hmac.compare_digest(provided, read_key)
    ):
        return OperationsPrincipal(
            role=OperationsRole.READ,
            credential_id=_credential_id(role=OperationsRole.READ, secret=read_key),
            plant_scope=(
                PlantScope.restricted(read_plant_ids)
                if read_plant_ids is not None
                else UNRESTRICTED_PLANT_SCOPE
            ),
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid operational credential",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def _resolve_persisted_credential(
    provided: str,
    *,
    require_admin: bool,
) -> OperationsPrincipal | None:
    from mplacas.credentials.service import CredentialService
    from mplacas.db.session import SessionFactory

    settings = get_settings()
    pepper = settings.credential_pepper.get_secret_value() if settings.credential_pepper else ""
    async with SessionFactory() as session:
        principal = await CredentialService(session, pepper=pepper).resolve(provided)
    if principal is None:
        return None
    if require_admin and not principal.can_admin():
        return None
    return principal


async def _authenticate_with_fallback(
    provided: str | None,
    *,
    require_admin: bool,
) -> OperationsPrincipal:
    settings = get_settings()
    try:
        return authenticate_operations_key(
            provided,
            admin_key=_secret_value(settings.operations_api_key),
            read_key=None if require_admin else _secret_value(settings.operations_read_api_key),
            read_plant_ids=None if require_admin else settings.operations_read_plant_id_set,
            require_admin=require_admin,
        )
    except HTTPException as exc:
        if exc.status_code != status.HTTP_401_UNAUTHORIZED or provided is None:
            raise
        persisted = await _resolve_persisted_credential(
            provided,
            require_admin=require_admin,
        )
        if persisted is None:
            raise
        return persisted


async def require_operations_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> OperationsPrincipal:
    principal = await _authenticate_with_fallback(x_api_key, require_admin=True)
    request.state.operations_principal = principal
    return principal


async def require_operations_read(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> OperationsPrincipal:
    principal = await _authenticate_with_fallback(x_api_key, require_admin=False)
    request.state.operations_principal = principal
    return principal
