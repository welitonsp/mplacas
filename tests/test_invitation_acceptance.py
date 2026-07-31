from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.core.config import get_settings
from mplacas.core.security import OperationsRole
from mplacas.credentials.db_models import OperationalUserRecord
from mplacas.db.base import Base
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_db_models import UserInvitationRecord
from mplacas.organizations.invitation_service import (
    InvitationService,
    hash_invitation_token,
)

_VALID_PASSWORD = "correct-horse-battery"


def _make_client(monkeypatch, tmp_path):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv(
        "MPLACAS_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path}/invitations.db",
    )
    get_settings.cache_clear()

    import mplacas.auth.router as auth_router
    import mplacas.db.session as db_session
    import mplacas.organizations.router as organizations_router
    from mplacas.main import app

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/invitations.db")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_prepare())

    monkeypatch.setattr(organizations_router, "SessionFactory", factory)
    monkeypatch.setattr(auth_router, "SessionFactory", factory)
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    return TestClient(app), factory


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    yield
    get_settings.cache_clear()


def _seed_org(factory) -> uuid.UUID:
    async def _seed() -> uuid.UUID:
        async with factory() as session:
            org = OrganizationRecord(
                name="Tenant", slug=f"tenant-{uuid.uuid4().hex[:12]}", active=True
            )
            session.add(org)
            await session.flush()
            await session.commit()
            return org.id

    return asyncio.run(_seed())


def _seed_invitation(
    factory,
    org_id: uuid.UUID,
    *,
    username: str = "new-user@tenant.example",
    role: OperationsRole = OperationsRole.READ,
    ttl_seconds: int = 3600,
) -> tuple[uuid.UUID, str]:
    async def _seed() -> tuple[uuid.UUID, str]:
        async with factory() as session:
            invitation, token = await InvitationService(session).create(
                organization_id=org_id,
                username=username,
                role=role,
                created_by_user_id=None,
                ttl_seconds=ttl_seconds,
            )
            await session.commit()
            return invitation.id, token

    return asyncio.run(_seed())


def _count_users(factory) -> int:
    async def _count() -> int:
        async with factory() as session:
            records = list(await session.scalars(select(OperationalUserRecord)))
            return len(records)

    return asyncio.run(_count())


def test_accept_invitation_creates_user_marks_accepted_and_returns_working_tokens(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)
    invitation_id, token = _seed_invitation(
        factory, org_id, role=OperationsRole.ADMIN
    )

    response = client.post(
        "/auth/invitations/accept",
        json={"token": token, "password": _VALID_PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"

    async def _check():
        async with factory() as session:
            invitation = await session.get(UserInvitationRecord, invitation_id)
            assert invitation is not None
            assert invitation.accepted_at is not None
            assert invitation.accepted_user_id is not None

            user = await session.get(OperationalUserRecord, invitation.accepted_user_id)
            assert user is not None
            assert user.name == "new-user@tenant.example"
            assert user.role == OperationsRole.ADMIN.value
            assert user.organization_id == org_id
            assert user.password_hash is not None
            assert user.password_hash != _VALID_PASSWORD

    asyncio.run(_check())

    # The tokens returned must authenticate on a real organization-scoped
    # route, exactly like the tokens returned by ``POST /auth/login``.
    own_org_response = client.get(
        f"/organizations/{org_id}",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert own_org_response.status_code == 200
    assert own_org_response.json()["id"] == str(org_id)


def test_accept_invitation_unknown_token_returns_uniform_400(monkeypatch, tmp_path) -> None:
    client, _factory = _make_client(monkeypatch, tmp_path)

    response = client.post(
        "/auth/invitations/accept",
        json={"token": "does-not-exist", "password": _VALID_PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid or expired invitation"


def test_accept_invitation_expired_token_returns_same_uniform_message(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)
    invitation_id, token = _seed_invitation(factory, org_id, ttl_seconds=3600)

    async def _expire():
        async with factory() as session:
            record = await session.get(UserInvitationRecord, invitation_id)
            assert record is not None
            record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(_expire())

    response = client.post(
        "/auth/invitations/accept",
        json={"token": token, "password": _VALID_PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid or expired invitation"

    unknown_response = client.post(
        "/auth/invitations/accept",
        json={"token": "totally-unknown-token", "password": _VALID_PASSWORD},
    )
    assert unknown_response.json()["detail"] == response.json()["detail"]


def test_accept_invitation_already_accepted_cannot_be_reused(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)
    _invitation_id, token = _seed_invitation(factory, org_id)

    first = client.post(
        "/auth/invitations/accept",
        json={"token": token, "password": _VALID_PASSWORD},
    )
    assert first.status_code == 200
    assert _count_users(factory) == 1

    second = client.post(
        "/auth/invitations/accept",
        json={"token": token, "password": "another-long-password"},
    )
    assert second.status_code == 400
    assert second.json()["detail"] == "invalid or expired invitation"
    # No second (orphaned) user was created for the reused token.
    assert _count_users(factory) == 1


def test_accept_invitation_password_too_short_rejected_without_side_effects(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)
    _invitation_id, token = _seed_invitation(factory, org_id)

    response = client.post(
        "/auth/invitations/accept",
        json={"token": token, "password": "short11"},
    )
    assert response.status_code == 422
    assert _count_users(factory) == 0

    async def _check_invitation_untouched():
        async with factory() as session:
            record = await session.scalar(
                select(UserInvitationRecord).where(
                    UserInvitationRecord.token_hash == hash_invitation_token(token)
                )
            )
            assert record is not None
            assert record.accepted_at is None

    asyncio.run(_check_invitation_untouched())


def test_accept_invitation_rate_limits_repeated_wrong_tokens(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MPLACAS_AUTH_LOGIN_MAX_ATTEMPTS", "2")
    client, _factory = _make_client(monkeypatch, tmp_path)

    for _ in range(2):
        response = client.post(
            "/auth/invitations/accept",
            json={"token": "guess-me", "password": _VALID_PASSWORD},
        )
        assert response.status_code == 400

    locked_response = client.post(
        "/auth/invitations/accept",
        json={"token": "guess-me", "password": _VALID_PASSWORD},
    )
    assert locked_response.status_code == 429


def test_inspect_invitation_never_creates_user_or_marks_accepted(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)
    invitation_id, token = _seed_invitation(factory, org_id, username="peek@tenant.example")

    for _ in range(3):
        response = client.post(
            "/auth/invitations/inspect",
            json={"token": token},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["username"] == "peek@tenant.example"
        assert body["role"] == "READ"
        assert body["organization_name"] == "Tenant"
        assert "expires_at" in body

    assert _count_users(factory) == 0

    async def _check_invitation():
        async with factory() as session:
            record = await session.get(UserInvitationRecord, invitation_id)
            assert record is not None
            assert record.accepted_at is None

    asyncio.run(_check_invitation())


def test_inspect_invitation_invalid_token_returns_uniform_400(monkeypatch, tmp_path) -> None:
    client, _factory = _make_client(monkeypatch, tmp_path)

    response = client.post(
        "/auth/invitations/inspect",
        json={"token": "nope"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid or expired invitation"


def test_accept_invitation_simulated_race_leaves_no_orphaned_user(
    monkeypatch, tmp_path
) -> None:
    """Two near-simultaneous ``consume`` calls for the same token: only the
    first may proceed to create a user and mark the invitation accepted; the
    second must fail cleanly with no orphaned user left behind.

    This exercises the same race ``mark_accepted``'s conditional UPDATE
    guards against in the full HTTP flow, by driving the service layer
    directly with two independent sessions sharing one token, mirroring what
    two concurrent HTTP requests would do.
    """
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)
    _invitation_id, token = _seed_invitation(factory, org_id)

    async def _race():
        async with factory() as session_a, factory() as session_b:
            invitation_a = await InvitationService(session_a).consume(token=token)
            invitation_b = await InvitationService(session_b).consume(token=token)

            from mplacas.auth.password import hash_password
            from mplacas.credentials.service import UserService

            user_a = await UserService(session_a).create(
                name=invitation_a.username,
                organization_id=invitation_a.organization_id,
                role=OperationsRole(invitation_a.role),
                password_hash=hash_password(_VALID_PASSWORD),
            )
            accepted_a = await InvitationService(session_a).mark_accepted(
                invitation_id=invitation_a.id,
                accepted_user_id=user_a.id,
            )
            await session_a.commit()
            assert accepted_a is True

            accepted_b = await InvitationService(session_b).mark_accepted(
                invitation_id=invitation_b.id,
                accepted_user_id=uuid.uuid4(),
            )
            # No user is created for session_b in this simulation (mirroring
            # the router: the user would be created before this check, and
            # rolled back by discarding the session without a commit when
            # ``mark_accepted`` returns False).
            assert accepted_b is False
            await session_b.close()

    asyncio.run(_race())

    # Only the winner's user survives; the HTTP-level reuse test above
    # confirms the router itself never leaves a second user behind.
    assert _count_users(factory) == 1

    # The full HTTP path must also refuse to reuse the now-accepted token.
    response = client.post(
        "/auth/invitations/accept",
        json={"token": token, "password": _VALID_PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid or expired invitation"
