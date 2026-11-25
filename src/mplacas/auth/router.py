"""HTTP layer for ``/auth``.

Credential checks live in ``auth.service``; sessions and rate limiting in
``auth.session_service``. The router keeps the transaction boundary on
purpose: a failed attempt is committed *before* the 401/400 is raised, so the
rate-limit counter survives the error response.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.audit.repository import AuditEventRepository
from mplacas.auth.password import hash_password
from mplacas.auth.service import (
    invitation_rate_key,
    load_active_user,
    verify_candidate_password,
)
from mplacas.auth.session_service import (
    AuthSessionService,
    IssuedRefreshSession,
    LoginRateLimitService,
)
from mplacas.core.client_ip import resolve_client_ip
from mplacas.core.config import Settings, get_settings
from mplacas.core.jwt import (
    JwtError,
    decode_token,
    encode_access_token,
)
from mplacas.core.security import OperationsRole
from mplacas.credentials.service import CredentialError, UserService
from mplacas.db.session import SessionFactory
from mplacas.core.tenancy import ReadPrincipal, is_platform_operator
from mplacas.credentials.db_models import OperationalUserRecord
from mplacas.db.tenant_context import set_platform_context, set_principal_context
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_db_models import (
    PURPOSE_INVITE,
    PURPOSE_RESET,
    UserInvitationRecord,
)
from mplacas.auth.db_models import AuthSessionRecord
from mplacas.organizations.invitation_service import (
    InvitationConsumeError,
    InvitationService,
)

router = APIRouter(prefix="/auth", tags=["auth"])
_MIN_INVITATION_PASSWORD_LENGTH = 12

# ADR-102 — cookie first-party do refresh token. O prefixo ``__Secure-`` faz o
# navegador recusar o cookie se ele chegar sem ``Secure`` ou por HTTP.
REFRESH_COOKIE_NAME = "__Secure-mplacas_rt"
# Pedidos autenticados pelo cookie precisam deste cabeçalho (valor exato) E de
# um ``Origin`` permitido. Um formulário de outro site não consegue mandar
# cabeçalho customizado, e um ``fetch`` de outro site com ele cai no preflight
# CORS, que só libera as origens configuradas.
AUTH_REQUEST_HEADER = "X-Mplacas-Auth"
_AUTH_REQUEST_HEADER_VALUE = "1"

# Usado quando o endpoint é chamado direto (testes antigos chamam
# ``logout(body, session)``): pedido vazio, sem cookie nem cabeçalhos — ou
# seja, o fluxo de refresh token no corpo, exatamente como antes.
_NO_HTTP_REQUEST = Request({"type": "http", "method": "POST", "path": "/", "headers": []})


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    # Transitório (ADR-102): o corpo só é necessário enquanto o frontend não
    # usa o cookie. Sem corpo, o refresh lê o cookie.
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
    # ADR-095: "INVITE" (criar a senha) ou "RESET" (redefinir o acesso).
    purpose: str = PURPOSE_INVITE


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


def _invalid_refresh_token(*, clear_cookie: str | None = None) -> HTTPException:
    headers = {"WWW-Authenticate": "Bearer"}
    if clear_cookie is not None:
        headers["Set-Cookie"] = clear_cookie
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or expired refresh token",
        headers=headers,
    )


def _forbidden_auth_origin() -> HTTPException:
    # Mesma resposta para cabeçalho ausente, Origin ausente ou Origin errado:
    # não ajuda quem está sondando qual das regras falhou.
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="request origin not allowed",
    )


def _normalize_origin(value: str) -> str:
    return value.strip().rstrip("/").lower()


def _origin_allowed(origin: str, settings: Settings) -> bool:
    allowed = {_normalize_origin(item) for item in settings.cors_allowed_origin_list}
    return _normalize_origin(origin) in allowed


def _require_cookie_request_guard(request: Request, settings: Settings) -> None:
    """Defesa CSRF de pedido autenticado pelo cookie (refresh/logout).

    Exige as duas coisas: ``X-Mplacas-Auth: 1`` e ``Origin`` presente e igual
    a uma origem de ``MPLACAS_CORS_ALLOWED_ORIGINS``. Lista vazia → nada passa
    (falha fechada).
    """
    if request.headers.get(AUTH_REQUEST_HEADER) != _AUTH_REQUEST_HEADER_VALUE:
        raise _forbidden_auth_origin()
    origin = request.headers.get("origin")
    if origin is None or not _origin_allowed(origin, settings):
        raise _forbidden_auth_origin()


def _require_allowed_origin_if_present(request: Request, settings: Settings) -> None:
    """Defesa contra login-CSRF em quem ABRE sessão (login, aceite de convite).

    Navegador sempre manda ``Origin`` em POST cruzado (``fetch`` ou formulário),
    então um site de terceiros que tente logar a vítima na conta do atacante é
    barrado aqui. Sem ``Origin`` (cliente servidor-a-servidor, testes) segue
    como antes: não é um navegador, logo não há vítima de CSRF. ``Origin: null``
    conta como presente e é recusado.
    """
    origin = request.headers.get("origin")
    if origin is not None and not _origin_allowed(origin, settings):
        raise _forbidden_auth_origin()


def _refresh_cookie_from(request: Request, settings: Settings) -> str | None:
    if not settings.auth_cookie_enabled:
        return None
    value = request.cookies.get(REFRESH_COOKIE_NAME)
    return value or None


def _set_refresh_cookie(
    response: Response, issued: IssuedRefreshSession, settings: Settings
) -> None:
    if not settings.auth_cookie_enabled:
        return
    remaining = issued.expires_at - datetime.now(UTC)
    max_age = max(0, int(remaining.total_seconds()))
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        issued.token,
        max_age=max_age,
        path=settings.auth_cookie_path,
        secure=True,
        httponly=True,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=settings.auth_cookie_path,
        secure=True,
        httponly=True,
        samesite="strict",
    )


def _clear_refresh_cookie_header(settings: Settings) -> str:
    scratch = Response()
    _clear_refresh_cookie(scratch, settings)
    return scratch.headers["set-cookie"]


def _session_ttl_kwargs(settings: Settings) -> dict[str, int]:
    return {
        "ttl_seconds": settings.jwt_refresh_ttl_seconds,
        "absolute_max_seconds": settings.auth_session_max_age_seconds,
    }


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
    client_host = resolve_client_ip(request, settings)
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
    response: Response,
    body: LoginRequest,
    session: AsyncSession = Depends(_get_session),
) -> TokenResponse:
    settings = get_settings()
    _require_jwt_configured(settings)
    _require_allowed_origin_if_present(request, settings)

    rate_limit = LoginRateLimitService(session)
    client_host = resolve_client_ip(request, settings)
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
    issued = await AuthSessionService(session).create_session(
        user_id=user.id,
        organization_id=user.organization_id,
        **_session_ttl_kwargs(settings),
    )
    await session.commit()

    _set_refresh_cookie(response, issued, settings)
    return TokenResponse(
        access_token=encode_access_token(user.id, user.organization_id, user.role),
        # Transitório (ADR-102): sai do corpo quando o frontend usar o cookie.
        refresh_token=issued.token,
    )


@router.post("/refresh", response_model=AccessTokenResponse, status_code=status.HTTP_200_OK)
async def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    session: AsyncSession = Depends(_get_session),
) -> AccessTokenResponse:
    """Rotaciona o refresh token. Cookie primeiro; corpo como fallback.

    Com cookie presente, ele é a credencial — o corpo é ignorado — e a defesa
    CSRF é obrigatória. Sem cookie, o fluxo do corpo segue idêntico ao de
    antes do ADR-102 (sem exigir cabeçalho nem Origin).
    """
    settings = get_settings()
    _require_jwt_configured(settings)

    cookie_token = _refresh_cookie_from(request, settings)
    if cookie_token is not None:
        _require_cookie_request_guard(request, settings)
        presented = cookie_token
        clear_on_failure: str | None = _clear_refresh_cookie_header(settings)
    elif body is not None:
        presented = body.refresh_token
        clear_on_failure = None
    else:
        raise _invalid_refresh_token()

    try:
        claims = decode_token(presented, expected_type="refresh")
    except JwtError as exc:
        raise _invalid_refresh_token(clear_cookie=clear_on_failure) from exc

    user = await load_active_user(
        session,
        user_id=claims.sub,
        organization_id=claims.org_id,
    )
    if user is None:
        raise _invalid_refresh_token(clear_cookie=clear_on_failure)

    issued = await AuthSessionService(session).rotate_session(
        token=presented,
        claims=claims,
        reuse_grace_seconds=settings.auth_refresh_reuse_grace_seconds,
        **_session_ttl_kwargs(settings),
    )
    # Commit também na falha: a revogação da família (replay, teto absoluto)
    # escrita por ``rotate_session`` não pode se perder num rollback.
    await session.commit()
    if issued is None:
        raise _invalid_refresh_token(clear_cookie=clear_on_failure)

    _set_refresh_cookie(response, issued, settings)
    return AccessTokenResponse(
        access_token=encode_access_token(claims.sub, claims.org_id, user.role),
        # Transitório (ADR-102): sai do corpo quando o frontend usar o cookie.
        refresh_token=issued.token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest | None = None,
    session: AsyncSession = Depends(_get_session),
    request: Request = _NO_HTTP_REQUEST,
) -> Response:
    """Revoke the presented refresh session without exposing token validity.

    ADR-102: com cookie, exige a mesma defesa CSRF do refresh (senão 403, sem
    revogar nem apagar — um site de terceiros não consegue deslogar ninguém);
    passando nela, revoga e apaga o cookie. Responde 204 para qualquer token
    (válido, inválido, expirado, já revogado). O fluxo do corpo, sem cookie,
    segue idêntico.
    """
    settings = get_settings()
    cookie_token = _refresh_cookie_from(request, settings)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    if cookie_token is not None:
        _require_cookie_request_guard(request, settings)
        _clear_refresh_cookie(response, settings)
        presented: str | None = cookie_token
    else:
        presented = body.refresh_token if body is not None else None
    if presented is None:
        return response

    try:
        claims = decode_token(presented, expected_type="refresh")
    except JwtError:
        return response

    if claims.jti is not None:
        await AuthSessionService(session).revoke(session_id=claims.jti)
        await session.commit()
    return response


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
        purpose=invitation.purpose,
    )


@router.post(
    "/invitations/accept",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def accept_invitation(
    request: Request,
    response: Response,
    body: InvitationAcceptRequest,
    session: AsyncSession = Depends(_get_session),
) -> TokenResponse:
    settings = get_settings()
    _require_jwt_configured(settings)
    # Aceitar convite abre sessão: mesma regra de Origin do login (ADR-102).
    _require_allowed_origin_if_present(request, settings)

    invitation = await _consume_invitation_rate_limited(
        session, request, token=body.token, settings=settings
    )

    if invitation.purpose == PURPOSE_RESET:
        return await _accept_access_reset(
            session, request, response, invitation, body.password, settings
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

    issued = await AuthSessionService(session).create_session(
        user_id=user.id,
        organization_id=user.organization_id,
        **_session_ttl_kwargs(settings),
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

    _set_refresh_cookie(response, issued, settings)
    return TokenResponse(
        access_token=encode_access_token(user.id, user.organization_id, user.role),
        refresh_token=issued.token,
    )


async def _accept_access_reset(
    session: AsyncSession,
    request: Request,
    response: Response,
    invitation: UserInvitationRecord,
    password: str,
    settings: Settings,
) -> TokenResponse:
    """Redefinição de acesso (ADR-095): troca a senha do usuário que já existe.

    Encerra todas as sessões abertas desse usuário antes de abrir a nova; a
    mesma resposta "convite inválido" de sempre cobre usuário inexistente ou
    desativado, sem revelar qual foi o caso.
    """
    user = await session.scalar(
        select(OperationalUserRecord).where(
            OperationalUserRecord.organization_id == invitation.organization_id,
            OperationalUserRecord.name == invitation.username,
            OperationalUserRecord.active.is_(True),
        )
    )
    if user is None:
        raise _invalid_invitation()
    accepted = await InvitationService(session).mark_accepted(
        invitation_id=invitation.id, accepted_user_id=user.id
    )
    if not accepted:
        raise _invalid_invitation()
    user.password_hash = hash_password(password)
    await session.execute(
        update(AuthSessionRecord)
        .where(AuthSessionRecord.user_id == user.id, AuthSessionRecord.active.is_(True))
        .values(active=False, revoked_at=datetime.now(UTC))
    )
    issued = await AuthSessionService(session).create_session(
        user_id=user.id,
        organization_id=user.organization_id,
        **_session_ttl_kwargs(settings),
    )
    await AuditEventRepository(session).record(
        request,
        organization_id=invitation.organization_id,
        action="invitations.access_reset",
        resource_type="user_invitation",
        resource_id=str(invitation.id),
        outcome="SUCCEEDED",
        details={"username": user.name, "user_id": str(user.id)},
    )
    await session.commit()
    # Todas as sessões antigas caíram acima; o cookie novo substitui o velho.
    _set_refresh_cookie(response, issued, settings)
    return TokenResponse(
        access_token=encode_access_token(user.id, user.organization_id, user.role),
        refresh_token=issued.token,
    )


class MeResponse(BaseModel):
    username: str | None
    role: str
    organization_id: str | None
    organization_name: str | None
    is_platform_operator: bool


@router.get("/me", response_model=MeResponse)
async def me(principal: ReadPrincipal) -> MeResponse:
    """Quem está logado (ADR-093): a tela mostra "Clientes" só ao operador e
    esconde escrita de quem não é ADMIN. Nunca devolve segredo nem token."""
    username: str | None = None
    organization_name: str | None = None
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        if principal.credential_id.startswith("user:"):
            try:
                user_id = uuid.UUID(principal.credential_id.removeprefix("user:"))
            except ValueError:
                user_id = None
            if user_id is not None:
                user = await session.get(OperationalUserRecord, user_id)
                username = user.name if user is not None else None
        if principal.organization_id is not None:
            organization = await session.get(OrganizationRecord, principal.organization_id)
            organization_name = organization.name if organization is not None else None
    return MeResponse(
        username=username,
        role=principal.role.value,
        organization_id=str(principal.organization_id) if principal.organization_id else None,
        organization_name=organization_name,
        is_platform_operator=is_platform_operator(principal),
    )
