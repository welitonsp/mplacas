from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.core.principal import OperationsRole
from mplacas.db.base import Base
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_db_models import UserInvitationRecord
from mplacas.organizations.invitation_service import (
    InvitationConsumeError,
    InvitationError,
    InvitationService,
)

_TTL_SECONDS = 259_200
_TEST_ENGINES = []


@pytest.fixture(autouse=True)
async def _dispose_test_engines():
    yield
    while _TEST_ENGINES:
        await _TEST_ENGINES.pop().dispose()


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _TEST_ENGINES.append(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _create_organization(session) -> uuid.UUID:
    org = OrganizationRecord(name="Org 1", slug=f"org-{uuid.uuid4().hex[:8]}", active=True)
    session.add(org)
    await session.flush()
    return org.id


async def _create_second_organization(session) -> uuid.UUID:
    org = OrganizationRecord(name="Org 2", slug=f"org-{uuid.uuid4().hex[:8]}", active=True)
    session.add(org)
    await session.flush()
    return org.id


@pytest.mark.asyncio
async def test_token_never_persisted_in_plain_text() -> None:
    factory = await _factory()
    async with factory() as session:
        organization_id = await _create_organization(session)
        service = InvitationService(session)
        record, token = await service.create(
            organization_id=organization_id,
            username="new-user@example.com",
            role=OperationsRole.ADMIN,
            created_by_user_id=None,
            ttl_seconds=_TTL_SECONDS,
        )
        await session.commit()

    async with factory() as session:
        stored = await session.get(UserInvitationRecord, record.id)
        assert stored is not None
        assert stored.token_hash != token
        result = await session.execute(select(UserInvitationRecord.token_hash))
        assert token not in {row[0] for row in result}


@pytest.mark.asyncio
async def test_expired_invitation_is_not_consumed() -> None:
    factory = await _factory()
    async with factory() as session:
        organization_id = await _create_organization(session)
        service = InvitationService(session)
        record, token = await service.create(
            organization_id=organization_id,
            username="expired@example.com",
            role=OperationsRole.READ,
            created_by_user_id=None,
            ttl_seconds=_TTL_SECONDS,
        )
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    async with factory() as session:
        service = InvitationService(session)
        with pytest.raises(InvitationConsumeError):
            await service.consume(token=token)


@pytest.mark.asyncio
async def test_already_accepted_invitation_is_not_consumed_again() -> None:
    factory = await _factory()
    async with factory() as session:
        organization_id = await _create_organization(session)
        service = InvitationService(session)
        record, token = await service.create(
            organization_id=organization_id,
            username="accepted@example.com",
            role=OperationsRole.READ,
            created_by_user_id=None,
            ttl_seconds=_TTL_SECONDS,
        )
        record.accepted_at = datetime.now(timezone.utc)
        record.accepted_user_id = uuid.uuid4()
        await session.commit()

    async with factory() as session:
        service = InvitationService(session)
        with pytest.raises(InvitationConsumeError):
            await service.consume(token=token)


@pytest.mark.asyncio
async def test_revoked_invitation_is_not_consumed() -> None:
    factory = await _factory()
    async with factory() as session:
        organization_id = await _create_organization(session)
        service = InvitationService(session)
        record, token = await service.create(
            organization_id=organization_id,
            username="revoked@example.com",
            role=OperationsRole.READ,
            created_by_user_id=None,
            ttl_seconds=_TTL_SECONDS,
        )
        await session.commit()
        revoked = await service.revoke(
            invitation_id=record.id, organization_id=organization_id
        )
        assert revoked is True
        await session.commit()

    async with factory() as session:
        service = InvitationService(session)
        with pytest.raises(InvitationConsumeError):
            await service.consume(token=token)


@pytest.mark.asyncio
async def test_list_only_returns_invitations_for_the_given_organization() -> None:
    factory = await _factory()
    async with factory() as session:
        organization_id = await _create_organization(session)
        other_organization_id = await _create_second_organization(session)
        service = InvitationService(session)
        await service.create(
            organization_id=organization_id,
            username="mine@example.com",
            role=OperationsRole.READ,
            created_by_user_id=None,
            ttl_seconds=_TTL_SECONDS,
        )
        await service.create(
            organization_id=other_organization_id,
            username="theirs@example.com",
            role=OperationsRole.READ,
            created_by_user_id=None,
            ttl_seconds=_TTL_SECONDS,
        )
        await session.commit()

        invitations = await service.list(organization_id=organization_id)
        assert len(invitations) == 1
        assert invitations[0].username == "mine@example.com"


@pytest.mark.asyncio
async def test_revoke_invitation_from_another_organization_fails() -> None:
    factory = await _factory()
    async with factory() as session:
        organization_id = await _create_organization(session)
        other_organization_id = await _create_second_organization(session)
        service = InvitationService(session)
        record, _token = await service.create(
            organization_id=organization_id,
            username="mine@example.com",
            role=OperationsRole.READ,
            created_by_user_id=None,
            ttl_seconds=_TTL_SECONDS,
        )
        await session.commit()

        revoked = await service.revoke(
            invitation_id=record.id, organization_id=other_organization_id
        )
        assert revoked is False

    async with factory() as session:
        stored = await session.get(UserInvitationRecord, record.id)
        assert stored is not None
        assert stored.revoked_at is None


@pytest.mark.asyncio
async def test_mark_accepted_is_idempotent_against_concurrent_acceptance() -> None:
    factory = await _factory()
    async with factory() as session:
        organization_id = await _create_organization(session)
        service = InvitationService(session)
        record, _token = await service.create(
            organization_id=organization_id,
            username="race@example.com",
            role=OperationsRole.READ,
            created_by_user_id=None,
            ttl_seconds=_TTL_SECONDS,
        )
        await session.commit()

        first_user_id = uuid.uuid4()
        second_user_id = uuid.uuid4()

        first = await service.mark_accepted(
            invitation_id=record.id, accepted_user_id=first_user_id
        )
        second = await service.mark_accepted(
            invitation_id=record.id, accepted_user_id=second_user_id
        )
        await session.commit()

        assert first is True
        assert second is False

    async with factory() as session:
        stored = await session.get(UserInvitationRecord, record.id)
        assert stored is not None
        assert stored.accepted_user_id == first_user_id


@pytest.mark.asyncio
async def test_create_rejects_username_without_email_format() -> None:
    factory = await _factory()
    async with factory() as session:
        organization_id = await _create_organization(session)
        service = InvitationService(session)
        with pytest.raises(InvitationError, match="email"):
            await service.create(
                organization_id=organization_id,
                username="not-an-email",
                role=OperationsRole.READ,
                created_by_user_id=None,
                ttl_seconds=_TTL_SECONDS,
            )
