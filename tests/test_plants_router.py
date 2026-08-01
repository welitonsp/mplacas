"""Tests for ``plants.router`` — ``PATCH /plants/{plant_id}/location``.

Follows the same in-memory-sqlite + JWT pattern used by
``test_climate_tenant_boundaries.py``: real database round-trips (not mocked
sessions), so persistence and cross-tenant isolation are verified by rereading
the database, not just by inspecting the HTTP response.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.plants.router as plants_router
from mplacas.audit.db_models import AuditEventRecord
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord

PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000f1")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed(factory) -> tuple[uuid.UUID, uuid.UUID]:
    """Create org A (with plant A) and org B (no plants)."""
    async with factory() as session:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        session.add_all(
            [
                OrganizationRecord(
                    id=org_a, name="Org A", slug=f"org-a-{org_a.hex[:8]}", active=True
                ),
                OrganizationRecord(
                    id=org_b, name="Org B", slug=f"org-b-{org_b.hex[:8]}", active=True
                ),
            ]
        )
        session.add(Plant(id=PLANT_A, organization_id=org_a, name="Plant A"))
        await session.commit()
        return org_a, org_b


@pytest.fixture
def tenancy_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    import asyncio

    factory = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(plants_router, "SessionFactory", factory)

    org_a, org_b = asyncio.run(_seed(factory))
    token_a_admin = encode_access_token(uuid.uuid4(), org_a, OperationsRole.ADMIN.value)
    token_a_read = encode_access_token(uuid.uuid4(), org_a, OperationsRole.READ.value)
    token_b_admin = encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)

    yield factory, org_a, org_b, token_a_admin, token_a_read, token_b_admin

    get_settings.cache_clear()


async def _reload_plant(factory, plant_id: uuid.UUID) -> Plant | None:
    async with factory() as session:
        return await session.get(Plant, plant_id)


async def _audit_events(factory) -> list[AuditEventRecord]:
    async with factory() as session:
        result = await session.execute(select(AuditEventRecord))
        return list(result.scalars())


def test_own_plant_location_update_persists(tenancy_setup) -> None:
    factory, _, _, token_a_admin, _, _ = tenancy_setup
    client = TestClient(app)

    response = client.patch(
        f"/plants/{PLANT_A}/location",
        headers={"Authorization": f"Bearer {token_a_admin}"},
        json={"latitude": "-23.55", "longitude": "-46.63"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plant_id"] == str(PLANT_A)
    assert Decimal(body["latitude"]) == Decimal("-23.55")
    assert Decimal(body["longitude"]) == Decimal("-46.63")

    import asyncio

    reloaded = asyncio.run(_reload_plant(factory, PLANT_A))
    assert reloaded is not None
    assert reloaded.latitude == Decimal("-23.550000")
    assert reloaded.longitude == Decimal("-46.630000")

    events = asyncio.run(_audit_events(factory))
    assert len(events) == 1
    event = events[0]
    assert event.action == "plant.location_updated"
    assert event.resource_type == "plant"
    assert event.resource_id == str(PLANT_A)
    assert event.outcome == "SUCCEEDED"
    assert event.details == {"latitude": "-23.55", "longitude": "-46.63"}


def test_cross_tenant_update_is_not_found_and_leaves_plant_untouched(
    tenancy_setup,
) -> None:
    factory, _, _, _, _, token_b_admin = tenancy_setup
    client = TestClient(app)

    response = client.patch(
        f"/plants/{PLANT_A}/location",
        headers={"Authorization": f"Bearer {token_b_admin}"},
        json={"latitude": "10.0", "longitude": "10.0"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}

    import asyncio

    reloaded = asyncio.run(_reload_plant(factory, PLANT_A))
    assert reloaded is not None
    assert reloaded.latitude is None
    assert reloaded.longitude is None

    events = asyncio.run(_audit_events(factory))
    assert events == []


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        ("91", "0"),
        ("-91", "0"),
        ("0", "181"),
        ("0", "-181"),
    ],
)
def test_out_of_range_coordinates_are_rejected(
    tenancy_setup, latitude: str, longitude: str
) -> None:
    _, _, _, token_a_admin, _, _ = tenancy_setup
    client = TestClient(app)

    response = client.patch(
        f"/plants/{PLANT_A}/location",
        headers={"Authorization": f"Bearer {token_a_admin}"},
        json={"latitude": latitude, "longitude": longitude},
    )

    assert response.status_code == 422


def test_read_role_is_forbidden(tenancy_setup) -> None:
    _, _, _, _, token_a_read, _ = tenancy_setup
    client = TestClient(app)

    response = client.patch(
        f"/plants/{PLANT_A}/location",
        headers={"Authorization": f"Bearer {token_a_read}"},
        json={"latitude": "1.0", "longitude": "1.0"},
    )

    assert response.status_code == 403
