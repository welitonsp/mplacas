"""PR-1: every OperationsPrincipal with organization_id set must carry a
restricted PlantScope, regardless of which authentication path produced it.

Covers the three sources of OperationsPrincipal that carry organization_id:
  - JWT bearer tokens (core.security._authenticate_bearer)
  - persisted ADMIN credentials without an explicit plant scope
  - persisted READ credentials with an explicit plant scope
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
from mplacas.core import security
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.credentials.service import CredentialService
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.organizations.db_models import OrganizationRecord

PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_org_with_plant(factory) -> uuid.UUID:
    async with factory() as session:
        organization_id = uuid.uuid4()
        session.add(
            OrganizationRecord(
                id=organization_id,
                name="Tenant",
                slug=f"tenant-{organization_id.hex[:8]}",
                active=True,
            )
        )
        session.add(
            Plant(id=PLANT_A, organization_id=organization_id, name="Plant A")
        )
        await session.flush()
        await session.commit()
        return organization_id


@pytest.mark.asyncio
async def test_jwt_bearer_principal_is_org_restricted(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret")
    get_settings.cache_clear()
    factory = await _factory()
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    organization_id = await _seed_org_with_plant(factory)
    token = encode_access_token(uuid.uuid4(), organization_id, OperationsRole.READ.value)

    principal = await security._authenticate_bearer(token, require_admin=False)

    assert principal is not None
    assert principal.organization_id is not None
    assert principal.plant_scope.is_restricted is True

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_persisted_admin_credential_without_plant_ids_is_org_restricted() -> None:
    factory = await _factory()
    organization_id = await _seed_org_with_plant(factory)

    async with factory() as session:
        _, secret = await CredentialService(session).create(
            name="admin-org",
            role=OperationsRole.ADMIN,
            organization_id=organization_id,
        )
        await session.commit()

    async with factory() as session:
        principal = await CredentialService(session).resolve(secret)

    assert principal is not None
    assert principal.organization_id is not None
    assert principal.plant_scope.is_restricted is True


@pytest.mark.asyncio
async def test_persisted_read_credential_with_plant_ids_is_org_restricted() -> None:
    factory = await _factory()
    organization_id = await _seed_org_with_plant(factory)

    async with factory() as session:
        _, secret = await CredentialService(session).create(
            name="leitor-org",
            role=OperationsRole.READ,
            organization_id=organization_id,
            plant_ids=frozenset({PLANT_A}),
        )
        await session.commit()

    async with factory() as session:
        principal = await CredentialService(session).resolve(secret)

    assert principal is not None
    assert principal.organization_id is not None
    assert principal.plant_scope.is_restricted is True
