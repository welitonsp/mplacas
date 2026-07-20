from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.core.config import get_settings
from mplacas.core.security import OperationsRole
from mplacas.credentials.service import (
    CredentialError,
    CredentialService,
    UserService,
)
from mplacas.db.base import Base


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

    jobs = client.get("/operations/jobs", headers={"X-API-Key": secret})
    assert jobs.status_code == 200

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

    get_settings.cache_clear()
