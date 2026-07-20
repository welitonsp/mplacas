from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.auth.password import verify_password
from mplacas.core.config import get_settings
from mplacas.core.jwt import JwtError, decode_token, encode_access_token, encode_refresh_token
from mplacas.credentials.db_models import OperationalUserRecord
from mplacas.db.session import SessionFactory

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


async def _get_session():
    async with SessionFactory() as session:
        yield session


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(_get_session),
) -> TokenResponse:
    settings = get_settings()
    if not settings.jwt_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT authentication is not configured",
        )

    result = await session.execute(
        select(OperationalUserRecord).where(
            OperationalUserRecord.name == body.username,
            OperationalUserRecord.active.is_(True),
        )
    )
    user: OperationalUserRecord | None = result.scalar_one_or_none()

    _INVALID = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Constant-time rejection — same code path whether user exists or not.
    if user is None or user.password_hash is None:
        raise _INVALID
    if not verify_password(body.password, user.password_hash):
        raise _INVALID

    if user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user has no associated organization",
        )

    org_id: uuid.UUID = user.organization_id
    return TokenResponse(
        access_token=encode_access_token(user.id, org_id, "ADMIN"),
        refresh_token=encode_refresh_token(user.id, org_id),
    )


@router.post("/refresh", response_model=AccessTokenResponse, status_code=status.HTTP_200_OK)
async def refresh(body: RefreshRequest) -> AccessTokenResponse:
    settings = get_settings()
    if not settings.jwt_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT authentication is not configured",
        )

    try:
        claims = decode_token(body.refresh_token, expected_type="refresh")
    except JwtError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return AccessTokenResponse(
        access_token=encode_access_token(claims.sub, claims.org_id, "ADMIN"),
    )
