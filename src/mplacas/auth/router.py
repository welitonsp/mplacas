from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.auth.password import hash_password, verify_password
from mplacas.auth.session_service import AuthSessionService, LoginRateLimitService
from mplacas.core.config import get_settings
from mplacas.core.jwt import (
    JwtError,
    decode_token,
    encode_access_token,
)
from mplacas.credentials.db_models import OperationalUserRecord
from mplacas.db.session import SessionFactory
from mplacas.organizations.db_models import OrganizationRecord

router = APIRouter(prefix="/auth", tags=["auth"])
_DUMMY_PASSWORD_HASH = hash_password("mplacas-invalid-user-dummy-password")


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
    refresh_token: str
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


def _rate_limited() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="too many failed login attempts; try again later",
    )


async def _load_active_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None = None,
    username: str | None = None,
    organization_id: uuid.UUID | None = None,
) -> OperationalUserRecord | None:
    statement = select(OperationalUserRecord).outerjoin(
        OrganizationRecord,
        OperationalUserRecord.organization_id == OrganizationRecord.id,
    )
    if user_id is not None:
        statement = statement.where(OperationalUserRecord.id == user_id)
    if username is not None:
        statement = statement.where(OperationalUserRecord.name == username)
    if organization_id is not None:
        statement = statement.where(
            OperationalUserRecord.organization_id == organization_id
        )
    statement = statement.where(
        OperationalUserRecord.active.is_(True),
        or_(OrganizationRecord.id.is_(None), OrganizationRecord.active.is_(True)),
    )
    return await session.scalar(statement)


def _verify_candidate_password(
    *,
    supplied_password: str,
    user: OperationalUserRecord | None,
) -> bool:
    if user is None or user.password_hash is None:
        verify_password(supplied_password, _DUMMY_PASSWORD_HASH)
        return False
    return verify_password(supplied_password, user.password_hash)


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    request: Request,
    body: LoginRequest,
    session: AsyncSession = Depends(_get_session),
) -> TokenResponse:
    settings = get_settings()
    if not settings.jwt_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT authentication is not configured",
        )

    rate_limit = LoginRateLimitService(session)
    client_host = request.client.host if request.client else None
    rate_key = LoginRateLimitService.key_for(
        username=body.username,
        client_host=client_host,
    )
    if await rate_limit.is_locked(rate_key):
        raise _rate_limited()

    user = await _load_active_user(session, username=body.username)
    if not _verify_candidate_password(supplied_password=body.password, user=user):
        await rate_limit.record_failure(
            rate_key,
            max_attempts=settings.auth_login_max_attempts,
            window_seconds=settings.auth_login_window_seconds,
            lockout_seconds=settings.auth_login_lockout_seconds,
        )
        await session.commit()
        raise _invalid_credentials()

    assert user is not None
    await rate_limit.clear(rate_key)
    refresh_token = await AuthSessionService(session).create(
        user_id=user.id,
        organization_id=user.organization_id,
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
    )
    await session.commit()

    return TokenResponse(
        access_token=encode_access_token(user.id, user.organization_id, user.role),
        refresh_token=refresh_token,
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

    new_refresh_token = await AuthSessionService(session).rotate(
        token=body.refresh_token,
        claims=claims,
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
    )
    if new_refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    await session.commit()

    return AccessTokenResponse(
        access_token=encode_access_token(claims.sub, claims.org_id, user.role),
        refresh_token=new_refresh_token,
    )
