from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt

from mplacas.core.config import get_settings

_ISSUER = "mplacas"
_ALGORITHM = "HS256"


class JwtError(Exception):
    """Raised when a JWT is invalid, expired, or has wrong type/issuer."""


@dataclass(frozen=True, slots=True)
class JwtClaims:
    sub: uuid.UUID
    org_id: uuid.UUID
    role: str
    type: str
    jti: uuid.UUID | None = None


def _settings():
    return get_settings()


def _secret() -> str:
    settings = _settings()
    if not settings.jwt_configured:
        raise JwtError("JWT is not configured")
    assert settings.jwt_secret is not None
    return settings.jwt_secret.get_secret_value()


def _encoding_headers() -> dict[str, str]:
    return {"kid": _settings().jwt_key_id}


def _verification_secret(token: str) -> str:
    settings = _settings()
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise JwtError("invalid token header") from exc
    if header.get("alg") != _ALGORITHM:
        raise JwtError("token algorithm is not allowed")
    key_id = header.get("kid")
    if key_id == settings.jwt_key_id:
        return _secret()
    if (
        settings.jwt_previous_secret is not None
        and key_id == settings.jwt_previous_key_id
    ):
        return settings.jwt_previous_secret.get_secret_value()
    raise JwtError("unknown token key id")


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
        "aud": settings.jwt_audience,
        "type": "access",
    }
    return jwt.encode(
        payload,
        _secret(),
        algorithm=_ALGORITHM,
        headers=_encoding_headers(),
    )


def encode_refresh_token(
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    *,
    jti: uuid.UUID | None = None,
) -> str:
    settings = _settings()
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "iat": now,
        "exp": now + settings.jwt_refresh_ttl_seconds,
        "iss": _ISSUER,
        "aud": settings.jwt_audience,
        "type": "refresh",
    }
    if jti is not None:
        payload["jti"] = str(jti)
    return jwt.encode(
        payload,
        _secret(),
        algorithm=_ALGORITHM,
        headers=_encoding_headers(),
    )


def decode_token(token: str, *, expected_type: str) -> JwtClaims:
    settings = _settings()
    try:
        payload = jwt.decode(
            token,
            _verification_secret(token),
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            audience=settings.jwt_audience,
            options={
                "require": ["sub", "exp", "iat", "iss", "aud", "type", "org_id"]
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise JwtError("token expired") from exc
    except jwt.InvalidIssuerError as exc:
        raise JwtError("invalid issuer") from exc
    except jwt.PyJWTError as exc:
        raise JwtError(f"invalid token: {exc}") from exc

    if payload.get("type") != expected_type:
        raise JwtError(f"expected token type '{expected_type}'")
    if expected_type == "refresh" and payload.get("jti") is None:
        raise JwtError("refresh token is missing jti")
    role = payload.get("role", "READ")
    if expected_type == "access" and role not in {"ADMIN", "READ"}:
        raise JwtError("invalid access token role")

    try:
        raw_jti = payload.get("jti")
        return JwtClaims(
            sub=uuid.UUID(payload["sub"]),
            org_id=uuid.UUID(payload["org_id"]),
            role=role,
            type=payload["type"],
            jti=uuid.UUID(raw_jti) if raw_jti is not None else None,
        )
    except (ValueError, KeyError) as exc:
        raise JwtError(f"malformed claims: {exc}") from exc
