from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import Header, HTTPException, Request, status

from mplacas.core.config import get_settings
from mplacas.core.jwt import JwtError, decode_token
from mplacas.core.principal import OperationsPrincipal, OperationsRole
from mplacas.core.tenancy import plant_scope_for_organization
from mplacas.observability.metrics import OUTCOME_SUCCESS, record_operation

logger = logging.getLogger(__name__)

__all__ = [
    "OperationsPrincipal",
    "OperationsRole",
    "authenticate_operations_key",
    "require_operations_key",
    "require_operations_read",
    "validate_operations_key",
]


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


def _warn_static_key_used(
    *,
    role: OperationsRole,
    credential_id: str,
    http_method: str | None,
    http_path: str | None,
) -> None:
    """Emit a deprecation-tracking warning for the static operations API key.

    The static ``OPERATIONS_API_KEY`` bypasses any organization-level
    isolation (it authenticates with ``organization_id`` unset). This does
    not change authentication behavior in any way — it only records usage so
    a safe deprecation timeline can be defined later. Never log the
    credential value itself, only its non-reversible fingerprint id.
    """
    logger.warning(
        "operations_static_key_auth_used",
        extra={
            "operations_role": role.value,
            "credential_id": credential_id,
            "http_method": http_method,
            "http_path": http_path,
        },
    )
    record_operation(
        operation=f"static_key_auth_{role.value.lower()}",
        outcome=OUTCOME_SUCCESS,
        duration_ms=0.0,
    )


def authenticate_operations_key(
    provided: str | None,
    *,
    admin_key: str | None,
    require_admin: bool = False,
    http_method: str | None = None,
    http_path: str | None = None,
) -> OperationsPrincipal:
    """Authenticate against the static admin operations API key.

    ``admin_key`` being unset only means this particular authentication
    method is unavailable — it is not, by itself, a reason to fail closed
    with ``503``. Callers (``_authenticate_with_fallback``) still have the
    persisted-credential store to fall back to, so an unmatched or missing
    static key surfaces as a plain ``401`` here, exactly like a wrong key
    would. ``require_admin`` is accepted for signature symmetry with the
    fallback dependency wiring; only the ``ADMIN`` role static key exists.
    """
    if admin_key and provided is not None and hmac.compare_digest(provided, admin_key):
        credential_id = _credential_id(role=OperationsRole.ADMIN, secret=admin_key)
        _warn_static_key_used(
            role=OperationsRole.ADMIN,
            credential_id=credential_id,
            http_method=http_method,
            http_path=http_path,
        )
        return OperationsPrincipal(
            role=OperationsRole.ADMIN,
            credential_id=credential_id,
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
    from mplacas.db.tenant_context import set_platform_context

    settings = get_settings()
    pepper = (
        settings.credential_pepper.get_secret_value()
        if settings.credential_pepper
        else ""
    )
    async with SessionFactory() as session:
        await set_platform_context(session)
        principal = await CredentialService(session, pepper=pepper).resolve(provided)
    if principal is None:
        return None
    if require_admin and not principal.can_admin():
        return None
    return principal


async def _authenticate_bearer(
    token: str,
    *,
    require_admin: bool,
) -> OperationsPrincipal | None:
    settings = get_settings()
    if not settings.jwt_configured:
        return None
    try:
        claims = decode_token(token, expected_type="access")
    except JwtError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if require_admin and claims.role != OperationsRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required",
        )
    scope = await plant_scope_for_organization(claims.org_id)
    return OperationsPrincipal(
        role=OperationsRole(claims.role),
        credential_id=f"user:{claims.sub}",
        plant_scope=scope,
        organization_id=claims.org_id,
    )


async def _authenticate_with_fallback(
    provided: str | None,
    *,
    require_admin: bool,
    http_method: str | None = None,
    http_path: str | None = None,
) -> OperationsPrincipal:
    settings = get_settings()
    try:
        return authenticate_operations_key(
            provided,
            admin_key=_secret_value(settings.operations_api_key),
            require_admin=require_admin,
            http_method=http_method,
            http_path=http_path,
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
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> OperationsPrincipal:
    if authorization and authorization.startswith("Bearer "):
        principal = await _authenticate_bearer(
            authorization[len("Bearer ") :], require_admin=True
        )
        if principal is not None:
            request.state.operations_principal = principal
            return principal
    principal = await _authenticate_with_fallback(
        x_api_key,
        require_admin=True,
        http_method=request.method,
        http_path=request.url.path,
    )
    request.state.operations_principal = principal
    return principal


async def require_operations_read(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> OperationsPrincipal:
    if authorization and authorization.startswith("Bearer "):
        principal = await _authenticate_bearer(
            authorization[len("Bearer ") :], require_admin=False
        )
        if principal is not None:
            request.state.operations_principal = principal
            return principal
    principal = await _authenticate_with_fallback(
        x_api_key,
        require_admin=False,
        http_method=request.method,
        http_path=request.url.path,
    )
    request.state.operations_principal = principal
    return principal
