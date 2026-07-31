"""PR-5: cross-tenant boundary test for ``climate.router``.

Verifies that a caller authenticated for organization B receives 404 (not
403 — same convention as PR-2/PR-3/PR-4, so the response does not reveal the
existence of a plant the caller has no access to) when trying to run
``/climate/collect`` against organization A's plant.

The negative-proof assertion below stubs the climate collection service to
raise if it is ever invoked, so the test fails loudly if the tenancy check is
ever bypassed (the same pattern used by ``test_billing_tenant_boundaries``'s
``/intake-text`` test, ``test_alerts_tenant_boundaries``'s ``/alerts/run``
test, and ``test_orchestration_tenant_boundaries``'s ``/pipeline/run`` test).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.climate.router as climate_router
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord

PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000e1")


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
def cross_tenant_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    import asyncio

    factory = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(climate_router, "SessionFactory", factory)

    org_a, org_b = asyncio.run(_seed(factory))
    token_b = encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)

    yield org_a, org_b, token_b

    get_settings.cache_clear()


def test_climate_collect_cross_tenant_is_not_found_and_never_collects(
    cross_tenant_setup, monkeypatch
) -> None:
    _, _, token_b = cross_tenant_setup
    client = TestClient(app)

    async def fake_collect(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError(
            "climate collection should not run before plant scope is validated"
        )

    monkeypatch.setattr(
        climate_router, "collect_and_persist_daily_climate", fake_collect
    )

    response = client.post(
        "/climate/collect",
        headers={"Authorization": f"Bearer {token_b}"},
        params={
            "plant_id": str(PLANT_A),
            "start_date": "2026-07-12",
            "end_date": "2026-07-13",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}
