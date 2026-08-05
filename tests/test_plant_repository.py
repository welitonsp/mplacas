from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.db.repositories.plant import PlantRepository
from mplacas.organizations.db_models import OrganizationRecord


async def _make_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_get_or_create_fills_default_plant_for_first_plant() -> None:
    """ADR-069 §E.4: a primeira usina criada numa organização elege a si
    própria como `default_plant_id`, na mesma transação."""
    engine, factory = await _make_session_factory()
    try:
        async with factory() as session:
            org = OrganizationRecord(name="Org Solo", slug="org-solo", active=True)
            session.add(org)
            await session.flush()
            organization_id = org.id

            plant = await PlantRepository(session).get_or_create(
                "Usina Única", organization_id=organization_id
            )
            await session.commit()

            refreshed = await session.get(OrganizationRecord, organization_id)
            assert refreshed is not None
            assert refreshed.default_plant_id == plant.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_default_plant_stays_unchanged_after_second_plant() -> None:
    """Invariante central do ADR-069: depois que a organização tem uma
    segunda usina, `default_plant_id` continua apontando para a primeira,
    nunca fica nulo e nunca é sobrescrito pela eleição automática."""
    engine, factory = await _make_session_factory()
    try:
        async with factory() as session:
            org = OrganizationRecord(name="Org Dupla", slug="org-dupla", active=True)
            session.add(org)
            await session.flush()
            organization_id = org.id

            repository = PlantRepository(session)
            first = await repository.get_or_create(
                "Matriz — Telhado A", organization_id=organization_id
            )
            second = await repository.get_or_create(
                "Filial Norte", organization_id=organization_id
            )
            await session.commit()

            assert first.id != second.id

            refreshed = await session.get(OrganizationRecord, organization_id)
            assert refreshed is not None
            assert refreshed.default_plant_id == first.id
            assert refreshed.default_plant_id != second.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_or_create_does_not_collide_across_organizations() -> None:
    """Bug preexistente corrigido no ADR-069 §E.1/E.10 item 4: duas
    organizações com uma usina de mesmo nome não colidem mais — cada uma
    ganha sua própria linha em `plants`."""
    engine, factory = await _make_session_factory()
    try:
        async with factory() as session:
            org_a = OrganizationRecord(name="Org A", slug="org-a", active=True)
            org_b = OrganizationRecord(name="Org B", slug="org-b", active=True)
            session.add_all([org_a, org_b])
            await session.flush()

            repository = PlantRepository(session)
            plant_a = await repository.get_or_create(
                "Usina Principal", organization_id=org_a.id
            )
            plant_b = await repository.get_or_create(
                "Usina Principal", organization_id=org_b.id
            )
            await session.commit()

            assert plant_a.id != plant_b.id
            assert plant_a.organization_id == org_a.id
            assert plant_b.organization_id == org_b.id

            # Calling again with the same name/organization must resolve to
            # the same row, not create a third one.
            plant_a_again = await repository.get_or_create(
                "Usina Principal", organization_id=org_a.id
            )
            assert plant_a_again.id == plant_a.id
    finally:
        await engine.dispose()
