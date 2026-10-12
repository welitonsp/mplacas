"""HTTP layer for ``/auth``.

Credential checks live in ``auth.service``; sessions and rate limiting in
``auth.session_service``. The router keeps the transaction boundary on
purpose: a failed attempt is committed *before* the 401/400 is raised, so the
rate-limit counter survives the error response.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.audit.repository import AuditEventRepository
from mplacas.auth.password import hash_password
from mplacas.auth.service import (
    invitation_rate_key,
    load_active_user,
    verify_candidate_password,
)
from mplacas.auth.session_service import AuthSessionService, LoginRateLimitService
from mplacas.core.config import Settings, get_settings
from mplacas.core.jwt import (
    JwtError,
    decode_token,
    encode_access_token,
)
from mplacas.core.security import OperationsRole
from mplacas.credentials.service import CredentialError, UserService
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_platform_context
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_db_models import UserInvitationRecord
from mplacas.organizations.invitation_service import (
    InvitationConsumeError,
    InvitationService,
)

router = APIRouter(prefix="/auth", tags=["auth"])
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
        await set_platform_context(session)
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


def _require_jwt_configured(settings: Settings) -> None:
    if not settings.jwt_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT authentication is not configured",
        )


def _invalid_refresh_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _consume_invitation_rate_limited(
    session: AsyncSession,
    request: Request,
    *,
    token: str,
    settings: Settings,
) -> UserInvitationRecord:
    """Consume an invitation token under the same lockout as ``/auth/login``.

    On failure the attempt is recorded and **committed** before raising, so
    the counter survives the 400; on success the counter is cleared (not yet
    committed — the caller commits with the rest of its work).
    """
    rate_limit = LoginRateLimitService(session)
    client_host = request.client.host if request.client else None
    rate_key = invitation_rate_key(token=token, client_host=client_host)
    if await rate_limit.is_locked(rate_key):
        raise _rate_limited()

    try:
        invitation = await InvitationService(session).consume(token=token)
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
    return invitation


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    request: Request,
    body: LoginRequest,
    session: AsyncSession = Depends(_get_session),
) -> TokenResponse:
    settings = get_settings()
    _require_jwt_configured(settings)

    rate_limit = LoginRateLimitService(session)
    client_host = request.client.host if request.client else None
    rate_key = LoginRateLimitService.key_for(
        username=body.username,
        client_host=client_host,
    )
    if await rate_limit.is_locked(rate_key):
        raise _rate_limited()

    user = await load_active_user(session, username=body.username)
    if not verify_candidate_password(supplied_password=body.password, user=user):
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
    _require_jwt_configured(settings)

    try:
        claims = decode_token(body.refresh_token, expected_type="refresh")
    except JwtError as exc:
        raise _invalid_refresh_token() from exc

    user = await load_active_user(
        session,
        user_id=claims.sub,
        organization_id=claims.org_id,
    )
    if user is None:
        raise _invalid_refresh_token()

    new_refresh_token = await AuthSessionService(session).rotate(
        token=body.refresh_token,
        claims=claims,
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
    )
    if new_refresh_token is None:
        raise _invalid_refresh_token()
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
    invitation = await _consume_invitation_rate_limited(
        session, request, token=body.token, settings=get_settings()
    )
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
    _require_jwt_configured(settings)

    invitation = await _consume_invitation_rate_limited(
        session, request, token=body.token, settings=settings
    )

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
        organization_id=invitation.organization_id,
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
