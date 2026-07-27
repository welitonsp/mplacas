from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.core.security import OperationsRole
from mplacas.credentials.service import CredentialError, CredentialService, UserService
from mplacas.db.base import Base
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord

OTHER_ORG_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d0")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _create_two_orgs(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    default = OrganizationRecord(
        id=DEFAULT_ORGANIZATION_ID,
        name="Default",
        slug="default",
        active=True,
    )
    other = OrganizationRecord(
        id=OTHER_ORG_ID,
        name="Other",
        slug="other",
        active=True,
    )
    session.add_all([default, other])
    await session.flush()
    return default.id, other.id


@pytest.mark.asyncio
async def test_revoke_is_scoped_before_mutating_credential() -> None:
    factory = await _factory()
    async with factory() as session:
        org_a, org_b = await _create_two_orgs(session)
        record, _ = await CredentialService(session).create(
            name="cred-org-b",
            role=OperationsRole.READ,
            organization_id=org_b,
        )
        await session.commit()

    async with factory() as session:
        with pytest.raises(CredentialError, match="credential not found"):
            await CredentialService(session).revoke(record.id, organization_id=org_a)
        await session.rollback()

    async with factory() as session:
        stored = await session.get(type(record), record.id)
        assert stored is not None
        assert stored.organization_id == org_b
        assert stored.active is True
        assert stored.revoked_at is None


@pytest.mark.asyncio
async def test_deactivate_is_scoped_before_mutating_user() -> None:
    factory = await _factory()
    async with factory() as session:
        org_a, org_b = await _create_two_orgs(session)
        user = await UserService(session).create(
            name="usuario-org-b",
            organization_id=org_b,
        )
        await session.commit()

    async with factory() as session:
        with pytest.raises(CredentialError, match="operational user not found"):
            await UserService(session).deactivate(user.id, organization_id=org_a)
        await session.rollback()

    async with factory() as session:
        stored = await session.get(type(user), user.id)
        assert stored is not None
        assert stored.organization_id == org_b
        assert stored.active is True
        assert stored.deactivated_at is None


@pytest.mark.asyncio
async def test_resolve_rejects_credential_when_organization_is_inactive() -> None:
    factory = await _factory()
    async with factory() as session:
        organization_id = await CredentialService(session)._resolve_default_organization_id()  # type: ignore[attr-defined]
        record, secret = await CredentialService(session).create(
            name="cred-org-inativa",
            role=OperationsRole.READ,
            organization_id=organization_id,
        )
        org = await session.get(OrganizationRecord, organization_id)
        assert org is not None
        org.active = False
        await session.commit()

    async with factory() as session:
        assert await CredentialService(session).resolve(secret) is None
        stored = await session.get(type(record), record.id)
        assert stored is not None
        assert stored.active is True
