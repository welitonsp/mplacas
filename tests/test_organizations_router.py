from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mplacas.auth.db_models import AuthSessionRecord
from mplacas.auth.session_service import AuthSessionService
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.organizations.db_models import OrganizationRecord

_TEST_ENGINES = []
_TEST_CLIENTS = []


def _make_client(monkeypatch, tmp_path):
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-admin-key")
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    monkeypatch.setenv(
        "MPLACAS_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path}/organizations.db",
    )
    get_settings.cache_clear()

    import mplacas.auth.router as auth_router
    import mplacas.db.session as db_session
    import mplacas.organizations.router as organizations_router
    from mplacas.main import app

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/organizations.db",
        poolclass=NullPool,
    )
    _TEST_ENGINES.append(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_prepare())

    monkeypatch.setattr(organizations_router, "SessionFactory", factory)
    monkeypatch.setattr(auth_router, "SessionFactory", factory)
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    client = TestClient(app)
    _TEST_CLIENTS.append(client)
    return client, factory


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    yield
    while _TEST_CLIENTS:
        _TEST_CLIENTS.pop().close()
    while _TEST_ENGINES:
        asyncio.run(_TEST_ENGINES.pop().dispose())
    get_settings.cache_clear()


def test_post_organizations_by_platform_creates_org_and_bootstrap_invitation(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)

    response = client.post(
        "/organizations",
        json={
            "name": "Acme Solar",
            "slug": "acme-solar",
            "admin_username": "admin@acme.example",
        },
        headers={"X-API-Key": "synthetic-admin-key"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme Solar"
    assert body["slug"] == "acme-solar"
    assert body["active"] is True
    assert body["telegram_chat_id"] is None

    invitation = body["bootstrap_invitation"]
    assert invitation["username"] == "admin@acme.example"
    assert invitation["role"] == "ADMIN"
    assert "token" in invitation and invitation["token"]
    assert "token_notice" in invitation

    import asyncio

    async def _fetch():
        async with factory() as session:
            return await session.scalar(
                select(OrganizationRecord).where(OrganizationRecord.slug == "acme-solar")
            )

    record = asyncio.run(_fetch())
    assert record is not None


def test_post_organizations_by_org_admin_is_forbidden(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)

    import asyncio

    async def _seed_org():
        async with factory() as session:
            org = OrganizationRecord(name="Tenant", slug="tenant", active=True)
            session.add(org)
            await session.flush()
            await session.commit()
            return org.id

    org_id = asyncio.run(_seed_org())
    token = encode_access_token(uuid.uuid4(), org_id, OperationsRole.ADMIN.value)

    response = client.post(
        "/organizations",
        json={
            "name": "Other Org",
            "slug": "other-org",
            "admin_username": "admin@other.example",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_post_organizations_duplicate_slug_returns_409(monkeypatch, tmp_path) -> None:
    client, _factory = _make_client(monkeypatch, tmp_path)

    payload = {
        "name": "Acme Solar",
        "slug": "acme-solar",
        "admin_username": "admin@acme.example",
    }
    first = client.post(
        "/organizations", json=payload, headers={"X-API-Key": "synthetic-admin-key"}
    )
    assert first.status_code == 201

    second = client.post(
        "/organizations",
        json={**payload, "admin_username": "someone-else@acme.example"},
        headers={"X-API-Key": "synthetic-admin-key"},
    )
    assert second.status_code == 409


def test_post_organizations_invalid_admin_username_rolls_back_organization(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)

    response = client.post(
        "/organizations",
        json={
            "name": "Acme Solar",
            "slug": "acme-solar",
            "admin_username": "not-an-email",
        },
        headers={"X-API-Key": "synthetic-admin-key"},
    )
    assert response.status_code == 422

    import asyncio

    async def _fetch():
        async with factory() as session:
            return await session.scalar(
                select(OrganizationRecord).where(OrganizationRecord.slug == "acme-solar")
            )

    assert asyncio.run(_fetch()) is None


def test_get_organizations_platform_lists_all_org_lists_only_own(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)

    import asyncio

    async def _seed_two_orgs():
        async with factory() as session:
            org_a = OrganizationRecord(name="Org A", slug="org-a", active=True)
            org_b = OrganizationRecord(name="Org B", slug="org-b", active=True)
            session.add(org_a)
            session.add(org_b)
            await session.flush()
            await session.commit()
            return org_a.id, org_b.id

    org_a_id, org_b_id = asyncio.run(_seed_two_orgs())

    platform_response = client.get(
        "/organizations", headers={"X-API-Key": "synthetic-admin-key"}
    )
    assert platform_response.status_code == 200
    assert platform_response.json()["count"] == 2

    token = encode_access_token(uuid.uuid4(), org_a_id, OperationsRole.ADMIN.value)
    org_response = client.get(
        "/organizations", headers={"Authorization": f"Bearer {token}"}
    )
    assert org_response.status_code == 200
    body = org_response.json()
    assert body["count"] == 1
    assert body["items"][0]["id"] == str(org_a_id)
    assert org_b_id  # sanity: fixture created, just not visible to org A


def test_get_organization_by_id_other_org_returns_404(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)

    import asyncio

    async def _seed_two_orgs():
        async with factory() as session:
            org_a = OrganizationRecord(name="Org A", slug="org-a", active=True)
            org_b = OrganizationRecord(name="Org B", slug="org-b", active=True)
            session.add(org_a)
            session.add(org_b)
            await session.flush()
            await session.commit()
            return org_a.id, org_b.id

    org_a_id, org_b_id = asyncio.run(_seed_two_orgs())
    token = encode_access_token(uuid.uuid4(), org_a_id, OperationsRole.ADMIN.value)

    own = client.get(
        f"/organizations/{org_a_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert own.status_code == 200

    other = client.get(
        f"/organizations/{org_b_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert other.status_code == 404

    missing = client.get(
        f"/organizations/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"}
    )
    assert missing.status_code == 404

    platform_can_see_any = client.get(
        f"/organizations/{org_b_id}", headers={"X-API-Key": "synthetic-admin-key"}
    )
    assert platform_can_see_any.status_code == 200


def test_deactivate_organization_blocks_login_and_revokes_sessions(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)

    import asyncio

    from mplacas.auth.password import hash_password
    from mplacas.credentials.db_models import OperationalUserRecord

    async def _seed():
        async with factory() as session:
            org = OrganizationRecord(name="Tenant", slug="tenant", active=True)
            session.add(org)
            await session.flush()
            user = OperationalUserRecord(
                name="user@tenant.example",
                role=OperationsRole.ADMIN.value,
                active=True,
                organization_id=org.id,
                password_hash=hash_password("s3cret-password"),
            )
            session.add(user)
            await session.flush()
            refresh_token = await AuthSessionService(session).create(
                user_id=user.id,
                organization_id=org.id,
                ttl_seconds=3600,
            )
            await session.commit()
            return org.id, refresh_token

    org_id, refresh_token = asyncio.run(_seed())

    deactivate_response = client.post(
        f"/organizations/{org_id}/deactivate",
        headers={"X-API-Key": "synthetic-admin-key"},
    )
    assert deactivate_response.status_code == 200
    body = deactivate_response.json()
    assert body["active"] is False

    async def _check():
        async with factory() as session:
            record = await session.get(OrganizationRecord, org_id)
            assert record is not None
            assert record.active is False
            assert record.deactivated_at is not None

            sessions = list(
                await session.scalars(
                    select(AuthSessionRecord).where(
                        AuthSessionRecord.organization_id == org_id
                    )
                )
            )
            assert sessions
            assert all(not s.active for s in sessions)

    asyncio.run(_check())

    login_response = client.post(
        "/auth/login",
        json={"username": "user@tenant.example", "password": "s3cret-password"},
    )
    assert login_response.status_code == 401

    refresh_response = client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refresh_response.status_code == 401


def test_post_organizations_requires_platform_principal_not_read(
    monkeypatch, tmp_path
) -> None:
    client, _factory = _make_client(monkeypatch, tmp_path)

    unauthorized = client.post(
        "/organizations",
        json={"name": "X", "slug": "x", "admin_username": "a@b.com"},
    )
    assert unauthorized.status_code == 401


def _seed_org(factory) -> uuid.UUID:
    import asyncio

    slug = f"tenant-{uuid.uuid4().hex[:12]}"

    async def _seed() -> uuid.UUID:
        async with factory() as session:
            org = OrganizationRecord(name="Tenant", slug=slug, active=True)
            session.add(org)
            await session.flush()
            await session.commit()
            return org.id

    return asyncio.run(_seed())


def _admin_headers(org_id: uuid.UUID) -> dict[str, str]:
    token = encode_access_token(uuid.uuid4(), org_id, OperationsRole.ADMIN.value)
    return {"Authorization": f"Bearer {token}"}


def _read_headers(org_id: uuid.UUID) -> dict[str, str]:
    token = encode_access_token(uuid.uuid4(), org_id, OperationsRole.READ.value)
    return {"Authorization": f"Bearer {token}"}


def test_post_invitations_creates_for_own_organization_ignoring_body_org_id(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)

    response = client.post(
        "/organizations/invitations",
        json={
            "username": "new-user@tenant.example",
            "role": "READ",
            # Hypothetical attempt to target another organization: must be
            # ignored, since ``InvitationCreateRequest`` has no such field.
            "organization_id": str(uuid.uuid4()),
        },
        headers=_admin_headers(org_id),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "new-user@tenant.example"
    assert body["role"] == "READ"
    assert "token" in body and body["token"]
    assert body["token_notice"]

    import asyncio

    from mplacas.organizations.invitation_db_models import UserInvitationRecord

    async def _fetch():
        async with factory() as session:
            return await session.get(UserInvitationRecord, uuid.UUID(body["id"]))

    record = asyncio.run(_fetch())
    assert record is not None
    assert record.organization_id == org_id


def test_post_invitations_requires_admin_not_read(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)

    response = client.post(
        "/organizations/invitations",
        json={"username": "new-user@tenant.example", "role": "READ"},
        headers=_read_headers(org_id),
    )
    assert response.status_code == 403


def test_get_invitations_never_includes_token_or_hash(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)

    create_response = client.post(
        "/organizations/invitations",
        json={"username": "new-user@tenant.example", "role": "READ"},
        headers=_admin_headers(org_id),
    )
    assert create_response.status_code == 201

    list_response = client.get(
        "/organizations/invitations", headers=_admin_headers(org_id)
    )
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    keys = set(items[0].keys())
    assert "token" not in keys
    assert "token_hash" not in keys


def test_get_invitations_derives_status_for_all_four_cases(
    monkeypatch, tmp_path
) -> None:
    import asyncio
    from datetime import datetime, timedelta, timezone

    from mplacas.organizations.invitation_db_models import UserInvitationRecord
    from mplacas.organizations.invitation_service import hash_invitation_token

    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)

    now = datetime.now(timezone.utc)

    async def _seed_invitations() -> None:
        async with factory() as session:
            pending = UserInvitationRecord(
                organization_id=org_id,
                username="pending@tenant.example",
                role=OperationsRole.READ.value,
                token_hash=hash_invitation_token("pending-token"),
                expires_at=now + timedelta(days=1),
            )
            accepted = UserInvitationRecord(
                organization_id=org_id,
                username="accepted@tenant.example",
                role=OperationsRole.READ.value,
                token_hash=hash_invitation_token("accepted-token"),
                expires_at=now + timedelta(days=1),
                accepted_at=now,
            )
            revoked = UserInvitationRecord(
                organization_id=org_id,
                username="revoked@tenant.example",
                role=OperationsRole.READ.value,
                token_hash=hash_invitation_token("revoked-token"),
                expires_at=now + timedelta(days=1),
                revoked_at=now,
            )
            expired = UserInvitationRecord(
                organization_id=org_id,
                username="expired@tenant.example",
                role=OperationsRole.READ.value,
                token_hash=hash_invitation_token("expired-token"),
                expires_at=now - timedelta(days=1),
            )
            session.add_all([pending, accepted, revoked, expired])
            await session.flush()
            await session.commit()

    asyncio.run(_seed_invitations())

    response = client.get(
        "/organizations/invitations", headers=_admin_headers(org_id)
    )
    assert response.status_code == 200
    by_username = {item["username"]: item["status"] for item in response.json()["items"]}
    assert by_username["pending@tenant.example"] == "PENDING"
    assert by_username["accepted@tenant.example"] == "ACCEPTED"
    assert by_username["revoked@tenant.example"] == "REVOKED"
    assert by_username["expired@tenant.example"] == "EXPIRED"


def test_invitations_isolated_between_organizations(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_a_id = _seed_org(factory)
    org_b_id = _seed_org(factory)

    create_response = client.post(
        "/organizations/invitations",
        json={"username": "user@org-b.example", "role": "READ"},
        headers=_admin_headers(org_b_id),
    )
    assert create_response.status_code == 201
    invitation_id = create_response.json()["id"]

    list_response = client.get(
        "/organizations/invitations", headers=_admin_headers(org_a_id)
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"] == []

    revoke_response = client.post(
        f"/organizations/invitations/{invitation_id}/revoke",
        headers=_admin_headers(org_a_id),
    )
    assert revoke_response.status_code == 404


def test_revoke_invitation_marks_revoked_and_updates_status(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)

    create_response = client.post(
        "/organizations/invitations",
        json={"username": "user@tenant.example", "role": "READ"},
        headers=_admin_headers(org_id),
    )
    invitation_id = create_response.json()["id"]

    revoke_response = client.post(
        f"/organizations/invitations/{invitation_id}/revoke",
        headers=_admin_headers(org_id),
    )
    assert revoke_response.status_code == 200
    assert revoke_response.json()["status"] == "REVOKED"

    list_response = client.get(
        "/organizations/invitations", headers=_admin_headers(org_id)
    )
    items = list_response.json()["items"]
    assert items[0]["status"] == "REVOKED"


def test_revoke_invitation_unknown_id_returns_404(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)

    response = client.post(
        f"/organizations/invitations/{uuid.uuid4()}/revoke",
        headers=_admin_headers(org_id),
    )
    assert response.status_code == 404


def test_patch_organization_by_own_org_admin_updates_telegram_fields(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)

    response = client.patch(
        f"/organizations/{org_id}",
        json={"telegram_chat_id": 123456, "telegram_allowed_user_id": 789},
        headers=_admin_headers(org_id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["telegram_chat_id"] == 123456
    assert body["telegram_allowed_user_id"] == 789

    import asyncio

    async def _fetch():
        async with factory() as session:
            return await session.get(OrganizationRecord, org_id)

    record = asyncio.run(_fetch())
    assert record is not None
    assert record.telegram_chat_id == 123456
    assert record.telegram_allowed_user_id == 789


def test_patch_organization_by_other_org_admin_returns_404(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_a_id = _seed_org(factory)
    org_b_id = _seed_org(factory)

    response = client.patch(
        f"/organizations/{org_b_id}",
        json={"telegram_chat_id": 123456},
        headers=_admin_headers(org_a_id),
    )
    assert response.status_code == 404

    import asyncio

    async def _fetch():
        async with factory() as session:
            return await session.get(OrganizationRecord, org_b_id)

    record = asyncio.run(_fetch())
    assert record is not None
    assert record.telegram_chat_id is None


def test_patch_organization_by_platform_updates_any_organization(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)

    response = client.patch(
        f"/organizations/{org_id}",
        json={"telegram_chat_id": 555},
        headers={"X-API-Key": "synthetic-admin-key"},
    )
    assert response.status_code == 200
    assert response.json()["telegram_chat_id"] == 555


def test_patch_organization_partial_update_does_not_clear_other_field(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)

    first = client.patch(
        f"/organizations/{org_id}",
        json={"telegram_chat_id": 111, "telegram_allowed_user_id": 222},
        headers=_admin_headers(org_id),
    )
    assert first.status_code == 200

    second = client.patch(
        f"/organizations/{org_id}",
        json={"telegram_chat_id": 333},
        headers=_admin_headers(org_id),
    )
    assert second.status_code == 200
    body = second.json()
    assert body["telegram_chat_id"] == 333
    assert body["telegram_allowed_user_id"] == 222


def test_patch_organization_explicit_null_unlinks_field(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)

    first = client.patch(
        f"/organizations/{org_id}",
        json={"telegram_chat_id": 111, "telegram_allowed_user_id": 222},
        headers=_admin_headers(org_id),
    )
    assert first.status_code == 200

    second = client.patch(
        f"/organizations/{org_id}",
        json={"telegram_chat_id": None},
        headers=_admin_headers(org_id),
    )
    assert second.status_code == 200
    body = second.json()
    assert body["telegram_chat_id"] is None
    assert body["telegram_allowed_user_id"] == 222


def test_patch_organization_duplicate_telegram_chat_id_returns_409_and_session_stays_usable(
    monkeypatch, tmp_path
) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_a_id = _seed_org(factory)
    org_b_id = _seed_org(factory)

    linked = client.patch(
        f"/organizations/{org_a_id}",
        json={"telegram_chat_id": 999},
        headers=_admin_headers(org_a_id),
    )
    assert linked.status_code == 200
    assert linked.json()["telegram_chat_id"] == 999

    conflict = client.patch(
        f"/organizations/{org_b_id}",
        json={"telegram_chat_id": 999},
        headers=_admin_headers(org_b_id),
    )
    assert conflict.status_code == 409

    import asyncio

    async def _fetch(org_id):
        async with factory() as session:
            return await session.get(OrganizationRecord, org_id)

    record_b = asyncio.run(_fetch(org_b_id))
    assert record_b is not None
    assert record_b.telegram_chat_id is None

    # The IntegrityError caught above rolled back its own session, not the
    # process/engine: a fresh PATCH against the same organization right after
    # must still work, proving no connection/session was left unusable.
    recovered = client.patch(
        f"/organizations/{org_b_id}",
        json={"telegram_chat_id": 1000},
        headers=_admin_headers(org_b_id),
    )
    assert recovered.status_code == 200
    assert recovered.json()["telegram_chat_id"] == 1000

    record_b_after = asyncio.run(_fetch(org_b_id))
    assert record_b_after is not None
    assert record_b_after.telegram_chat_id == 1000


def test_patch_organization_requires_admin_not_read(monkeypatch, tmp_path) -> None:
    client, factory = _make_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory)

    response = client.patch(
        f"/organizations/{org_id}",
        json={"telegram_chat_id": 123},
        headers=_read_headers(org_id),
    )
    assert response.status_code == 403
