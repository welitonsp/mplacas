from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.audit.repository import AuditEventRepository
from mplacas.auth.password import hash_password, verify_password
from mplacas.auth.session_service import AuthSessionService, LoginRateLimitService
from mplacas.core.config import get_settings
from mplacas.core.jwt import (
    JwtError,
    decode_token,
    encode_access_token,
)
from mplacas.core.security import OperationsRole
from mplacas.credentials.db_models import OperationalUserRecord
from mplacas.credentials.service import CredentialError, UserService
from mplacas.db.session import SessionFactory
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_service import (
    InvitationConsumeError,
    InvitationService,
)

router = APIRouter(prefix="/auth", tags=["auth"])
_DUMMY_PASSWORD_HASH = hash_password("mplacas-invalid-user-dummy-password")
_MIN_INVITATION_PASSWORD_LENGTH = 12


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class InvitationInspectRequest(BaseModel):
    token: str


class InvitationInspectResponse(BaseModel):
    organization_name: str
    username: str
    role: str
    expires_at: datetime


class InvitationAcceptRequest(BaseModel):
    token: str
    # No composition rule (uppercase/digit/symbol) by design — only a length
    # floor, per the project's password policy decision for this flow.
    password: str = Field(min_length=_MIN_INVITATION_PASSWORD_LENGTH, max_length=200)


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


def _invalid_invitation() -> HTTPException:
    # Deliberately identical for every failure mode (not found, expired,
    # already accepted, revoked, organization deactivated, lost race against
    # a concurrent accept): see ``InvitationConsumeError`` docstring for why
    # the reason is never surfaced to an unauthenticated caller.
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="invalid or expired invitation",
    )


def _invitation_rate_key(*, token: str, client_host: str | None) -> str:
    # The token itself must never be logged or used verbatim as a rate-limit
    # key (it would defeat hashing at rest in ``LoginRateLimitRecord``); a
    # truncated SHA-256 digest plays the same role ``username`` plays for
    # ``/auth/login``, reusing ``LoginRateLimitService.key_for`` as-is rather
    # than inventing a parallel rate-limit mechanism.
    token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return LoginRateLimitService.key_for(username=token_digest, client_host=client_host)


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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    session: AsyncSession = Depends(_get_session),
) -> Response:
    """Revoke the presented refresh session without exposing token validity."""

    try:
        claims = decode_token(body.refresh_token, expected_type="refresh")
    except JwtError:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if claims.jti is not None:
        await AuthSessionService(session).revoke(session_id=claims.jti)
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/invitations/inspect",
    response_model=InvitationInspectResponse,
    status_code=status.HTTP_200_OK,
)
async def inspect_invitation(
    request: Request,
    body: InvitationInspectRequest,
    session: AsyncSession = Depends(_get_session),
) -> InvitationInspectResponse:
    # POST, not ``GET /auth/invitations/{token}``: a token in the path would
    # land in access logs, browser history and the ``Referer`` header. Same
    # reasoning that already puts the refresh token in ``RefreshRequest``'s
    # body instead of a path/query parameter.
    settings = get_settings()
    rate_limit = LoginRateLimitService(session)
    client_host = request.client.host if request.client else None
    rate_key = _invitation_rate_key(token=body.token, client_host=client_host)
    if await rate_limit.is_locked(rate_key):
        raise _rate_limited()

    try:
        invitation = await InvitationService(session).consume(token=body.token)
    except InvitationConsumeError as exc:
        await rate_limit.record_failure(
            rate_key,
            max_attempts=settings.auth_login_max_attempts,
            window_seconds=settings.auth_login_window_seconds,
            lockout_seconds=settings.auth_login_lockout_seconds,
        )
        await session.commit()
        raise _invalid_invitation() from exc

    await rate_limit.clear(rate_key)
    organization = await session.get(OrganizationRecord, invitation.organization_id)
    assert organization is not None
    await session.commit()

    return InvitationInspectResponse(
        organization_name=organization.name,
        username=invitation.username,
        role=invitation.role,
        expires_at=invitation.expires_at,
    )


@router.post(
    "/invitations/accept",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def accept_invitation(
    request: Request,
    body: InvitationAcceptRequest,
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
    rate_key = _invitation_rate_key(token=body.token, client_host=client_host)
    if await rate_limit.is_locked(rate_key):
        raise _rate_limited()

    try:
        invitation = await InvitationService(session).consume(token=body.token)
    except InvitationConsumeError as exc:
        await rate_limit.record_failure(
            rate_key,
            max_attempts=settings.auth_login_max_attempts,
            window_seconds=settings.auth_login_window_seconds,
            lockout_seconds=settings.auth_login_lockout_seconds,
        )
        await session.commit()
        raise _invalid_invitation() from exc

    await rate_limit.clear(rate_key)

    try:
        user = await UserService(session).create(
            name=invitation.username,
            organization_id=invitation.organization_id,
            role=OperationsRole(invitation.role),
            password_hash=hash_password(body.password),
        )
    except CredentialError as exc:
        # E.g. the invited username already belongs to another operational
        # user. The invitation is never marked accepted in this branch (we
        # never reach ``mark_accepted``), and nothing here is committed, so
        # closing the session below rolls back the failed user insert too —
        # same "discard without commit" convention used for every other
        # domain-error branch in this router/``organizations.router``.
        raise _invalid_invitation() from exc

    accepted = await InvitationService(session).mark_accepted(
        invitation_id=invitation.id,
        accepted_user_id=user.id,
    )
    if not accepted:
        # Lost a race against a concurrent ``accept`` for the same token
        # between ``consume`` above and ``mark_accepted`` here: some other
        # request already marked this invitation accepted in between. The
        # operational user row just inserted above must not survive as an
        # orphan with no valid invitation behind it, so — same as the
        # ``CredentialError`` branch — nothing is committed and the whole
        # transaction (including that insert) is rolled back on session
        # close.
        raise _invalid_invitation()

    refresh_token = await AuthSessionService(session).create(
        user_id=user.id,
        organization_id=user.organization_id,
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
    )

    await AuditEventRepository(session).record(
        request,
        action="invitations.accept",
        resource_type="user_invitation",
        resource_id=str(invitation.id),
        outcome="SUCCEEDED",
        # The actor is anonymous until this point; the record is written
        # only now that the accepting user exists, identified in ``details``
        # rather than as ``actor_*`` (those columns describe the caller's
        # pre-existing credential/role, which does not apply here).
        details={"username": user.name, "accepted_user_id": str(user.id)},
    )
    await session.commit()

    return TokenResponse(
        access_token=encode_access_token(user.id, user.organization_id, user.role),
        refresh_token=refresh_token,
    )
