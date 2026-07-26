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
from mplacas.organizations.db_models import OrganizationRecord

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


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _load_active_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None = None,
    username: str | None = None,
    organization_id: uuid.UUID | None = None,
) -> OperationalUserRecord | None:
    statement = select(OperationalUserRecord).join(
        OrganizationRecord,
        OperationalUserRecord.organization_id == OrganizationRecord.id,
    )
    if user_id is not None:
        statement = statement.where(OperationalUserRecord.id == user_id)
    if username is not None:
        statement = statement.where(OperationalUserRecord.name == username)
    if organization_id is not None:
        statement = statement.where(OperationalUserRecord.organization_id == organization_id)
    statement = statement.where(
        OperationalUserRecord.active.is_(True),
        OrganizationRecord.active.is_(True),
    )
    return await session.scalar(statement)


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

    user = await _load_active_user(session, username=body.username)

    # Invalid responses intentionally use the same public message.
    if user is None or user.password_hash is None:
        raise _invalid_credentials()
    if not verify_password(body.password, user.password_hash):
        raise _invalid_credentials()

    org_id: uuid.UUID = user.organization_id
    return TokenResponse(
        access_token=encode_access_token(user.id, org_id, "ADMIN"),
        refresh_token=encode_refresh_token(user.id, org_id),
    )


@router.post("/refresh", response_model=AccessTokenResponse, status_code=status.HTTP_200_OK)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(_get_session),
) -> AccessTokenResponse:
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

    user = await _load_active_user(
        session,
        user_id=claims.sub,
        organization_id=claims.org_id,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AccessTokenResponse(
        access_token=encode_access_token(claims.sub, claims.org_id, "ADMIN"),
    )
