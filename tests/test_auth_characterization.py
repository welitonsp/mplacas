"""Characterization tests for ``/auth`` — pin today's security behaviour.

Written after the post-merge review of PR #170 found that most security rules
of the login flow had no test that would fail if they were removed. These
tests change no production code: they fix the current behaviour of
``auth/router.py`` and ``auth/service.py`` end to end (HTTP + real SQLite
file), so a future refactor of this module cannot silently drop a rule.
Each rule here was mutation-checked: removing it makes at least one test fail.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mplacas.auth.db_models import LoginRateLimitRecord
from mplacas.auth.password import hash_password
from mplacas.core.config import get_settings
from mplacas.core.jwt import decode_token
from mplacas.core.security import OperationsRole
from mplacas.credentials.db_models import OperationalUserRecord
from mplacas.db.base import Base
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_service import InvitationService

_PASSWORD = "correct-horse-battery"
_JWT_SECRET = "test-jwt-secret-at-least-32-bytes-long"
_ENGINES: list = []
_CLIENTS: list = []


def _make_client(monkeypatch, tmp_path, *, jwt: bool = True):
    if jwt:
        monkeypatch.setenv("MPLACAS_JWT_SECRET", _JWT_SECRET)
    else:
        monkeypatch.delenv("MPLACAS_JWT_SECRET", raising=False)
    url = f"sqlite+aiosqlite:///{tmp_path}/auth.db"
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
    factory,
    *,
    name: str = "dona@tenant.example",
    password: str | None = _PASSWORD,
    user_active: bool = True,
    org_active: bool = True,
) -> tuple[uuid.UUID, uuid.UUID]:
    async def _seed() -> tuple[uuid.UUID, uuid.UUID]:
        async with factory() as session:
            org = OrganizationRecord(
                name="Tenant", slug=f"tenant-{uuid.uuid4().hex[:12]}", active=org_active
            )
            session.add(org)
            await session.flush()
            user = OperationalUserRecord(
                organization_id=org.id,
                name=name,
                role="ADMIN",
                active=user_active,
                password_hash=hash_password(password) if password is not None else None,
            )
            session.add(user)
            await session.commit()
            return user.id, org.id

    return asyncio.run(_seed())


def _rate_limit_rows(factory) -> list[LoginRateLimitRecord]:
    async def _read() -> list[LoginRateLimitRecord]:
        async with factory() as session:
            return list(await session.scalars(select(LoginRateLimitRecord)))

    return asyncio.run(_read())


def _login(client: TestClient, username: str, password: str):
    return client.post("/auth/login", json={"username": username, "password": password})


def _assert_invalid_credentials(response) -> None:
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}
    assert response.headers.get("www-authenticate") == "Bearer"


# --- /auth/login --------------------------------------------------------------


def test_login_success_returns_token_pair_for_the_user(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    user_id, org_id = _seed_user(factory)

    response = _login(client, "dona@tenant.example", _PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    access = decode_token(body["access_token"], expected_type="access")
    assert (access.sub, access.org_id, access.role) == (user_id, org_id, "ADMIN")
    refresh = decode_token(body["refresh_token"], expected_type="refresh")
    assert (refresh.sub, refresh.org_id) == (user_id, org_id)


def test_login_wrong_password_and_unknown_user_are_indistinguishable(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)

    wrong_password = _login(client, "dona@tenant.example", "not-the-password")
    unknown_user = _login(client, "ninguem@tenant.example", _PASSWORD)

    _assert_invalid_credentials(wrong_password)
    _assert_invalid_credentials(unknown_user)
    assert wrong_password.json() == unknown_user.json()


@pytest.mark.parametrize(
    ("user_active", "org_active"), [(False, True), (True, False)], ids=["user", "org"]
)
def test_login_rejects_inactive_user_or_organization(
    monkeypatch, tmp_path, user_active, org_active
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory, user_active=user_active, org_active=org_active)

    _assert_invalid_credentials(_login(client, "dona@tenant.example", _PASSWORD))


@pytest.mark.parametrize("password", [None, _PASSWORD], ids=["no-hash", "unknown-user"])
def test_login_without_usable_user_still_pays_the_dummy_hash(
    monkeypatch, tmp_path, password
) -> None:
    """Timing defence: a missing user (or one without a password) must still
    run one Argon2 verification, against the module's dummy hash."""
    import mplacas.auth.service as auth_service

    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory, password=password)
    calls: list[str] = []
    real_verify = auth_service.verify_password

    def spy(supplied: str, stored: str) -> bool:
        calls.append(stored)
        return real_verify(supplied, stored)

    monkeypatch.setattr(auth_service, "verify_password", spy)
    username = "dona@tenant.example" if password is None else "ninguem@tenant.example"

    _assert_invalid_credentials(_login(client, username, _PASSWORD))
    assert calls == [auth_service.DUMMY_PASSWORD_HASH]


def test_login_failure_is_committed_before_the_401(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)

    _assert_invalid_credentials(_login(client, "dona@tenant.example", "wrong"))

    # Read back in a fresh session: only a committed row is visible.
    rows = _rate_limit_rows(factory)
    assert [row.attempt_count for row in rows] == [1]


def test_login_locks_out_after_max_attempts_even_with_right_password(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("MPLACAS_AUTH_LOGIN_MAX_ATTEMPTS", "2")
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)

    for _ in range(2):
        _assert_invalid_credentials(_login(client, "dona@tenant.example", "wrong"))
    locked = _login(client, "dona@tenant.example", _PASSWORD)

    assert locked.status_code == 429
    assert locked.json() == {"detail": "too many failed login attempts; try again later"}


def test_login_success_clears_previous_failures(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)
    _login(client, "dona@tenant.example", "wrong")
    assert len(_rate_limit_rows(factory)) == 1

    assert _login(client, "dona@tenant.example", _PASSWORD).status_code == 200

    assert _rate_limit_rows(factory) == []


# --- JWT not configured -------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/auth/login", {"username": "dona@tenant.example", "password": _PASSWORD}),
        ("/auth/refresh", {"refresh_token": "anything"}),
        ("/auth/invitations/accept", {"token": "anything", "password": _PASSWORD}),
    ],
    ids=["login", "refresh", "accept"],
)
def test_returns_503_without_jwt_and_touches_no_rate_limit(
    monkeypatch, tmp_path, path, payload
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path, jwt=False)

    response = client.post(path, json=payload)

    assert response.status_code == 503
    assert response.json() == {"detail": "JWT authentication is not configured"}
    assert _rate_limit_rows(factory) == []


# --- /auth/refresh ------------------------------------------------------------


def _assert_invalid_refresh(response) -> None:
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid or expired refresh token"}
    assert response.headers.get("www-authenticate") == "Bearer"


def test_refresh_rejects_malformed_token(monkeypatch, tmp_path) -> None:
    client, _factory = _make_client(monkeypatch, tmp_path)

    _assert_invalid_refresh(client.post("/auth/refresh", json={"refresh_token": "x.y.z"}))


def test_refresh_rotates_once_and_rejects_reuse(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    _seed_user(factory)
    first = _login(client, "dona@tenant.example", _PASSWORD).json()["refresh_token"]

    rotated = client.post("/auth/refresh", json={"refresh_token": first})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != first

    _assert_invalid_refresh(client.post("/auth/refresh", json={"refresh_token": first}))


def test_refresh_rejects_user_deactivated_after_login(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    user_id, _org_id = _seed_user(factory)
    token = _login(client, "dona@tenant.example", _PASSWORD).json()["refresh_token"]

    async def _deactivate() -> None:
        async with factory() as session:
            user = await session.get(OperationalUserRecord, user_id)
            assert user is not None
            user.active = False
            await session.commit()

    asyncio.run(_deactivate())

    _assert_invalid_refresh(client.post("/auth/refresh", json={"refresh_token": token}))


def test_load_active_user_requires_the_token_organization(monkeypatch, tmp_path) -> None:
    """The refresh flow passes the token's ``org_id``; a user must not be
    found under any other organization."""
    from mplacas.auth.service import load_active_user

    _client, factory = _make_client(monkeypatch, tmp_path)
    user_id, org_id = _seed_user(factory)

    async def _lookup(organization_id: uuid.UUID) -> OperationalUserRecord | None:
        async with factory() as session:
            return await load_active_user(
                session, user_id=user_id, organization_id=organization_id
            )

    assert asyncio.run(_lookup(org_id)) is not None
    assert asyncio.run(_lookup(uuid.uuid4())) is None


# --- invitations --------------------------------------------------------------


def test_inspect_invitation_locks_out_after_max_attempts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MPLACAS_AUTH_LOGIN_MAX_ATTEMPTS", "2")
    client, _factory = _make_client(monkeypatch, tmp_path)

    for _ in range(2):
        response = client.post("/auth/invitations/inspect", json={"token": "guess-me"})
        assert response.status_code == 400
        assert response.json() == {"detail": "invalid or expired invitation"}

    locked = client.post("/auth/invitations/inspect", json={"token": "guess-me"})
    assert locked.status_code == 429


def test_invitation_rate_limit_key_never_contains_the_token(monkeypatch, tmp_path) -> None:
    """The key is derived from a truncated SHA-256 of the token (never the
    token itself), then hashed again by ``LoginRateLimitService.key_for``.
    The expected value is computed independently of ``invitation_rate_key``
    so this pins the documented derivation, not the function's own output."""
    from mplacas.auth.session_service import LoginRateLimitService

    client, factory = _make_client(monkeypatch, tmp_path)
    token = "segredo-do-convite-que-nao-pode-vazar"

    client.post("/auth/invitations/inspect", json={"token": token})

    (row,) = _rate_limit_rows(factory)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    assert token not in row.key
    assert row.key == LoginRateLimitService.key_for(username=digest, client_host="testclient")


def test_valid_invitation_clears_its_failure_counter(monkeypatch, tmp_path) -> None:
    from mplacas.auth.service import invitation_rate_key

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
            session.add(
                LoginRateLimitRecord(
                    key=invitation_rate_key(token=token, client_host="testclient"),
                    attempt_count=1,
                )
            )
            await session.commit()
            return token

    token = asyncio.run(_seed())

    assert client.post("/auth/invitations/inspect", json={"token": token}).status_code == 200
    assert _rate_limit_rows(factory) == []


def test_accept_that_loses_the_mark_accepted_race_leaves_no_orphan_user(
    monkeypatch, tmp_path
) -> None:
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

    token = asyncio.run(_seed())

    async def lost_race(self, **_kwargs) -> bool:
        return False

    monkeypatch.setattr(InvitationService, "mark_accepted", lost_race)

    response = client.post(
        "/auth/invitations/accept", json={"token": token, "password": _PASSWORD}
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid or expired invitation"}

    async def _count() -> int:
        async with factory() as session:
            return int(
                await session.scalar(
                    select(func.count()).select_from(OperationalUserRecord).where(
                        OperationalUserRecord.name == "convidado@tenant.example"
                    )
                )
                or 0
            )

    assert asyncio.run(_count()) == 0
