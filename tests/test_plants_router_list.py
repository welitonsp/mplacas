"""``GET /plants`` cross-tenant boundary tests (ADR-069, Etapa A).

This is the first endpoint in the project whose response is a *list* of
resource identifiers derived from the caller's scope (enumeration between
tenants), rather than a read of an id the caller already possessed. The
tests below follow the rigor of ``test_photovoltaic_tenant_boundaries.py``
and ``test_plant_scoped_read_access.py``: a plant id belonging to another
organization must never appear in the response, under any principal shape
(bearer JWT, persisted READ credential with a restricted scope, or the
static platform operational key).
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.plants.router as plants_router
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.credentials.service import CredentialService
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord

_TEST_ENGINES: list = []


@pytest.fixture(autouse=True)
def _dispose_test_engines():
    yield
    while _TEST_ENGINES:
        asyncio.run(_TEST_ENGINES.pop().dispose())


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _TEST_ENGINES.append(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed():
    """Org A with two plants, org B with one plant."""
    factory = await _factory()
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
        await session.flush()

        plant_a1 = uuid.uuid4()
        plant_a2 = uuid.uuid4()
        plant_b1 = uuid.uuid4()
        session.add_all(
            [
                Plant(
                    id=plant_a1,
                    organization_id=org_a,
                    name="Filial Norte",
                    installed_power_kwp=Decimal("48.600"),
                ),
                Plant(
                    id=plant_a2,
                    organization_id=org_a,
                    name="Matriz",
                    installed_power_kwp=None,
                ),
                Plant(id=plant_b1, organization_id=org_b, name="Usina B"),
            ]
        )
        await session.commit()
    return factory, org_a, org_b, plant_a1, plant_a2, plant_b1


@pytest.fixture
def seeded(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    factory, org_a, org_b, plant_a1, plant_a2, plant_b1 = asyncio.run(_seed())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(plants_router, "SessionFactory", factory)

    yield {
        "factory": factory,
        "org_a": org_a,
        "org_b": org_b,
        "plant_a1": plant_a1,
        "plant_a2": plant_a2,
        "plant_b1": plant_b1,
    }

    get_settings.cache_clear()


def _bearer(organization_id: uuid.UUID, role: OperationsRole = OperationsRole.ADMIN) -> dict:
    token = encode_access_token(uuid.uuid4(), organization_id, role.value)
    return {"Authorization": f"Bearer {token}"}


def test_org_a_receives_exactly_its_own_plants_never_org_b(seeded) -> None:
    response = TestClient(app).get("/plants", headers=_bearer(seeded["org_a"]))
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    ids = {item["id"] for item in body["items"]}
    assert ids == {str(seeded["plant_a1"]), str(seeded["plant_a2"])}
    assert str(seeded["plant_b1"]) not in ids
    # Ordered by Plant.name: "Filial Norte" < "Matriz"
    assert [item["name"] for item in body["items"]] == ["Filial Norte", "Matriz"]
    assert body["items"][0]["installed_power_kwp"] == "48.600"
    assert body["items"][1]["installed_power_kwp"] is None


def test_org_b_never_sees_org_a_plant_id_under_any_circumstance(seeded) -> None:
    response = TestClient(app).get("/plants", headers=_bearer(seeded["org_b"]))
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    ids = {item["id"] for item in body["items"]}
    assert ids == {str(seeded["plant_b1"])}
    assert str(seeded["plant_a1"]) not in ids
    assert str(seeded["plant_a2"]) not in ids


def test_restricted_credential_lists_only_its_scoped_plant(seeded, monkeypatch) -> None:
    async def _prepare() -> str:
        async with seeded["factory"]() as session:
            _, secret = await CredentialService(session).create(
                name="cred-read-restricted",
                role=OperationsRole.READ,
                organization_id=seeded["org_a"],
                plant_ids=frozenset({seeded["plant_a1"]}),
            )
            await session.commit()
            return secret

    secret = asyncio.run(_prepare())

    response = TestClient(app).get("/plants", headers={"X-API-Key": secret})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["id"] == str(seeded["plant_a1"])


def test_organization_without_plants_gets_empty_200_not_404_not_403(seeded) -> None:
    empty_org = uuid.uuid4()

    async def _create_empty_org() -> None:
        async with seeded["factory"]() as session:
            session.add(
                OrganizationRecord(
                    id=empty_org,
                    name="Org Vazia",
                    slug=f"org-vazia-{empty_org.hex[:8]}",
                    active=True,
                )
            )
            await session.commit()

    asyncio.run(_create_empty_org())

    response = TestClient(app).get("/plants", headers=_bearer(empty_org))
    assert response.status_code == 200
    assert response.json() == {"count": 0, "items": []}


def test_platform_static_key_lists_every_plant_across_all_organizations(
    seeded, monkeypatch
) -> None:
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-static-key")
    get_settings.cache_clear()

    response = TestClient(app).get(
        "/plants", headers={"X-API-Key": "synthetic-static-key"}
    )
    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body["items"]}
    assert ids == {
        str(seeded["plant_a1"]),
        str(seeded["plant_a2"]),
        str(seeded["plant_b1"]),
    }
    assert body["count"] == 3


def test_read_role_receives_200_not_rejected_for_needing_admin(seeded) -> None:
    response = TestClient(app).get(
        "/plants", headers=_bearer(seeded["org_a"], role=OperationsRole.READ)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
