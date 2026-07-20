from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.core.config import get_settings
from mplacas.core.security import OperationsRole
from mplacas.credentials.db_models import ApiCredentialRecord
from mplacas.credentials.service import (
    CredentialError,
    CredentialService,
    hash_secret,
)
from mplacas.db.base import Base

PLANT_A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
PLANT_B = uuid.UUID("00000000-0000-0000-0000-00000000000b")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_create_stores_hash_only_and_resolves_principal() -> None:
    factory = await _factory()
    async with factory() as session:
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

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/credentials.db")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    import asyncio

    asyncio.run(_prepare())
    import mplacas.db.session as db_session
    import mplacas.operations.router as operations_router

    monkeypatch.setattr(credentials_router, "SessionFactory", factory)
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(operations_router, "SessionFactory", factory)
    assert security is not None

    client = TestClient(app)

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

    unrestricted = client.post(
        "/operations/credentials",
        json={"name": "leitor-geral", "role": "READ"},
        headers={"X-API-Key": "synthetic-admin-key"},
    )
    assert unrestricted.status_code == 201
    db_secret = unrestricted.json()["secret"]

    jobs_with_db_credential = client.get(
        "/operations/jobs",
        headers={"X-API-Key": db_secret},
    )
    assert jobs_with_db_credential.status_code == 200

    admin_denied_for_db_read = client.post(
        "/operations/credentials",
        json={"name": "negada", "role": "READ"},
        headers={"X-API-Key": db_secret},
    )
    assert admin_denied_for_db_read.status_code == 401

    revoke_db_credential = client.post(
        f"/operations/credentials/{unrestricted.json()['id']}/revoke",
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
