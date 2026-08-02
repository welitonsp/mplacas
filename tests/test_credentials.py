from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.credentials.db_models import ApiCredentialRecord
from mplacas.credentials.service import (
    CredentialError,
    CredentialService,
    hash_secret,
)
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord

PLANT_A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
PLANT_B = uuid.UUID("00000000-0000-0000-0000-00000000000b")
_TEST_ENGINES: list[AsyncEngine] = []
_TEST_CLIENTS: list[TestClient] = []


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _TEST_ENGINES.append(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _dispose_test_engines():
    yield
    while _TEST_CLIENTS:
        _TEST_CLIENTS.pop().close()
    while _TEST_ENGINES:
        await _TEST_ENGINES.pop().dispose()


async def _ensure_default_organization(session: AsyncSession) -> uuid.UUID:
    record = await session.get(OrganizationRecord, DEFAULT_ORGANIZATION_ID)
    if record is None:
        record = OrganizationRecord(
            id=DEFAULT_ORGANIZATION_ID,
            name="Default",
            slug="default",
            active=True,
        )
        session.add(record)
        await session.flush()
    return record.id


async def _ensure_plants(session: AsyncSession, *plant_ids: uuid.UUID) -> uuid.UUID:
    organization_id = await _ensure_default_organization(session)
    for plant_id in plant_ids:
        existing = await session.get(Plant, plant_id)
        if existing is None:
            session.add(
                Plant(
                    id=plant_id,
                    organization_id=organization_id,
                    name=f"Plant {plant_id}",
                )
            )
    await session.flush()
    return organization_id


@pytest.mark.asyncio
async def test_create_stores_hash_only_and_resolves_principal() -> None:
    factory = await _factory()
    async with factory() as session:
        await _ensure_plants(session, PLANT_A)
        record, secret = await CredentialService(session).create(
            name="leitor-usina-a",
            role=OperationsRole.READ,
            plant_ids=frozenset({PLANT_A}),
        )
        await session.commit()

    assert secret not in (record.key_hash, record.name)
    assert record.key_hash == hash_secret(secret)
    assert len(record.key_hash) == 64

    async with factory() as session:
        principal = await CredentialService(session).resolve(secret)
    assert principal is not None
    assert principal.role is OperationsRole.READ
    assert principal.credential_id == f"credential:{record.id}"
    assert principal.plant_scope.allows(PLANT_A)
    assert not principal.plant_scope.allows(PLANT_B)


@pytest.mark.asyncio
async def test_org_bound_unscoped_credential_is_restricted_to_org_plants() -> None:
    """A persisted credential with organization_id and no explicit plant_ids
    must never resolve to an unrestricted PlantScope; it is derived from the
    organization's own plants instead (see ADR-052 / PR-1)."""
    factory = await _factory()
    async with factory() as session:
        await _ensure_plants(session, PLANT_A)
        _, secret = await CredentialService(session).create(
            name="leitor-org",
            role=OperationsRole.READ,
        )
        await session.commit()

    async with factory() as session:
        principal = await CredentialService(session).resolve(secret)

    assert principal is not None
    assert principal.organization_id is not None
    assert principal.plant_scope.is_restricted is True
    assert principal.plant_scope.allows(PLANT_A) is True
    assert principal.plant_scope.allows(PLANT_B) is False
    principal.require_plant_access(PLANT_A)
    with pytest.raises(HTTPException) as exc_info:
        principal.require_plant_access(PLANT_B)
    assert exc_info.value.status_code == 404
    with pytest.raises(HTTPException) as global_error:
        principal.require_unrestricted_access()
    assert global_error.value.status_code == 403


@pytest.mark.asyncio
async def test_org_bound_admin_credential_without_plants_is_deny_all() -> None:
    """An organization with no plants yet must deny access rather than grant
    unrestricted access to an ADMIN credential."""
    factory = await _factory()
    async with factory() as session:
        organization_id = await _ensure_default_organization(session)
        _, secret = await CredentialService(session).create(
            name="admin-sem-usinas",
            role=OperationsRole.ADMIN,
            organization_id=organization_id,
        )
        await session.commit()

    async with factory() as session:
        principal = await CredentialService(session).resolve(secret)

    assert principal is not None
    assert principal.organization_id is not None
    assert principal.plant_scope.is_restricted is True
    assert principal.plant_scope.allows(PLANT_A) is False


@pytest.mark.asyncio
async def test_create_rejects_plant_scope_outside_organization() -> None:
    factory = await _factory()
    other_org_id = uuid.UUID("00000000-0000-0000-0000-0000000000c0")
    async with factory() as session:
        organization_id = await _ensure_plants(session, PLANT_A)
        session.add(
            OrganizationRecord(
                id=other_org_id,
                name="Other",
                slug="other",
                active=True,
            )
        )
        session.add(
            Plant(
                id=PLANT_B,
                organization_id=other_org_id,
                name="Other plant",
            )
        )
        await session.flush()

        with pytest.raises(CredentialError, match="outside this organization"):
            await CredentialService(session).create(
                name="escopo-invalido",
                role=OperationsRole.READ,
                organization_id=organization_id,
                plant_ids=frozenset({PLANT_B}),
            )


@pytest.mark.asyncio
async def test_resolve_rejects_wrong_secret_and_revoked_credential() -> None:
    factory = await _factory()
    async with factory() as session:
        service = CredentialService(session)
        record, secret = await service.create(name="revogavel", role=OperationsRole.READ)
        await session.commit()

    async with factory() as session:
        assert await CredentialService(session).resolve("segredo-errado") is None
        assert await CredentialService(session).resolve("") is None

    async with factory() as session:
        service = CredentialService(session)
        revoked = await service.revoke(record.id)
        await session.commit()
    assert revoked.active is False
    assert revoked.revoked_at is not None

    async with factory() as session:
        assert await CredentialService(session).resolve(secret) is None


@pytest.mark.asyncio
async def test_create_enforces_domain_rules() -> None:
    factory = await _factory()
    async with factory() as session:
        await _ensure_plants(session, PLANT_A)
        service = CredentialService(session)
        with pytest.raises(CredentialError, match="name is required"):
            await service.create(name="   ", role=OperationsRole.READ)
        with pytest.raises(CredentialError, match="at least one plant"):
            await service.create(
                name="vazio",
                role=OperationsRole.READ,
                plant_ids=frozenset(),
            )
        with pytest.raises(CredentialError, match="cannot be plant-restricted"):
            await service.create(
                name="admin-restrito",
                role=OperationsRole.ADMIN,
                plant_ids=frozenset({PLANT_A}),
            )
        await service.create(name="duplicada", role=OperationsRole.READ)
        with pytest.raises(CredentialError, match="already in use"):
            await service.create(name="duplicada", role=OperationsRole.READ)


@pytest.mark.asyncio
async def test_revoke_missing_credential_raises() -> None:
    factory = await _factory()
    async with factory() as session:
        with pytest.raises(CredentialError, match="not found"):
            await CredentialService(session).revoke(uuid.uuid4())


def test_credential_endpoints_require_admin_and_return_secret_once(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-admin-key")
    monkeypatch.setenv(
        "MPLACAS_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path}/credentials.db",
    )
    get_settings.cache_clear()

    import mplacas.core.security as security
    import mplacas.credentials.router as credentials_router
    from mplacas.main import app

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/credentials.db",
        poolclass=NullPool,
    )
    _TEST_ENGINES.append(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            await _ensure_plants(session, PLANT_A)
            await session.commit()

    import asyncio

    asyncio.run(_prepare())
    import mplacas.db.session as db_session
    import mplacas.operations.router as operations_router

    monkeypatch.setattr(credentials_router, "SessionFactory", factory)
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(operations_router, "SessionFactory", factory)
    assert security is not None

    client = TestClient(app)
    _TEST_CLIENTS.append(client)

    unauthorized = client.post(
        "/operations/credentials",
        json={"name": "leitor", "role": "READ"},
    )
    assert unauthorized.status_code == 401

    created = client.post(
        "/operations/credentials",
        json={"name": "leitor", "role": "READ", "plant_ids": [str(PLANT_A)]},
        headers={"X-API-Key": "synthetic-admin-key"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["role"] == "READ"
    assert body["plant_ids"] == [str(PLANT_A)]
    assert "secret" in body
    secret = body["secret"]

    listed = client.get(
        "/operations/credentials",
        headers={"X-API-Key": "synthetic-admin-key"},
    )
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert "secret" not in listed.json()["items"][0]
    assert "key_hash" not in listed.json()["items"][0]

    revoked = client.post(
        f"/operations/credentials/{body['id']}/revoke",
        headers={"X-API-Key": "synthetic-admin-key"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["active"] is False

    read_denied = client.post(
        "/operations/credentials",
        json={"name": "outra", "role": "READ"},
        headers={"X-API-Key": secret},
    )
    assert read_denied.status_code == 401

    org_scoped = client.post(
        "/operations/credentials",
        json={"name": "leitor-geral", "role": "READ"},
        headers={"X-API-Key": "synthetic-admin-key"},
    )
    assert org_scoped.status_code == 201
    db_secret = org_scoped.json()["secret"]

    # An org-bound READ credential without an explicit plant scope now
    # resolves to that organization's own plants (PR-1 invariant) instead of
    # UNRESTRICTED_PLANT_SCOPE, so it can no longer reach org-wide,
    # unrestricted-only endpoints such as /operations/jobs.
    jobs_with_db_credential = client.get(
        "/operations/jobs",
        headers={"X-API-Key": db_secret},
    )
    assert jobs_with_db_credential.status_code == 403

    admin_denied_for_db_read = client.post(
        "/operations/credentials",
        json={"name": "negada", "role": "READ"},
        headers={"X-API-Key": db_secret},
    )
    assert admin_denied_for_db_read.status_code == 401

    revoke_db_credential = client.post(
        f"/operations/credentials/{org_scoped.json()['id']}/revoke",
        headers={"X-API-Key": "synthetic-admin-key"},
    )
    assert revoke_db_credential.status_code == 200

    jobs_after_revoke = client.get(
        "/operations/jobs",
        headers={"X-API-Key": db_secret},
    )
    assert jobs_after_revoke.status_code == 401

    async def _hash_still_only_storage() -> None:
        async with factory() as session:
            record = await session.get(
                ApiCredentialRecord, uuid.UUID(body["id"])
            )
            assert record is not None
            assert secret not in record.key_hash

    asyncio.run(_hash_still_only_storage())

    get_settings.cache_clear()


def _prepare_credential_admin_client(monkeypatch, tmp_path):
    """Build a TestClient wired to a fresh sqlite db, with both the static
    operations key and JWT bearer auth configured (PR-6: org-admin bearer
    JWTs must now reach ``/operations/credentials``/``/operations/users``,
    which previously only accepted the static platform key)."""
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-admin-key")
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    monkeypatch.setenv(
        "MPLACAS_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path}/credentials-org-admin.db",
    )
    get_settings.cache_clear()

    import asyncio

    import mplacas.credentials.router as credentials_router
    import mplacas.db.session as db_session
    import mplacas.operations.router as operations_router
    from mplacas.main import app

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/credentials-org-admin.db",
        poolclass=NullPool,
    )
    _TEST_ENGINES.append(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_prepare())
    monkeypatch.setattr(credentials_router, "SessionFactory", factory)
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(operations_router, "SessionFactory", factory)

    client = TestClient(app)
    _TEST_CLIENTS.append(client)
    return client, factory


def _seed_org_with_plant(factory, *, name: str, slug: str, plant_id: uuid.UUID) -> uuid.UUID:
    import asyncio

    async def _seed() -> uuid.UUID:
        async with factory() as session:
            org = OrganizationRecord(name=name, slug=slug, active=True)
            session.add(org)
            await session.flush()
            session.add(Plant(id=plant_id, organization_id=org.id, name=f"Plant {plant_id}"))
            await session.flush()
            await session.commit()
            return org.id

    return asyncio.run(_seed())


def test_credential_endpoints_allow_org_admin_bearer_jwt(monkeypatch, tmp_path) -> None:
    """A JWT-authenticated organization ADMIN can now create/list/revoke
    credentials for its own organization -- previously this returned 403
    because the handler called ``principal.require_unrestricted_access()``,
    which rejects every organization-scoped principal by design."""
    client, factory = _prepare_credential_admin_client(monkeypatch, tmp_path)
    org_id = _seed_org_with_plant(
        factory, name="Tenant", slug="tenant", plant_id=PLANT_A
    )
    admin_token = encode_access_token(uuid.uuid4(), org_id, OperationsRole.ADMIN.value)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    created = client.post(
        "/operations/credentials",
        json={"name": "leitor-tenant", "role": "READ", "plant_ids": [str(PLANT_A)]},
        headers=admin_headers,
    )
    assert created.status_code == 201
    credential_id = created.json()["id"]
    assert created.json()["organization_id"] == str(org_id)

    listed = client.get("/operations/credentials", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["items"][0]["id"] == credential_id

    revoked = client.post(
        f"/operations/credentials/{credential_id}/revoke", headers=admin_headers
    )
    assert revoked.status_code == 200
    assert revoked.json()["active"] is False

    read_token = encode_access_token(uuid.uuid4(), org_id, OperationsRole.READ.value)
    read_denied = client.post(
        "/operations/credentials",
        json={"name": "outra", "role": "READ"},
        headers={"Authorization": f"Bearer {read_token}"},
    )
    assert read_denied.status_code == 403


def test_credential_endpoints_isolate_organizations_for_org_admin(
    monkeypatch, tmp_path
) -> None:
    """An org-admin JWT must never see or revoke another organization's
    credentials, even though it now passes the admin authorization gate."""
    client, factory = _prepare_credential_admin_client(monkeypatch, tmp_path)
    org_a_id = _seed_org_with_plant(
        factory, name="Org A", slug="org-a", plant_id=PLANT_A
    )
    org_b_id = _seed_org_with_plant(
        factory, name="Org B", slug="org-b", plant_id=PLANT_B
    )
    admin_a_token = encode_access_token(uuid.uuid4(), org_a_id, OperationsRole.ADMIN.value)
    admin_b_token = encode_access_token(uuid.uuid4(), org_b_id, OperationsRole.ADMIN.value)
    headers_a = {"Authorization": f"Bearer {admin_a_token}"}
    headers_b = {"Authorization": f"Bearer {admin_b_token}"}

    created_b = client.post(
        "/operations/credentials",
        json={"name": "leitor-b", "role": "READ", "plant_ids": [str(PLANT_B)]},
        headers=headers_b,
    )
    assert created_b.status_code == 201
    credential_b_id = created_b.json()["id"]

    listed_a = client.get("/operations/credentials", headers=headers_a)
    assert listed_a.status_code == 200
    assert listed_a.json()["count"] == 0

    revoke_from_a = client.post(
        f"/operations/credentials/{credential_b_id}/revoke", headers=headers_a
    )
    assert revoke_from_a.status_code == 404

    # The static platform key must keep behaving exactly as before: it can
    # still see and manage credentials across the (single, in this fixture)
    # ambiguous-organization scenario is avoided by using each org's own
    # admin token above; the static key path itself is covered by
    # ``test_credential_endpoints_require_admin_and_return_secret_once``.
