from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt

from mplacas.core.config import get_settings

_ISSUER = "mplacas"


class JwtError(Exception):
    """Raised when a JWT is invalid, expired, or has wrong type/issuer."""


@dataclass(frozen=True, slots=True)
class JwtClaims:
    sub: uuid.UUID
    org_id: uuid.UUID
    role: str
    type: str


def _settings():
    return get_settings()


def _secret() -> str:
    settings = _settings()
    if not settings.jwt_configured:
        raise JwtError("JWT is not configured")
    assert settings.jwt_secret is not None
    return settings.jwt_secret.get_secret_value()


def encode_access_token(
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    role: str,
) -> str:
    settings = _settings()
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "role": role,
        "iat": now,
        "exp": now + settings.jwt_access_ttl_seconds,
        "iss": _ISSUER,
        "type": "access",
    }
    return jwt.encode(payload, _secret(), algorithm=settings.jwt_algorithm)


def encode_refresh_token(user_id: uuid.UUID, org_id: uuid.UUID) -> str:
    settings = _settings()
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "iat": now,
        "exp": now + settings.jwt_refresh_ttl_seconds,
        "iss": _ISSUER,
        "type": "refresh",
    }
    return jwt.encode(payload, _secret(), algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, expected_type: str) -> JwtClaims:
    settings = _settings()
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[settings.jwt_algorithm],
            issuer=_ISSUER,
            options={"require": ["sub", "exp", "iat", "iss", "type", "org_id"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise JwtError("token expired") from exc
    except jwt.InvalidIssuerError as exc:
        raise JwtError("invalid issuer") from exc
    except jwt.PyJWTError as exc:
        raise JwtError(f"invalid token: {exc}") from exc

    if payload.get("type") != expected_type:
        raise JwtError(f"expected token type '{expected_type}'")

    try:
        return JwtClaims(
            sub=uuid.UUID(payload["sub"]),
            org_id=uuid.UUID(payload["org_id"]),
            role=payload.get("role", "READ"),
            type=payload["type"],
        )
    except (ValueError, KeyError) as exc:
        raise JwtError(f"malformed claims: {exc}") from exc
