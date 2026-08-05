"""Tests for ``plants.router`` — ``PATCH /plants/{plant_id}/location``.

Follows the same in-memory-sqlite + JWT pattern used by
``test_climate_tenant_boundaries.py``: real database round-trips (not mocked
sessions), so persistence and cross-tenant isolation are verified by rereading
the database, not just by inspecting the HTTP response.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
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
from mplacas.db.models import Device, Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord

PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000f1")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


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
        plant = Plant(id=PLANT_A, organization_id=org_a, name="Plant A")
        session.add(plant)
        session.add_all(
            [
                Device(plant_id=PLANT_A, serial_number="INV-A"),
                Device(plant_id=PLANT_A, serial_number="INV-B"),
            ]
        )
        await session.commit()
        return org_a, org_b


@pytest.fixture
def tenancy_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    factory, engine = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(plants_router, "SessionFactory", factory)

    org_a, org_b = asyncio.run(_seed(factory))
    token_a_admin = encode_access_token(uuid.uuid4(), org_a, OperationsRole.ADMIN.value)
    token_a_read = encode_access_token(uuid.uuid4(), org_a, OperationsRole.READ.value)
    token_b_admin = encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)

    yield factory, org_a, org_b, token_a_admin, token_a_read, token_b_admin

    asyncio.run(engine.dispose())
    get_settings.cache_clear()


@pytest.fixture
def client(tenancy_setup):
    with TestClient(app) as test_client:
        yield test_client


async def _reload_plant(factory, plant_id: uuid.UUID) -> Plant | None:
    async with factory() as session:
        return await session.get(Plant, plant_id)


async def _audit_events(factory) -> list[AuditEventRecord]:
    async with factory() as session:
        result = await session.execute(select(AuditEventRecord))
        return list(result.scalars())


async def _devices(factory) -> list[Device]:
    async with factory() as session:
        result = await session.scalars(
            select(Device).where(Device.plant_id == PLANT_A).order_by(Device.serial_number)
        )
        return list(result)


def test_own_plant_location_update_persists(tenancy_setup, client: TestClient) -> None:
    factory, _, _, token_a_admin, _, _ = tenancy_setup
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
    client: TestClient,
) -> None:
    factory, _, _, _, _, token_b_admin = tenancy_setup
    response = client.patch(
        f"/plants/{PLANT_A}/location",
        headers={"Authorization": f"Bearer {token_b_admin}"},
        json={"latitude": "10.0", "longitude": "10.0"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}

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
    tenancy_setup, client: TestClient, latitude: str, longitude: str
) -> None:
    _, _, _, token_a_admin, _, _ = tenancy_setup
    response = client.patch(
        f"/plants/{PLANT_A}/location",
        headers={"Authorization": f"Bearer {token_a_admin}"},
        json={"latitude": latitude, "longitude": longitude},
    )

    assert response.status_code == 422


def test_read_role_is_forbidden(tenancy_setup, client: TestClient) -> None:
    _, _, _, _, token_a_read, _ = tenancy_setup
    response = client.patch(
        f"/plants/{PLANT_A}/location",
        headers={"Authorization": f"Bearer {token_a_read}"},
        json={"latitude": "1.0", "longitude": "1.0"},
    )

    assert response.status_code == 403


def test_technical_configuration_update_and_read_are_persisted(
    tenancy_setup, client: TestClient
) -> None:
    factory, _, _, token_a_admin, token_a_read, _ = tenancy_setup
    devices = asyncio.run(_devices(factory))
    response = client.patch(
        f"/plants/{PLANT_A}/technical-configuration",
        headers={"Authorization": f"Bearer {token_a_admin}"},
        json={
            "dc_capacity_kwp": "12.600",
            "ac_capacity_kw": "10.000",
            "array_tilt_degrees": "18.50",
            "array_azimuth_degrees": "12.25",
            "module_technology": "MONOCRYSTALLINE_SILICON",
            "commissioned_on": "2024-03-15",
            "devices": [
                {
                    "device_id": str(devices[0].id),
                    "dc_capacity_kwp": "6.300",
                    "ac_capacity_kw": "5.000",
                },
                {
                    "device_id": str(devices[1].id),
                    "dc_capacity_kwp": "6.300",
                    "ac_capacity_kw": "5.000",
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["dc_capacity_kwp"]) == Decimal("12.600")
    assert Decimal(body["ac_capacity_kw"]) == Decimal("10.000")
    assert body["module_technology"] == "MONOCRYSTALLINE_SILICON"
    assert body["commissioned_on"] == "2024-03-15"
    assert [device["serial_number"] for device in body["devices"]] == ["INV-A", "INV-B"]

    read_response = client.get(
        f"/plants/{PLANT_A}/technical-configuration",
        headers={"Authorization": f"Bearer {token_a_read}"},
    )
    assert read_response.status_code == 200
    assert read_response.json() == body

    plant = asyncio.run(_reload_plant(factory, PLANT_A))
    assert plant is not None
    assert plant.installed_power_kwp == Decimal("12.600")
    assert plant.ac_capacity_kw == Decimal("10.000")
    assert plant.array_tilt_degrees == Decimal("18.50")
    assert plant.array_azimuth_degrees == Decimal("12.25")
    assert plant.commissioned_on == date(2024, 3, 15)

    events = asyncio.run(_audit_events(factory))
    assert len(events) == 1
    assert events[0].action == "plant.technical_configuration_updated"


@pytest.mark.parametrize(
    "field,value",
    [
        ("dc_capacity_kwp", "0"),
        ("ac_capacity_kw", "-1"),
        ("array_tilt_degrees", "90.01"),
        ("array_azimuth_degrees", "360"),
        ("module_technology", "PERC_UNKNOWN"),
    ],
)
def test_invalid_technical_configuration_is_rejected(
    tenancy_setup, client: TestClient, field: str, value: str
) -> None:
    _, _, _, token_a_admin, _, _ = tenancy_setup
    response = client.patch(
        f"/plants/{PLANT_A}/technical-configuration",
        headers={"Authorization": f"Bearer {token_a_admin}"},
        json={field: value},
    )
    assert response.status_code == 422


def test_foreign_device_rejects_entire_technical_update(
    tenancy_setup, client: TestClient
) -> None:
    factory, _, _, token_a_admin, _, _ = tenancy_setup
    response = client.patch(
        f"/plants/{PLANT_A}/technical-configuration",
        headers={"Authorization": f"Bearer {token_a_admin}"},
        json={
            "dc_capacity_kwp": "20.000",
            "devices": [{"device_id": str(uuid.uuid4()), "ac_capacity_kw": "5.000"}],
        },
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "device not found"}

    plant = asyncio.run(_reload_plant(factory, PLANT_A))
    assert plant is not None
    assert plant.installed_power_kwp is None
    assert asyncio.run(_audit_events(factory)) == []


def test_technical_configuration_is_tenant_and_role_scoped(
    tenancy_setup, client: TestClient
) -> None:
    _, _, _, _, token_a_read, token_b_admin = tenancy_setup
    path = f"/plants/{PLANT_A}/technical-configuration"

    assert client.patch(
        path,
        headers={"Authorization": f"Bearer {token_a_read}"},
        json={"dc_capacity_kwp": "5.000"},
    ).status_code == 403
    assert client.get(
        path, headers={"Authorization": f"Bearer {token_b_admin}"}
    ).status_code == 404
    assert client.patch(
        path,
        headers={"Authorization": f"Bearer {token_b_admin}"},
        json={"dc_capacity_kwp": "5.000"},
    ).status_code == 404


def test_financial_configuration_get_defaults_to_null(
    tenancy_setup, client: TestClient
) -> None:
    _, _, _, _, token_a_read, _ = tenancy_setup
    response = client.get(
        f"/plants/{PLANT_A}/financial-configuration",
        headers={"Authorization": f"Bearer {token_a_read}"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "plant_id": str(PLANT_A),
        "investment_amount_brl": None,
        "investment_recorded_on": None,
    }


def test_financial_configuration_update_and_read_are_persisted(
    tenancy_setup, client: TestClient
) -> None:
    factory, _, _, token_a_admin, token_a_read, _ = tenancy_setup
    response = client.patch(
        f"/plants/{PLANT_A}/financial-configuration",
        headers={"Authorization": f"Bearer {token_a_admin}"},
        json={
            "investment_amount_brl": "48000.00",
            "investment_recorded_on": "2024-03-11",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["investment_amount_brl"]) == Decimal("48000.00")
    assert body["investment_recorded_on"] == "2024-03-11"

    read_response = client.get(
        f"/plants/{PLANT_A}/financial-configuration",
        headers={"Authorization": f"Bearer {token_a_read}"},
    )
    assert read_response.status_code == 200
    assert read_response.json() == body

    plant = asyncio.run(_reload_plant(factory, PLANT_A))
    assert plant is not None
    assert plant.investment_amount_brl == Decimal("48000.00")
    assert plant.investment_recorded_on == date(2024, 3, 11)

    events = asyncio.run(_audit_events(factory))
    assert len(events) == 1
    event = events[0]
    assert event.action == "plant.financial_configuration_updated"
    assert event.resource_type == "plant"
    assert event.resource_id == str(PLANT_A)
    assert event.outcome == "SUCCEEDED"
    assert event.details == {
        "investment_amount_brl": "48000.00",
        "investment_recorded_on": "2024-03-11",
    }


def test_financial_configuration_partial_update_preserves_other_field(
    tenancy_setup, client: TestClient
) -> None:
    _, _, _, token_a_admin, _, _ = tenancy_setup
    client.patch(
        f"/plants/{PLANT_A}/financial-configuration",
        headers={"Authorization": f"Bearer {token_a_admin}"},
        json={
            "investment_amount_brl": "48000.00",
            "investment_recorded_on": "2024-03-11",
        },
    )

    response = client.patch(
        f"/plants/{PLANT_A}/financial-configuration",
        headers={"Authorization": f"Bearer {token_a_admin}"},
        json={"investment_amount_brl": "50000.00"},
    )

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["investment_amount_brl"]) == Decimal("50000.00")
    assert body["investment_recorded_on"] == "2024-03-11"


def test_financial_configuration_explicit_null_clears_field(
    tenancy_setup, client: TestClient
) -> None:
    _, _, _, token_a_admin, _, _ = tenancy_setup
    client.patch(
        f"/plants/{PLANT_A}/financial-configuration",
        headers={"Authorization": f"Bearer {token_a_admin}"},
        json={
            "investment_amount_brl": "48000.00",
            "investment_recorded_on": "2024-03-11",
        },
    )

    response = client.patch(
        f"/plants/{PLANT_A}/financial-configuration",
        headers={"Authorization": f"Bearer {token_a_admin}"},
        json={"investment_amount_brl": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["investment_amount_brl"] is None
    assert body["investment_recorded_on"] == "2024-03-11"


@pytest.mark.parametrize("value", ["0", "-1", "-100.50"])
def test_financial_configuration_rejects_non_positive_investment(
    tenancy_setup, client: TestClient, value: str
) -> None:
    _, _, _, token_a_admin, _, _ = tenancy_setup
    response = client.patch(
        f"/plants/{PLANT_A}/financial-configuration",
        headers={"Authorization": f"Bearer {token_a_admin}"},
        json={"investment_amount_brl": value},
    )
    assert response.status_code == 422


def test_financial_configuration_rejects_empty_payload(
    tenancy_setup, client: TestClient
) -> None:
    _, _, _, token_a_admin, _, _ = tenancy_setup
    response = client.patch(
        f"/plants/{PLANT_A}/financial-configuration",
        headers={"Authorization": f"Bearer {token_a_admin}"},
        json={},
    )
    assert response.status_code == 422


def test_financial_configuration_is_tenant_and_role_scoped(
    tenancy_setup, client: TestClient
) -> None:
    factory, _, _, _, token_a_read, token_b_admin = tenancy_setup
    path = f"/plants/{PLANT_A}/financial-configuration"

    assert client.patch(
        path,
        headers={"Authorization": f"Bearer {token_a_read}"},
        json={"investment_amount_brl": "5000.00"},
    ).status_code == 403
    assert client.get(
        path, headers={"Authorization": f"Bearer {token_b_admin}"}
    ).status_code == 404
    assert client.get(
        path, headers={"Authorization": f"Bearer {token_b_admin}"}
    ).json() == {"detail": "plant not found"}
    assert client.patch(
        path,
        headers={"Authorization": f"Bearer {token_b_admin}"},
        json={"investment_amount_brl": "5000.00"},
    ).status_code == 404

    plant = asyncio.run(_reload_plant(factory, PLANT_A))
    assert plant is not None
    assert plant.investment_amount_brl is None
    assert asyncio.run(_audit_events(factory)) == []
