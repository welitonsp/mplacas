from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.credentials.db_models import OperationalUserRecord
from mplacas.credentials.service import (
    CredentialError,
    CredentialService,
    UserService,
)
from mplacas.db.base import Base
from mplacas.organizations.db_models import OrganizationRecord


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_expired_credential_does_not_authenticate() -> None:
    factory = await _factory()
    async with factory() as session:
        service = CredentialService(session)
        _, valid_secret = await service.create(
            name="valida",
            role=OperationsRole.READ,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        with pytest.raises(CredentialError, match="must be in the future"):
            await service.create(
                name="ja-expirada",
                role=OperationsRole.READ,
                expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            )
        record, short_secret = await service.create(
            name="curta",
            role=OperationsRole.READ,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await session.commit()

    async with factory() as session:
        service = CredentialService(session)
        assert await service.resolve(valid_secret) is not None
        assert await service.resolve(short_secret) is not None

    async with factory() as session:
        stored = await session.get(type(record), record.id)
        assert stored is not None
        stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    async with factory() as session:
        service = CredentialService(session)
        assert await service.resolve(short_secret) is None
        assert await service.resolve(valid_secret) is not None


@pytest.mark.asyncio
async def test_deactivating_user_blocks_all_their_credentials() -> None:
    factory = await _factory()
    async with factory() as session:
        user = await UserService(session).create(name="cb-weliton")
        service = CredentialService(session)
        _, secret_one = await service.create(
            name="cred-1", role=OperationsRole.READ, user_id=user.id
        )
        _, secret_two = await service.create(
            name="cred-2", role=OperationsRole.READ, user_id=user.id
        )
        _, orphan_secret = await service.create(
            name="sem-usuario", role=OperationsRole.READ
        )
        await session.commit()

    async with factory() as session:
        service = CredentialService(session)
        assert await service.resolve(secret_one) is not None
        assert await service.resolve(secret_two) is not None

    async with factory() as session:
        deactivated = await UserService(session).deactivate(user.id)
        await session.commit()
    assert deactivated.active is False
    assert deactivated.deactivated_at is not None

    async with factory() as session:
        service = CredentialService(session)
        assert await service.resolve(secret_one) is None
        assert await service.resolve(secret_two) is None
        assert await service.resolve(orphan_secret) is not None


@pytest.mark.asyncio
async def test_user_domain_rules() -> None:
    factory = await _factory()
    async with factory() as session:
        users = UserService(session)
        with pytest.raises(CredentialError, match="name is required"):
            await users.create(name="   ")
        await users.create(name="duplicado")
        with pytest.raises(CredentialError, match="already in use"):
            await users.create(name="duplicado")
        with pytest.raises(CredentialError, match="not found"):
            await users.deactivate(uuid.uuid4())

        inactive = await users.create(name="inativo")
        await users.deactivate(inactive.id)
        with pytest.raises(CredentialError, match="is deactivated"):
            await CredentialService(session).create(
                name="para-inativo",
                role=OperationsRole.READ,
                user_id=inactive.id,
            )
        with pytest.raises(CredentialError, match="user not found"):
            await CredentialService(session).create(
                name="usuario-fantasma",
                role=OperationsRole.READ,
                user_id=uuid.uuid4(),
            )


@pytest.mark.asyncio
async def test_user_create_translates_concurrent_duplicate_integrity_error(
    monkeypatch,
) -> None:
    """Simulates the TOCTOU window between the uniqueness ``SELECT`` and the
    ``INSERT``: two concurrent requests for the same ``name`` can both pass
    the pre-check before either commits. The second one must still fail with
    the same clean ``CredentialError`` its own pre-check would have raised,
    never with a raw, unhandled ``IntegrityError`` from the database.
    """
    factory = await _factory()

    async with factory() as winner_session:
        await UserService(winner_session).create(name="corrida-toctou")
        await winner_session.commit()

    async with factory() as racer_session:
        service = UserService(racer_session)

        async def _miss_the_uniqueness_check(*args, **kwargs):
            # Pretends the pre-check ``SELECT`` ran before ``winner_session``
            # committed above, i.e. before the row existed yet.
            return None

        monkeypatch.setattr(racer_session, "scalar", _miss_the_uniqueness_check)

        with pytest.raises(CredentialError, match="already in use"):
            await service.create(name="corrida-toctou")

        # The session must remain usable after the translated error (the
        # failed flush was rolled back), not left in a broken transaction.
        monkeypatch.undo()
        assert await racer_session.scalar(
            select(OperationalUserRecord).where(
                OperationalUserRecord.name == "outro-nome-toctou"
            )
        ) is None
        await UserService(racer_session).create(name="outro-nome-toctou")
        await racer_session.commit()


def test_user_endpoints_manage_lifecycle(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-admin-key")
    monkeypatch.setenv(
        "MPLACAS_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path}/users.db",
    )
    get_settings.cache_clear()

    import mplacas.credentials.router as credentials_router
    import mplacas.db.session as db_session
    import mplacas.operations.router as operations_router
    from mplacas.main import app

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/users.db")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_prepare())
    monkeypatch.setattr(credentials_router, "SessionFactory", factory)
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(operations_router, "SessionFactory", factory)

    client = TestClient(app)
    admin = {"X-API-Key": "synthetic-admin-key"}

    assert client.post("/operations/users", json={"name": "x"}).status_code == 401

    created = client.post(
        "/operations/users", json={"name": "cb-weliton"}, headers=admin
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert created.json()["active"] is True

    credential = client.post(
        "/operations/credentials",
        json={
            "name": "cred-do-usuario",
            "role": "READ",
            "user_id": user_id,
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(days=30)
            ).isoformat(),
        },
        headers=admin,
    )
    assert credential.status_code == 201
    assert credential.json()["user_id"] == user_id
    secret = credential.json()["secret"]

    # A READ credential bound to an organization without an explicit plant
    # scope now derives its PlantScope from that organization's own plants
    # (PR-1 invariant), so it is denied on org-wide, unrestricted-only
    # endpoints such as /operations/jobs.
    jobs = client.get("/operations/jobs", headers={"X-API-Key": secret})
    assert jobs.status_code == 403

    listed = client.get("/operations/users", headers=admin)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    deactivated = client.post(
        f"/operations/users/{user_id}/deactivate", headers=admin
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False

    blocked = client.get("/operations/jobs", headers={"X-API-Key": secret})
    assert blocked.status_code == 401

    missing = client.post(
        f"/operations/users/{uuid.uuid4()}/deactivate", headers=admin
    )
    assert missing.status_code == 404

    duplicate = client.post(
        "/operations/users", json={"name": "cb-weliton"}, headers=admin
    )
    assert duplicate.status_code == 422
    assert "already in use" in duplicate.json()["detail"]

    get_settings.cache_clear()


def _prepare_user_admin_client(monkeypatch, tmp_path):
    """Build a TestClient with both the static operations key and JWT bearer
    auth configured (PR-6: org-admin bearer JWTs must now reach
    ``/operations/users``, which previously only accepted the static
    platform key)."""
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-admin-key")
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv(
        "MPLACAS_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path}/users-org-admin.db",
    )
    get_settings.cache_clear()

    import mplacas.credentials.router as credentials_router
    import mplacas.db.session as db_session
    import mplacas.operations.router as operations_router
    from mplacas.main import app

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/users-org-admin.db")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_prepare())
    monkeypatch.setattr(credentials_router, "SessionFactory", factory)
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(operations_router, "SessionFactory", factory)

    return TestClient(app), factory


def _seed_org(factory, *, name: str, slug: str) -> uuid.UUID:
    async def _seed() -> uuid.UUID:
        async with factory() as session:
            org = OrganizationRecord(name=name, slug=slug, active=True)
            session.add(org)
            await session.flush()
            await session.commit()
            return org.id

    return asyncio.run(_seed())


def test_user_endpoints_allow_org_admin_bearer_jwt(monkeypatch, tmp_path) -> None:
    """A JWT-authenticated organization ADMIN can now create/list/deactivate
    operational users for its own organization -- previously this returned
    403 because the handler called ``principal.require_unrestricted_access()``,
    which rejects every organization-scoped principal by design."""
    client, factory = _prepare_user_admin_client(monkeypatch, tmp_path)
    org_id = _seed_org(factory, name="Tenant", slug="tenant")
    admin_token = encode_access_token(uuid.uuid4(), org_id, OperationsRole.ADMIN.value)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    created = client.post(
        "/operations/users", json={"name": "cb-tenant"}, headers=admin_headers
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert created.json()["organization_id"] == str(org_id)

    listed = client.get("/operations/users", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["items"][0]["id"] == user_id

    deactivated = client.post(
        f"/operations/users/{user_id}/deactivate", headers=admin_headers
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False

    read_token = encode_access_token(uuid.uuid4(), org_id, OperationsRole.READ.value)
    read_denied = client.post(
        "/operations/users",
        json={"name": "outro"},
        headers={"Authorization": f"Bearer {read_token}"},
    )
    assert read_denied.status_code == 403


def test_user_endpoints_isolate_organizations_for_org_admin(
    monkeypatch, tmp_path
) -> None:
    """An org-admin JWT must never see or deactivate another organization's
    operational users, even though it now passes the admin authorization
    gate."""
    client, factory = _prepare_user_admin_client(monkeypatch, tmp_path)
    org_a_id = _seed_org(factory, name="Org A", slug="org-a")
    org_b_id = _seed_org(factory, name="Org B", slug="org-b")
    admin_a_token = encode_access_token(uuid.uuid4(), org_a_id, OperationsRole.ADMIN.value)
    admin_b_token = encode_access_token(uuid.uuid4(), org_b_id, OperationsRole.ADMIN.value)
    headers_a = {"Authorization": f"Bearer {admin_a_token}"}
    headers_b = {"Authorization": f"Bearer {admin_b_token}"}

    created_b = client.post(
        "/operations/users", json={"name": "cb-org-b"}, headers=headers_b
    )
    assert created_b.status_code == 201
    user_b_id = created_b.json()["id"]

    listed_a = client.get("/operations/users", headers=headers_a)
    assert listed_a.status_code == 200
    assert listed_a.json()["count"] == 0

    deactivate_from_a = client.post(
        f"/operations/users/{user_b_id}/deactivate", headers=headers_a
    )
    assert deactivate_from_a.status_code == 404
