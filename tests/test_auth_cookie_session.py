"""ADR-102 — sessão persistente por cookie first-party via proxy.

Fixa, ponta a ponta (HTTP + SQLite em arquivo), as regras novas:

- todo lugar que abre sessão (login, aceite de convite, redefinição de acesso)
  também grava ``__Secure-mplacas_rt`` com HttpOnly, Secure, SameSite=Strict,
  Path configurável e Max-Age limitado pelo teto absoluto;
- refresh lê o cookie primeiro e, com cookie, exige ``X-Mplacas-Auth: 1`` e
  ``Origin`` permitido (senão 403, sem rotacionar);
- logout com cookie revoga e apaga o cookie;
- token recém-rotacionado (duas abas) → 401 sem derrubar a família; depois
  da janela, replay derruba a família;
- teto absoluto da família → 401 e família encerrada;
- isolamento entre organizações também pelo cookie;
- IP do cliente: ``X-Forwarded-For`` forjado não vale, e
  ``X-Mplacas-Client-IP`` só vale com o segredo do proxy (que nunca vai a log).

O fluxo antigo (refresh token no corpo, sem cookie) continua coberto, sem
alteração, por ``test_auth_characterization.py`` e companhia.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.requests import Request

from mplacas.auth.db_models import AuthSessionRecord, LoginRateLimitRecord
from mplacas.auth.password import hash_password
from mplacas.auth.session_service import LoginRateLimitService
from mplacas.core.client_ip import resolve_client_ip
from mplacas.core.config import Settings, get_settings
from mplacas.core.jwt import decode_token
from mplacas.core.security import OperationsRole
from mplacas.credentials.db_models import OperationalUserRecord
from mplacas.db.base import Base
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_db_models import PURPOSE_RESET
from mplacas.organizations.invitation_service import InvitationService

_PASSWORD = "correct-horse-battery"
_JWT_SECRET = "cookie-test-jwt-secret-at-least-32-bytes"
_ORIGIN = "https://mplacas-frontend.pages.dev"
_COOKIE = "__Secure-mplacas_rt"
_GUARD = {"X-Mplacas-Auth": "1", "Origin": _ORIGIN}
_PROXY_SECRET = "segredo-do-proxy-de-teste-com-mais-de-32-bytes"
_ENGINES: list = []
_CLIENTS: list = []


def _make_client(monkeypatch, tmp_path, **env: str):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", _JWT_SECRET)
    monkeypatch.setenv("MPLACAS_CORS_ALLOWED_ORIGINS", _ORIGIN)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    url = f"sqlite+aiosqlite:///{tmp_path}/auth-cookie.db"
    monkeypatch.setenv("MPLACAS_DATABASE_URL", url)
    get_settings.cache_clear()

    import mplacas.auth.router as auth_router
    import mplacas.db.session as db_session
    from mplacas.main import app

    engine = create_async_engine(url, poolclass=NullPool)
    _ENGINES.append(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_prepare())
    monkeypatch.setattr(auth_router, "SessionFactory", factory)
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    client = TestClient(app)
    _CLIENTS.append(client)
    return client, factory


@pytest.fixture(autouse=True)
def _teardown():
    yield
    while _CLIENTS:
        _CLIENTS.pop().close()
    while _ENGINES:
        asyncio.run(_ENGINES.pop().dispose())
    get_settings.cache_clear()


def _seed_user(
    factory, *, name: str = "dona@tenant.example", slug: str | None = None
) -> tuple[uuid.UUID, uuid.UUID]:
    async def _seed() -> tuple[uuid.UUID, uuid.UUID]:
        async with factory() as session:
            org = OrganizationRecord(
                name="Tenant", slug=slug or f"tenant-{uuid.uuid4().hex[:12]}", active=True
            )
            session.add(org)
            await session.flush()
            user = OperationalUserRecord(
                organization_id=org.id,
                name=name,
                role="ADMIN",
                active=True,
                password_hash=hash_password(_PASSWORD),
            )
            session.add(user)
            await session.commit()
            return user.id, org.id

    return asyncio.run(_seed())


def _login(client: TestClient, username: str = "dona@tenant.example", **headers: str):
    return client.post(
        "/auth/login", json={"username": username, "password": _PASSWORD}, headers=headers
    )


def _set_cookies(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def _parse_cookie(header: str) -> tuple[str, str, dict[str, str]]:
    first, *attributes = [part.strip() for part in header.split(";")]
    name, _, value = first.partition("=")
    parsed: dict[str, str] = {}
    for attribute in attributes:
        key, _, attr_value = attribute.partition("=")
        parsed[key.lower()] = attr_value
    return name, value, parsed


def _refresh_cookie(response) -> tuple[str, dict[str, str]]:
    matches = [_parse_cookie(h) for h in _set_cookies(response) if h.startswith(f"{_COOKIE}=")]
    assert len(matches) == 1, _set_cookies(response)
    _name, value, attributes = matches[0]
    return value.strip('"'), attributes


def _assert_session_cookie_attributes(attributes: dict[str, str], *, path: str = "/api/auth"):
    assert "httponly" in attributes
    assert "secure" in attributes
    assert attributes["samesite"].lower() == "strict"
    assert attributes["path"] == path


def _cookie_refresh(client: TestClient, token: str, headers: dict[str, str] | None = None, **kw):
    merged = {"Cookie": f"{_COOKIE}={token}", **(_GUARD if headers is None else headers)}
    return client.post("/auth/refresh", headers=merged, **kw)


def _sessions(factory) -> list[AuthSessionRecord]:
    async def _read() -> list[AuthSessionRecord]:
        async with factory() as session:
            return list(await session.scalars(select(AuthSessionRecord)))

    return asyncio.run(_read())


def _session_for(factory, token: str) -> AuthSessionRecord:
    jti = decode_token(token, expected_type="refresh").jti
    (record,) = [s for s in _sessions(factory) if s.id == jti]
    return record


def _execute(factory, statement) -> None:
    async def _run() -> None:
        async with factory() as session:
            await session.execute(statement)
            await session.commit()

    asyncio.run(_run())


# --- cookie emitido em todo lugar que abre sessão -----------------------------


def test_login_sets_refresh_cookie_with_all_attributes(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)

    response = _login(client)

    assert response.status_code == 200
    value, attributes = _refresh_cookie(response)
    # Transitório: o corpo ainda traz o mesmo token.
    assert value == response.json()["refresh_token"]
    _assert_session_cookie_attributes(attributes)
    max_age = int(attributes["max-age"])
    assert 1_209_600 - 5 <= max_age <= 1_209_600


def test_cookie_max_age_never_goes_beyond_absolute_cap(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(
        monkeypatch, tmp_path, MPLACAS_AUTH_SESSION_MAX_AGE_DAYS="1"
    )
    _seed_user(factory)

    login = _login(client)
    _value, attributes = _refresh_cookie(login)
    assert 86_400 - 5 <= int(attributes["max-age"]) <= 86_400

    refreshed = _cookie_refresh(client, login.json()["refresh_token"])
    assert refreshed.status_code == 200
    _value, attributes = _refresh_cookie(refreshed)
    assert int(attributes["max-age"]) <= 86_400


def test_cookie_path_is_configurable(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path, MPLACAS_AUTH_COOKIE_PATH="/auth")
    _seed_user(factory)

    _value, attributes = _refresh_cookie(_login(client))

    _assert_session_cookie_attributes(attributes, path="/auth")


def test_cookie_can_be_turned_off(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path, MPLACAS_AUTH_COOKIE_ENABLED="false")
    _seed_user(factory)

    login = _login(client)
    assert login.status_code == 200
    assert _set_cookies(login) == []
    # Desligado, o cookie também não é lido: sem corpo, não há credencial.
    response = _cookie_refresh(client, login.json()["refresh_token"])
    assert response.status_code == 401
    assert _session_for(factory, login.json()["refresh_token"]).active is True


def test_invitation_accept_sets_refresh_cookie(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _user_id, org_id = _seed_user(factory)

    async def _seed() -> str:
        async with factory() as session:
            _invitation, token = await InvitationService(session).create(
                organization_id=org_id,
                username="convidado@tenant.example",
                role=OperationsRole.READ,
                created_by_user_id=None,
                ttl_seconds=3600,
            )
            await session.commit()
            return token

    response = client.post(
        "/auth/invitations/accept",
        json={"token": asyncio.run(_seed()), "password": _PASSWORD},
        headers={"Origin": _ORIGIN},
    )

    assert response.status_code == 200, response.text
    value, attributes = _refresh_cookie(response)
    assert value == response.json()["refresh_token"]
    _assert_session_cookie_attributes(attributes)


def test_access_reset_revokes_all_sessions_and_sets_fresh_cookie(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _user_id, org_id = _seed_user(factory)
    old_tokens = [_login(client).json()["refresh_token"] for _ in range(2)]

    async def _seed() -> str:
        async with factory() as session:
            _invitation, token = await InvitationService(session).create(
                organization_id=org_id,
                username="dona@tenant.example",
                role=OperationsRole.ADMIN,
                created_by_user_id=None,
                ttl_seconds=3600,
                purpose=PURPOSE_RESET,
            )
            await session.commit()
            return token

    response = client.post(
        "/auth/invitations/accept",
        json={"token": asyncio.run(_seed()), "password": "uma-senha-nova-longa"},
    )

    assert response.status_code == 200, response.text
    new_cookie, attributes = _refresh_cookie(response)
    _assert_session_cookie_attributes(attributes)
    assert new_cookie not in old_tokens
    assert all(_session_for(factory, t).active is False for t in old_tokens)
    for token in old_tokens:
        assert _cookie_refresh(client, token).status_code == 401
    assert _cookie_refresh(client, new_cookie).status_code == 200


# --- refresh pelo cookie e defesa CSRF -----------------------------------------


def test_refresh_via_cookie_rotates_and_sets_new_cookie(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    user_id, org_id = _seed_user(factory)
    first = _login(client).json()["refresh_token"]

    response = _cookie_refresh(client, first)

    assert response.status_code == 200
    new_cookie, attributes = _refresh_cookie(response)
    _assert_session_cookie_attributes(attributes)
    assert new_cookie != first
    assert new_cookie == response.json()["refresh_token"]
    access = decode_token(response.json()["access_token"], expected_type="access")
    assert (access.sub, access.org_id) == (user_id, org_id)
    assert _session_for(factory, first).active is False
    assert _session_for(factory, new_cookie).active is True


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": _ORIGIN},
        {"X-Mplacas-Auth": "true", "Origin": _ORIGIN},
        {"X-Mplacas-Auth": "1"},
        {"X-Mplacas-Auth": "1", "Origin": "https://evil.example"},
        {"X-Mplacas-Auth": "1", "Origin": "null"},
        {"X-Mplacas-Auth": "1", "Origin": "https://mplacas-frontend.pages.dev.evil.example"},
    ],
    ids=[
        "sem-cabecalho",
        "cabecalho-errado",
        "sem-origin",
        "origin-alheio",
        "origin-null",
        "sufixo",
    ],
)
def test_refresh_via_cookie_without_csrf_guard_is_403_and_does_not_rotate(
    monkeypatch, tmp_path, headers
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)
    token = _login(client).json()["refresh_token"]

    response = _cookie_refresh(client, token, headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "request origin not allowed"}
    assert _set_cookies(response) == []
    assert _session_for(factory, token).active is True
    assert len(_sessions(factory)) == 1


def test_cookie_flow_fails_closed_without_configured_origins(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)
    token = _login(client).json()["refresh_token"]
    monkeypatch.delenv("MPLACAS_CORS_ALLOWED_ORIGINS")
    get_settings.cache_clear()

    assert _cookie_refresh(client, token).status_code == 403
    assert _session_for(factory, token).active is True


def test_cookie_wins_over_body_token(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)
    cookie_token = _login(client).json()["refresh_token"]
    body_token = _login(client).json()["refresh_token"]

    response = _cookie_refresh(client, cookie_token, json={"refresh_token": body_token})

    assert response.status_code == 200
    assert _session_for(factory, cookie_token).active is False
    assert _session_for(factory, body_token).active is True


def test_invalid_cookie_is_401_and_cleared(monkeypatch, tmp_path) -> None:
    client, _factory = _make_client(monkeypatch, tmp_path)

    response = _cookie_refresh(client, "x.y.z")

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid or expired refresh token"}
    _value, attributes = _refresh_cookie(response)
    assert attributes["max-age"] == "0"
    _assert_session_cookie_attributes(attributes)


def test_refresh_without_cookie_or_body_is_401(monkeypatch, tmp_path) -> None:
    client, _factory = _make_client(monkeypatch, tmp_path)

    response = client.post("/auth/refresh", headers=_GUARD)

    assert response.status_code == 401


def test_body_flow_needs_no_guard_headers(monkeypatch, tmp_path) -> None:
    """O frontend atual (corpo, sem cookie, sem cabeçalho) segue funcionando."""
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)
    token = _login(client, Origin=_ORIGIN).json()["refresh_token"]

    response = client.post(
        "/auth/refresh", json={"refresh_token": token}, headers={"Origin": _ORIGIN}
    )

    assert response.status_code == 200
    assert response.json()["refresh_token"] != token


# --- login-CSRF ----------------------------------------------------------------


@pytest.mark.parametrize("origin", ["https://evil.example", "null"])
def test_login_from_foreign_origin_is_403_and_touches_nothing(
    monkeypatch, tmp_path, origin
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)

    response = _login(client, Origin=origin)

    assert response.status_code == 403
    assert _set_cookies(response) == []
    assert _sessions(factory) == []

    async def _rows() -> list[LoginRateLimitRecord]:
        async with factory() as session:
            return list(await session.scalars(select(LoginRateLimitRecord)))

    assert asyncio.run(_rows()) == []


def test_login_with_allowed_origin_or_without_origin_works(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)

    assert _login(client, Origin=_ORIGIN).status_code == 200
    assert _login(client, Origin=_ORIGIN + "/").status_code == 200
    assert _login(client).status_code == 200


def test_invitation_accept_from_foreign_origin_is_403(monkeypatch, tmp_path) -> None:
    client, _factory = _make_client(monkeypatch, tmp_path)

    response = client.post(
        "/auth/invitations/accept",
        json={"token": "qualquer", "password": _PASSWORD},
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403


# --- logout --------------------------------------------------------------------


def test_logout_via_cookie_revokes_and_clears_cookie(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)
    token = _login(client).json()["refresh_token"]

    response = client.post("/auth/logout", headers={"Cookie": f"{_COOKIE}={token}", **_GUARD})

    assert response.status_code == 204
    value, attributes = _refresh_cookie(response)
    assert value == ""
    assert attributes["max-age"] == "0"
    _assert_session_cookie_attributes(attributes)
    record = _session_for(factory, token)
    assert record.active is False
    assert record.revoked_at is not None
    assert _cookie_refresh(client, token).status_code == 401


def test_logout_via_cookie_is_204_even_for_garbage(monkeypatch, tmp_path) -> None:
    client, _factory = _make_client(monkeypatch, tmp_path)

    response = client.post("/auth/logout", headers={"Cookie": f"{_COOKIE}=lixo", **_GUARD})

    assert response.status_code == 204
    assert _refresh_cookie(response)[1]["max-age"] == "0"


def test_logout_via_cookie_without_guard_is_403_and_keeps_session(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)
    token = _login(client).json()["refresh_token"]

    response = client.post(
        "/auth/logout",
        headers={"Cookie": f"{_COOKIE}={token}", "Origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert _set_cookies(response) == []
    assert _session_for(factory, token).active is True


def test_logout_body_flow_still_works_over_http(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)
    token = _login(client).json()["refresh_token"]

    response = client.post("/auth/logout", json={"refresh_token": token})

    assert response.status_code == 204
    assert _session_for(factory, token).active is False


# --- tolerância de rotação e replay ------------------------------------------------


def test_reuse_within_grace_is_401_without_revoking_family(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)
    first = _login(client).json()["refresh_token"]
    second = _cookie_refresh(client, first).json()["refresh_token"]

    # A "outra aba" chega com o token que acabou de ser trocado.
    late = _cookie_refresh(client, first)

    assert late.status_code == 401
    assert len(_sessions(factory)) == 2  # nenhuma sessão nova emitida
    assert _session_for(factory, second).active is True
    assert _session_for(factory, first).revoked_at is None
    assert _cookie_refresh(client, second).status_code == 200


def test_reuse_after_grace_is_replay_and_revokes_family(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)
    first = _login(client).json()["refresh_token"]
    second = _cookie_refresh(client, first).json()["refresh_token"]
    first_id = decode_token(first, expected_type="refresh").jti
    _execute(
        factory,
        update(AuthSessionRecord)
        .where(AuthSessionRecord.id == first_id)
        .values(rotated_at=datetime.now(UTC) - timedelta(seconds=11)),
    )

    assert _cookie_refresh(client, first).status_code == 401

    assert all(record.active is False for record in _sessions(factory))
    assert _session_for(factory, second).revoked_at is not None
    assert _cookie_refresh(client, second).status_code == 401


def test_body_flow_replay_after_grace_also_revokes_family(monkeypatch, tmp_path) -> None:
    """A revogação por replay agora é gravada (commit antes do 401)."""
    client, factory = _make_client(
        monkeypatch, tmp_path, MPLACAS_AUTH_REFRESH_REUSE_GRACE_SECONDS="0"
    )
    _seed_user(factory)
    first = _login(client).json()["refresh_token"]
    second = client.post("/auth/refresh", json={"refresh_token": first}).json()["refresh_token"]

    assert client.post("/auth/refresh", json={"refresh_token": first}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": second}).status_code == 401
    assert all(record.active is False for record in _sessions(factory))


# --- teto absoluto ------------------------------------------------------------------


def test_refresh_past_absolute_cap_is_401_and_ends_family(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)
    root = _login(client).json()["refresh_token"]
    second = _cookie_refresh(client, root).json()["refresh_token"]
    root_id = decode_token(root, expected_type="refresh").jti
    _execute(
        factory,
        update(AuthSessionRecord)
        .where(AuthSessionRecord.id == root_id)
        .values(created_at=datetime.now(UTC) - timedelta(days=31)),
    )

    response = _cookie_refresh(client, second)

    assert response.status_code == 401
    assert _refresh_cookie(response)[1]["max-age"] == "0"
    assert all(record.active is False for record in _sessions(factory))
    assert len(_sessions(factory)) == 2
    assert _session_for(factory, second).revoked_at is not None


def test_rotated_session_never_expires_after_family_cap(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)
    root = _login(client).json()["refresh_token"]
    root_id = decode_token(root, expected_type="refresh").jti
    started = datetime.now(UTC) - timedelta(days=29)
    _execute(
        factory,
        update(AuthSessionRecord).where(AuthSessionRecord.id == root_id).values(created_at=started),
    )

    response = _cookie_refresh(client, root)

    assert response.status_code == 200
    new_token, attributes = _refresh_cookie(response)
    assert int(attributes["max-age"]) <= 86_400
    expires_at = _session_for(factory, new_token).expires_at.replace(tzinfo=UTC)
    assert expires_at <= started + timedelta(days=30, seconds=1)


# --- isolamento entre organizações ----------------------------------------------------


def test_cookie_of_org_a_never_yields_token_for_org_b(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    user_a, org_a = _seed_user(factory, name="a@tenant-a.example")
    _user_b, org_b = _seed_user(factory, name="b@tenant-b.example")
    token_a = _login(client, "a@tenant-a.example").json()["refresh_token"]
    token_b = _login(client, "b@tenant-b.example").json()["refresh_token"]

    response = _cookie_refresh(client, token_a, json={"refresh_token": token_b})

    assert response.status_code == 200
    access = decode_token(response.json()["access_token"], expected_type="access")
    refreshed = decode_token(response.json()["refresh_token"], expected_type="refresh")
    assert (access.sub, access.org_id) == (user_a, org_a)
    assert refreshed.org_id == org_a != org_b
    assert _session_for(factory, token_b).active is True


def test_deactivated_organization_cannot_refresh_via_cookie(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _user_id, org_id = _seed_user(factory)
    token = _login(client).json()["refresh_token"]
    _execute(
        factory,
        update(OrganizationRecord).where(OrganizationRecord.id == org_id).values(active=False),
    )

    response = _cookie_refresh(client, token)

    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_deactivated_user_cannot_refresh_via_cookie(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    user_id, _org_id = _seed_user(factory)
    token = _login(client).json()["refresh_token"]
    _execute(
        factory,
        update(OperationalUserRecord)
        .where(OperationalUserRecord.id == user_id)
        .values(active=False),
    )

    assert _cookie_refresh(client, token).status_code == 401


# --- IP do cliente -------------------------------------------------------------------


def _request(headers: dict[str, str], client_host: str = "10.0.0.5") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (client_host, 1234),
        }
    )


def _settings(secret: str | None) -> Settings:
    return Settings(_env_file=None, proxy_shared_secret=secret)  # type: ignore[call-arg]


def test_client_ip_header_ignored_without_configured_secret() -> None:
    request = _request(
        {"X-Mplacas-Client-IP": "203.0.113.7", "X-Mplacas-Proxy-Secret": _PROXY_SECRET}
    )
    assert resolve_client_ip(request, _settings(None)) == "10.0.0.5"


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Mplacas-Client-IP": "203.0.113.7"},
        {"X-Mplacas-Client-IP": "203.0.113.7", "X-Mplacas-Proxy-Secret": "errado"},
        {"X-Mplacas-Client-IP": "não-é-ip", "X-Mplacas-Proxy-Secret": _PROXY_SECRET},
    ],
    ids=["sem-segredo", "segredo-errado", "ip-invalido"],
)
def test_client_ip_header_needs_matching_secret_and_valid_ip(headers) -> None:
    assert resolve_client_ip(_request(headers), _settings(_PROXY_SECRET)) == "10.0.0.5"


def test_client_ip_header_honoured_with_matching_secret() -> None:
    request = _request(
        {"X-Mplacas-Client-IP": " 2001:db8::1 ", "X-Mplacas-Proxy-Secret": _PROXY_SECRET}
    )
    assert resolve_client_ip(request, _settings(_PROXY_SECRET)) == "2001:db8::1"


def test_short_proxy_secret_is_rejected() -> None:
    with pytest.raises(ValueError):
        _settings("curto")


def test_login_rate_limit_uses_proxy_ip_only_with_secret(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(
        monkeypatch, tmp_path, MPLACAS_PROXY_SHARED_SECRET=_PROXY_SECRET
    )

    def _fail(**headers: str) -> None:
        response = client.post(
            "/auth/login",
            json={"username": "ninguem@x.example", "password": "errada"},
            headers=headers,
        )
        assert response.status_code == 401

    _fail(**{"X-Mplacas-Client-IP": "203.0.113.7", "X-Mplacas-Proxy-Secret": _PROXY_SECRET})
    _fail(**{"X-Mplacas-Client-IP": "198.51.100.9", "X-Mplacas-Proxy-Secret": "chute"})
    _fail(**{"X-Forwarded-For": "192.0.2.1"})

    async def _keys() -> set[str]:
        async with factory() as session:
            return set(await session.scalars(select(LoginRateLimitRecord.key)))

    def key(host: str) -> str:
        return LoginRateLimitService.key_for(username="ninguem@x.example", client_host=host)

    keys = asyncio.run(_keys())
    assert keys == {key("203.0.113.7"), key("testclient")}


def test_spoofed_ip_cannot_dodge_login_lockout(monkeypatch, tmp_path) -> None:
    client, _factory = _make_client(monkeypatch, tmp_path, MPLACAS_AUTH_LOGIN_MAX_ATTEMPTS="2")

    statuses = [
        client.post(
            "/auth/login",
            json={"username": "alvo@x.example", "password": "errada"},
            headers={
                "X-Forwarded-For": f"192.0.2.{attempt}",
                "X-Mplacas-Client-IP": f"198.51.100.{attempt}",
                "X-Mplacas-Proxy-Secret": _PROXY_SECRET,
            },
        ).status_code
        for attempt in range(1, 4)
    ]

    assert statuses == [401, 401, 429]


def test_proxy_secret_never_reaches_logs(monkeypatch, tmp_path, caplog) -> None:
    client, factory = _make_client(
        monkeypatch, tmp_path, MPLACAS_PROXY_SHARED_SECRET=_PROXY_SECRET
    )
    _seed_user(factory)
    wrong_secret = "outro-segredo-errado-tambem-com-32-bytes-ou-mais"

    with caplog.at_level(logging.DEBUG):
        for secret in (_PROXY_SECRET, wrong_secret):
            client.post(
                "/auth/login",
                json={"username": "dona@tenant.example", "password": _PASSWORD},
                headers={"X-Mplacas-Client-IP": "203.0.113.7", "X-Mplacas-Proxy-Secret": secret},
            )

    assert any(r.getMessage() == "proxy_shared_secret_mismatch" for r in caplog.records)
    dumped = caplog.text + "".join(repr(vars(record)) for record in caplog.records)
    assert _PROXY_SECRET not in dumped
    assert wrong_secret not in dumped
    assert _PROXY_SECRET not in repr(get_settings())
    assert _PROXY_SECRET not in str(get_settings().safe_summary())


def test_forwarded_for_trusted_only_from_private_proxy() -> None:
    """Com a configuração padrão, o uvicorn só aceita X-Forwarded-For vindo do
    proxy do Render (rede privada) e pega o endereço mais à direita que não é
    proxy: o que o cliente escreveu à esquerda é descartado."""
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    seen: dict[str, object] = {}

    async def app(scope, receive, send) -> None:
        seen["client"] = scope["client"]

    middleware = ProxyHeadersMiddleware(
        app, trusted_hosts=Settings(_env_file=None).forwarded_allow_ips  # type: ignore[call-arg]
    )

    def call(peer: str, xff: str) -> object:
        scope = {
            "type": "http",
            "client": (peer, 1234),
            "headers": [(b"x-forwarded-for", xff.encode())],
        }
        asyncio.run(middleware(scope, None, None))  # type: ignore[arg-type]
        return seen["client"][0]  # type: ignore[index]

    assert call("10.20.30.40", "1.2.3.4, 198.51.100.9") == "198.51.100.9"
    assert call("10.20.30.40", "1.2.3.4, 198.51.100.9, 10.1.1.1") == "198.51.100.9"
    assert call("203.0.113.50", "1.2.3.4") == "203.0.113.50"


def test_wildcard_forwarded_allow_ips_is_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, forwarded_allow_ips="*")  # type: ignore[call-arg]
