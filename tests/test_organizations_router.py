from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.auth.db_models import AuthSessionRecord
from mplacas.auth.session_service import AuthSessionService
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.organizations.db_models import OrganizationRecord


def _make_client(monkeypatch, tmp_path):
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-admin-key")
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv(
        "MPLACAS_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path}/organizations.db",
    )
    get_settings.cache_clear()

    import mplacas.auth.router as auth_router
    import mplacas.db.session as db_session
    import mplacas.organizations.router as organizations_router
    from mplacas.main import app

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/organizations.db")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    import asyncio

    asyncio.run(_prepare())

    monkeypatch.setattr(organizations_router, "SessionFactory", factory)
    monkeypatch.setattr(auth_router, "SessionFactory", factory)
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    return TestClient(app), factory


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    yield
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
