from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from mplacas.core.config import get_settings


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


async def require_operations_key(x_api_key: str | None = Header(default=None)) -> None:
    secret = get_settings().operations_api_key
    configured = secret.get_secret_value() if secret else None
    validate_operations_key(x_api_key, configured)
