"""ADR-069 § E5 / § E.11.3 -- ``resolve_admin_plant_fanout`` / ``ScopedPlantSet``.

Unit tests for the fan-out resolver in isolation, without touching any HTTP
endpoint (wiring the four handlers to it is Etapa E7, done separately).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
from mplacas.core.authorization import PlantScope
from mplacas.core.config import get_settings
from mplacas.core.principal import OperationsPrincipal, OperationsRole
from mplacas.core.tenancy import resolve_admin_plant_fanout
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.organizations.db_models import OrganizationRecord

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


async def _seed_org_with_plants(
    factory, names: list[str]
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
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
        plant_ids: dict[str, uuid.UUID] = {}
        for name in names:
            plant_id = uuid.uuid4()
            plant_ids[name] = plant_id
            session.add(Plant(id=plant_id, organization_id=organization_id, name=name))
        await session.flush()
        await session.commit()
        return organization_id, plant_ids


def _admin_principal(
    *, organization_id: uuid.UUID | None, plant_scope: PlantScope = PlantScope.unrestricted()
) -> OperationsPrincipal:
    return OperationsPrincipal(
        role=OperationsRole.ADMIN,
        credential_id="synthetic-test-credential",
        organization_id=organization_id,
        plant_scope=plant_scope,
    )


@pytest.mark.asyncio
async def test_explicit_plant_id_returns_single_member_set(monkeypatch) -> None:
    """(a) plant_id explicit -> set of 1, explicit=True."""
    factory = await _factory()
    organization_id, plant_ids = await _seed_org_with_plants(factory, ["Alpha", "Beta"])
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    principal = _admin_principal(organization_id=organization_id)
    scoped = await resolve_admin_plant_fanout(principal, plant_ids["Beta"])

    assert scoped.plant_ids == (plant_ids["Beta"],)
    assert scoped.explicit is True
    assert scoped.principal is principal


@pytest.mark.asyncio
async def test_platform_principal_single_plant_resolves(monkeypatch) -> None:
    """(b) platform principal (organization_id=None) with exactly one plant
    in the whole database resolves to a set of 1, never fanning out."""
    factory = await _factory()
    _organization_id, plant_ids = await _seed_org_with_plants(factory, ["Only"])
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    principal = _admin_principal(organization_id=None)
    scoped = await resolve_admin_plant_fanout(principal, None)

    assert scoped.plant_ids == (plant_ids["Only"],)
    assert scoped.explicit is False


@pytest.mark.asyncio
async def test_platform_principal_multiple_plants_raises_409(monkeypatch) -> None:
    """(b) platform principal never fans out: 2+ plants -> 409, not a set of 2."""
    factory = await _factory()
    await _seed_org_with_plants(factory, ["Alpha", "Beta"])
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    principal = _admin_principal(organization_id=None)

    with pytest.raises(HTTPException) as exc_info:
        await resolve_admin_plant_fanout(principal, None)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_organization_with_two_plants_returns_both_ordered_by_name(
    monkeypatch,
) -> None:
    """(c) organization with 2 plants -> both, ordered by Plant.name."""
    factory = await _factory()
    organization_id, plant_ids = await _seed_org_with_plants(factory, ["Zulu", "Alpha"])
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    principal = _admin_principal(organization_id=organization_id)
    scoped = await resolve_admin_plant_fanout(principal, None)

    assert scoped.plant_ids == (plant_ids["Alpha"], plant_ids["Zulu"])
    assert scoped.explicit is False


@pytest.mark.asyncio
async def test_organization_with_tied_names_breaks_tie_by_plant_id(monkeypatch) -> None:
    """(c) tie in Plant.name -> broken by Plant.id ascending."""
    factory = await _factory()
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
        low_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        high_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
        session.add(Plant(id=high_id, organization_id=organization_id, name="Same"))
        session.add(Plant(id=low_id, organization_id=organization_id, name="Same"))
        await session.flush()
        await session.commit()
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    principal = _admin_principal(organization_id=organization_id)
    scoped = await resolve_admin_plant_fanout(principal, None)

    assert scoped.plant_ids == (low_id, high_id)


@pytest.mark.asyncio
async def test_restricted_scope_filters_out_non_allowed_plant(monkeypatch) -> None:
    """(d) PlantScope.restricted({p2}) in an org {p1, p2} -> only p2."""
    factory = await _factory()
    organization_id, plant_ids = await _seed_org_with_plants(factory, ["Alpha", "Beta"])
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    principal = _admin_principal(
        organization_id=organization_id,
        plant_scope=PlantScope.restricted({plant_ids["Beta"]}),
    )
    scoped = await resolve_admin_plant_fanout(principal, None)

    assert scoped.plant_ids == (plant_ids["Beta"],)


@pytest.mark.asyncio
async def test_foreign_organizations_plant_never_appears(monkeypatch) -> None:
    """(e) a plant from another organization never appears in the set."""
    factory = await _factory()
    organization_a_id, plants_a = await _seed_org_with_plants(factory, ["Alpha"])
    _organization_b_id, plants_b = await _seed_org_with_plants(factory, ["Bravo"])
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    principal = _admin_principal(organization_id=organization_a_id)
    scoped = await resolve_admin_plant_fanout(principal, None)

    assert scoped.plant_ids == (plants_a["Alpha"],)
    assert plants_b["Bravo"] not in scoped.plant_ids


@pytest.mark.asyncio
async def test_scope_above_cap_raises_409_without_building_set(monkeypatch) -> None:
    """(f) scope above settings.fanout_max_plants -> 409, cap lowered to 2
    with 3 plants seeded to make the boundary easy to hit."""
    factory = await _factory()
    organization_id, _plant_ids = await _seed_org_with_plants(
        factory, ["Alpha", "Beta", "Gamma"]
    )
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setenv("MPLACAS_FANOUT_MAX_PLANTS", "2")
    get_settings.cache_clear()

    principal = _admin_principal(organization_id=organization_id)

    try:
        with pytest.raises(HTTPException) as exc_info:
            await resolve_admin_plant_fanout(principal, None)
        assert exc_info.value.status_code == 409
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_organization_with_zero_visible_plants_raises_actionable_409(
    monkeypatch,
) -> None:
    """Organization with 0 plants visible in scope -> 409, not a crash."""
    factory = await _factory()
    organization_id, _plant_ids = await _seed_org_with_plants(factory, [])
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    principal = _admin_principal(organization_id=organization_id)

    with pytest.raises(HTTPException) as exc_info:
        await resolve_admin_plant_fanout(principal, None)

    assert exc_info.value.status_code == 409
    assert "default_plant_id" in exc_info.value.detail


@pytest.mark.asyncio
async def test_explicit_plant_id_outside_scope_raises_404(monkeypatch) -> None:
    """(a) explicit plant_id outside the caller's scope -> 404, not leaked."""
    factory = await _factory()
    organization_id, plant_ids = await _seed_org_with_plants(factory, ["Alpha", "Beta"])
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    principal = _admin_principal(
        organization_id=organization_id,
        plant_scope=PlantScope.restricted({plant_ids["Alpha"]}),
    )

    with pytest.raises(HTTPException) as exc_info:
        await resolve_admin_plant_fanout(principal, plant_ids["Beta"])

    assert exc_info.value.status_code == 404
