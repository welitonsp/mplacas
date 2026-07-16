from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Header, HTTPException, Request, status

from mplacas.core.config import get_settings


class OperationsRole(StrEnum):
    ADMIN = "ADMIN"
    READ = "READ"


@dataclass(frozen=True, slots=True)
class OperationsPrincipal:
    role: OperationsRole
    credential_id: str

    def can_read(self) -> bool:
        return self.role in {OperationsRole.ADMIN, OperationsRole.READ}

    def can_admin(self) -> bool:
        return self.role is OperationsRole.ADMIN


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
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid operational credential",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def require_operations_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> OperationsPrincipal:
    settings = get_settings()
    principal = authenticate_operations_key(
        x_api_key,
        admin_key=_secret_value(settings.operations_api_key),
        require_admin=True,
    )
    request.state.operations_principal = principal
    return principal


async def require_operations_read(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> OperationsPrincipal:
    settings = get_settings()
    principal = authenticate_operations_key(
        x_api_key,
        admin_key=_secret_value(settings.operations_api_key),
        read_key=_secret_value(settings.operations_read_api_key),
    )
    request.state.operations_principal = principal
    return principal
