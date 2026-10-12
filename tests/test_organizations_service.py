"""Unit tests for ``organizations.service.OrganizationService`` — no FastAPI app.

The HTTP contract (status codes, audit events, platform vs tenant
dependencies) stays covered by ``test_organizations_router.py`` and
``test_invitation_acceptance.py``; these pin the domain rules — especially
the tenant-hiding ones — directly against a real in-memory database.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, UTC

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.organizations.invitation_service import InvitationError
from mplacas.organizations.schemas import (
    OrganizationCreateRequest,
    OrganizationUpdateRequest,
)
from mplacas.organizations.service import (
    DefaultPlantNotFoundError,
    OrganizationNotFoundError,
    OrganizationService,
    SlugInUseError,
    TelegramChatAlreadyLinkedError,
)

ORG_A = uuid.UUID("00000000-0000-0000-0000-00000000aa01")
ORG_B = uuid.UUID("00000000-0000-0000-0000-00000000bb01")
PLANT_A = uuid.UUID("00000000-0000-0000-0000-00000000aa0a")
PLANT_B = uuid.UUID("00000000-0000-0000-0000-00000000bb0b")
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        seed.add_all(
            [
                OrganizationRecord(
                    id=ORG_A, name="A", slug="org-a", active=True, telegram_chat_id=111
                ),
                OrganizationRecord(id=ORG_B, name="B", slug="org-b", active=True),
            ]
        )
        await seed.flush()
        seed.add_all(
            [
                Plant(id=PLANT_A, organization_id=ORG_A, name="Usina A"),
                Plant(id=PLANT_B, organization_id=ORG_B, name="Usina B"),
            ]
        )
        await seed.commit()
    async with factory() as active:
        yield active
    await engine.dispose()


# --- visibility -------------------------------------------------------------


async def test_list_visible_returns_only_own_organization_for_tenant(session):
    records = await OrganizationService(session).list_visible(principal_organization_id=ORG_A)

    assert [r.id for r in records] == [ORG_A]


async def test_list_visible_returns_every_organization_for_platform(session):
    records = await OrganizationService(session).list_visible(principal_organization_id=None)

    assert {r.id for r in records} == {ORG_A, ORG_B}


async def test_get_visible_hides_existing_foreign_organization_as_not_found(session):
    with pytest.raises(OrganizationNotFoundError):
        await OrganizationService(session).get_visible(ORG_B, principal_organization_id=ORG_A)


async def test_get_visible_never_queries_foreign_organization(session, monkeypatch):
    # Without RLS in SQLite, only this guard keeps a tenant from loading
    # another organization's row; it must reject before touching the database.
    async def forbidden_get(*_args, **_kwargs):
        raise AssertionError("foreign organization must not be queried")

    monkeypatch.setattr(session, "get", forbidden_get)

    with pytest.raises(OrganizationNotFoundError):
        await OrganizationService(session).get_visible(ORG_B, principal_organization_id=ORG_A)


async def test_get_visible_lets_platform_read_any_organization(session):
    record = await OrganizationService(session).get_visible(
        ORG_B, principal_organization_id=None
    )

    assert record.id == ORG_B


async def test_get_visible_raises_not_found_for_missing_id(session):
    with pytest.raises(OrganizationNotFoundError):
        await OrganizationService(session).get_visible(
            uuid.uuid4(), principal_organization_id=None
        )


# --- create -----------------------------------------------------------------


async def test_create_rejects_slug_in_use(session):
    payload = OrganizationCreateRequest(name="Outra", slug="org-a", admin_username="admin")

    with pytest.raises(SlugInUseError):
        await OrganizationService(session).create_with_bootstrap_admin(
            payload, invitation_ttl_seconds=3600
        )


async def test_create_returns_active_organization_with_admin_invitation(session):
    payload = OrganizationCreateRequest(name="Nova", slug="nova", admin_username="dona@exemplo.com")

    organization, invitation, token = await OrganizationService(
        session
    ).create_with_bootstrap_admin(payload, invitation_ttl_seconds=3600)

    assert organization.active is True
    assert invitation.organization_id == organization.id
    assert invitation.username == "dona@exemplo.com"
    assert invitation.role == "ADMIN"
    assert token


async def test_create_propagates_invitation_error(session):
    payload = OrganizationCreateRequest(name="Nova", slug="nova", admin_username="  ")

    with pytest.raises(InvitationError):
        await OrganizationService(session).create_with_bootstrap_admin(
            payload, invitation_ttl_seconds=3600
        )


# --- update -----------------------------------------------------------------


async def test_update_rejects_default_plant_of_another_organization(session):
    service = OrganizationService(session)
    record = await service.get_visible(ORG_A, principal_organization_id=ORG_A)

    with pytest.raises(DefaultPlantNotFoundError):
        await service.update(
            record, OrganizationUpdateRequest.model_validate({"default_plant_id": str(PLANT_B)})
        )


async def test_update_sets_own_default_plant_and_leaves_omitted_fields(session):
    service = OrganizationService(session)
    record = await service.get_visible(ORG_A, principal_organization_id=ORG_A)

    await service.update(
        record, OrganizationUpdateRequest.model_validate({"default_plant_id": str(PLANT_A)})
    )

    assert record.default_plant_id == PLANT_A
    assert record.telegram_chat_id == 111


async def test_update_explicit_null_clears_field(session):
    service = OrganizationService(session)
    record = await service.get_visible(ORG_A, principal_organization_id=ORG_A)

    await service.update(
        record, OrganizationUpdateRequest.model_validate({"telegram_chat_id": None})
    )

    assert record.telegram_chat_id is None


async def test_update_maps_duplicate_telegram_chat_to_domain_error(session):
    service = OrganizationService(session)
    record = await service.get_visible(ORG_B, principal_organization_id=ORG_B)

    with pytest.raises(TelegramChatAlreadyLinkedError):
        await service.update(
            record, OrganizationUpdateRequest.model_validate({"telegram_chat_id": 111})
        )


# --- deactivate -------------------------------------------------------------


async def test_deactivate_sets_flag_and_timestamp_once(session):
    service = OrganizationService(session)

    record, revoked = await service.deactivate(ORG_A, now=NOW)
    assert record.active is False
    assert record.deactivated_at is not None
    assert revoked == 0

    later = datetime(2026, 10, 13, tzinfo=UTC)
    record, _ = await service.deactivate(ORG_A, now=later)
    first = record.deactivated_at
    assert first is not None
    assert first.replace(tzinfo=UTC) == NOW


async def test_deactivate_raises_not_found_for_missing_id(session):
    with pytest.raises(OrganizationNotFoundError):
        await OrganizationService(session).deactivate(uuid.uuid4(), now=NOW)
