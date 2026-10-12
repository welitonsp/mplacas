from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from mplacas.telegram.bot_service import (
    TelegramBotService,
    UnlinkedTelegramChatError,
    format_plant_list_message,
)


class FakeScalarResult:
    def __init__(self, values: list) -> None:
        self._values = values

    def scalars(self):
        return self._values

    def scalar_one_or_none(self):
        if not self._values:
            return None
        return self._values[0]

    def scalar(self):
        # Used by ``_infer_single_plant_for_organization_in_session``'s
        # ``organizations.default_plant_id`` lookup (ADR-069 § E.2), which
        # runs *before* the plant-enumeration query these fixtures seed via
        # ``scalars()``. These tests pre-date the default-plant feature and
        # exercise the (c)/(d) fallback path, so no default is ever
        # configured here — always ``None``, letting resolution fall through
        # to the ``scalars()``-seeded enumeration below.
        return None


class FakeSession:
    """Fake session returning canned rows regardless of the statement shape.

    Good enough for these unit tests, which only exercise
    ``TelegramBotService.resolve_organization``/``resolve_bill_plant`` in
    isolation with pre-seeded return values (the organization-scoped plant
    inference itself is covered end-to-end by
    ``core.tenancy``/``test_tenancy.py`` and by the cross-tenant webhook test
    below).
    """

    def __init__(self, values: list) -> None:
        self._values = values

    async def execute(self, statement):
        return FakeScalarResult(self._values)


@pytest.mark.asyncio
async def test_resolve_telegram_organization_returns_matching_organization() -> None:
    organization_id = uuid.uuid4()

    resolved = await TelegramBotService(
        FakeSession([organization_id]),  # type: ignore[arg-type]
    ).resolve_organization(123)

    assert resolved == organization_id


@pytest.mark.asyncio
async def test_resolve_telegram_organization_rejects_unknown_chat() -> None:
    # The router maps this to 403 "not linked to any organization"; that
    # HTTP contract is covered in test_telegram_webhook_cross_tenant.py.
    with pytest.raises(UnlinkedTelegramChatError):
        await TelegramBotService(
            FakeSession([]),  # type: ignore[arg-type]
        ).resolve_organization(999)


@pytest.mark.asyncio
async def test_resolve_telegram_allowed_user_id_returns_configured_value() -> None:
    organization_id = uuid.uuid4()

    resolved = await TelegramBotService(
        FakeSession([777]),  # type: ignore[arg-type]
    ).allowed_user_id(organization_id)

    assert resolved == 777


@pytest.mark.asyncio
async def test_resolve_telegram_allowed_user_id_returns_none_when_unconfigured() -> None:
    organization_id = uuid.uuid4()

    resolved = await TelegramBotService(
        FakeSession([]),  # type: ignore[arg-type]
    ).allowed_user_id(organization_id)

    assert resolved is None


@pytest.mark.asyncio
async def test_resolve_bill_plant_reuses_the_given_session() -> None:
    """``TelegramBotService.resolve_bill_plant`` delegates to
    ``core.tenancy._infer_single_plant_for_organization_in_session``, which
    queries against the ``session`` passed in — no second session/connection
    is opened. See ``test_telegram_webhook_cross_tenant.py`` for full
    integration coverage (0/1/>1 plant scenarios, cross-tenant isolation)."""
    plant_id = uuid.uuid4()
    organization_id = uuid.uuid4()

    resolved = await TelegramBotService(
        FakeSession([plant_id]),  # type: ignore[arg-type]
    ).resolve_bill_plant(organization_id)

    assert resolved == plant_id


@pytest.mark.asyncio
async def test_resolve_bill_plant_rejects_ambiguous_scope() -> None:
    organization_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc:
        await TelegramBotService(
            FakeSession([uuid.uuid4(), uuid.uuid4()]),  # type: ignore[arg-type]
        ).resolve_bill_plant(organization_id)

    assert exc.value.status_code == 409


def test_format_plant_list_message_marks_default_and_suggests_switch() -> None:
    first, second = uuid.uuid4(), uuid.uuid4()

    message = format_plant_list_message([(first, "Filial"), (second, "Matriz")], second)

    assert message.splitlines() == [
        "Usinas da sua conta:",
        "- Filial",
        "- Matriz (padrão)",
        "Para trocar: /usina Matriz",
    ]


def test_format_plant_list_message_without_plants() -> None:
    assert (
        format_plant_list_message([], None)
        == "Sua conta ainda não tem nenhuma usina cadastrada."
    )


# --- Cross-tenant isolation of the plant commands, against a real database ---
#
# SQLite enforces no RLS, so these pin the explicit ``organization_id``
# filters in ``TelegramBotService`` — removing any of them used to go unnoticed
# by the whole suite (mutation-checked during the service-layer refactor).

ORG_A = uuid.UUID("00000000-0000-0000-0000-0000000a0001")
ORG_B = uuid.UUID("00000000-0000-0000-0000-0000000b0001")
PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000a00a1")
PLANT_B_SAME_NAME = uuid.UUID("00000000-0000-0000-0000-0000000b00b1")
PLANT_B_PREFIX = uuid.UUID("00000000-0000-0000-0000-0000000b00b2")


@pytest.fixture
async def two_tenant_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from mplacas.db.base import Base
    from mplacas.db.models import Plant
    from mplacas.organizations.db_models import OrganizationRecord

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed:
        seed.add_all(
            [
                OrganizationRecord(id=ORG_A, name="A", slug="org-a", active=True),
                OrganizationRecord(id=ORG_B, name="B", slug="org-b", active=True),
            ]
        )
        await seed.flush()
        seed.add_all(
            [
                Plant(id=PLANT_A, organization_id=ORG_A, name="Matriz"),
                # Same name and a prefix match, but in the other organization.
                Plant(id=PLANT_B_SAME_NAME, organization_id=ORG_B, name="Matriz"),
                Plant(id=PLANT_B_PREFIX, organization_id=ORG_B, name="Matriz Sul"),
            ]
        )
        await seed.commit()
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_find_plants_by_name_never_matches_another_organization(two_tenant_session):
    service = TelegramBotService(two_tenant_session)

    assert await service.find_plants_by_name(ORG_A, "matriz") == [(PLANT_A, "Matriz")]
    assert await service.find_plants_by_name(ORG_A, "Matriz S") == []
    # Exact name that exists *only* in the other organization.
    assert await service.find_plants_by_name(ORG_A, "matriz sul") == []


async def test_plant_list_command_only_shows_own_plants(two_tenant_session):
    reply = await TelegramBotService(two_tenant_session).handle_command(ORG_A, "/usinas")

    assert reply.splitlines() == [
        "Usinas da sua conta:",
        "- Matriz",
        "Para trocar: /usina Matriz",
    ]


async def test_switch_command_sets_own_plant_despite_homonym_elsewhere(two_tenant_session):
    from mplacas.organizations.db_models import OrganizationRecord

    reply = await TelegramBotService(two_tenant_session).handle_command(ORG_A, "/usina matriz")

    assert reply.startswith("Usina ativa agora: Matriz.")
    org_a = await two_tenant_session.get(OrganizationRecord, ORG_A)
    org_b = await two_tenant_session.get(OrganizationRecord, ORG_B)
    assert org_a is not None and org_a.default_plant_id == PLANT_A
    assert org_b is not None and org_b.default_plant_id is None
