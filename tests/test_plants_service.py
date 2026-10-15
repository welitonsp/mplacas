"""Unit tests for ``plants.service.PlantService`` — no FastAPI app involved.

The HTTP contract (status codes, tenant 404s, audit events) stays covered by
``test_plants_router.py`` and ``test_plants_router_list.py``; these tests pin
the domain rules directly against a real in-memory database.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.core.authorization import UNRESTRICTED_PLANT_SCOPE, PlantScope
from mplacas.db.base import Base
from mplacas.db.models import Device, Plant
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.plants.schemas import (
    ModuleTechnology,
    PlantFinancialConfigurationUpdateRequest,
    PlantLocationUpdateRequest,
    PlantTechnicalConfigurationUpdateRequest,
)
from mplacas.plants.service import DeviceNotFoundError, PlantNotFoundError, PlantService

ORG_A = uuid.UUID("00000000-0000-0000-0000-00000000a001")
ORG_B = uuid.UUID("00000000-0000-0000-0000-00000000b001")
PLANT_A1 = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
PLANT_A2 = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
PLANT_B1 = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
DEVICE_A1 = uuid.UUID("00000000-0000-0000-0000-0000000d00a1")
DEVICE_B1 = uuid.UUID("00000000-0000-0000-0000-0000000d00b1")


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as seed:
        seed.add_all(
            [
                OrganizationRecord(id=ORG_A, name="Org A", slug="org-a", active=True),
                OrganizationRecord(id=ORG_B, name="Org B", slug="org-b", active=True),
            ]
        )
        await seed.flush()
        seed.add_all(
            [
                # Names chosen so ordering by name differs from insertion order.
                Plant(id=PLANT_A1, organization_id=ORG_A, name="Zeta"),
                Plant(
                    id=PLANT_A2,
                    organization_id=ORG_A,
                    name="Alpha",
                    installed_power_kwp=Decimal("5.400"),
                ),
                Plant(id=PLANT_B1, organization_id=ORG_B, name="Beta"),
            ]
        )
        await seed.flush()
        seed.add_all(
            [
                Device(id=DEVICE_A1, plant_id=PLANT_A1, serial_number="INV-A1"),
                Device(id=DEVICE_B1, plant_id=PLANT_B1, serial_number="INV-B1"),
            ]
        )
        organization_a = await seed.get(OrganizationRecord, ORG_A)
        assert organization_a is not None
        organization_a.default_plant_id = PLANT_A1
        await seed.commit()

    async with factory() as active:
        yield active
    await engine.dispose()


async def test_list_visible_filters_by_organization_and_orders_by_name(session):
    entries = await PlantService(session).list_visible(
        organization_id=ORG_A, plant_scope=UNRESTRICTED_PLANT_SCOPE
    )

    assert [(e.plant.id, e.is_default) for e in entries] == [
        (PLANT_A2, False),
        (PLANT_A1, True),
    ]


async def test_list_visible_resolves_default_per_organization_without_org_filter(session):
    entries = await PlantService(session).list_visible(
        organization_id=None, plant_scope=UNRESTRICTED_PLANT_SCOPE
    )

    defaults = {e.plant.id: e.is_default for e in entries}
    # Org B has no default plant; Org A's default must not leak to it.
    assert defaults == {PLANT_A2: False, PLANT_B1: False, PLANT_A1: True}


async def test_list_visible_intersects_with_restricted_plant_scope(session):
    entries = await PlantService(session).list_visible(
        organization_id=ORG_A, plant_scope=PlantScope.restricted([PLANT_A2])
    )

    assert [e.plant.id for e in entries] == [PLANT_A2]


async def test_get_raises_domain_error_for_missing_plant(session):
    with pytest.raises(PlantNotFoundError):
        await PlantService(session).get(uuid.uuid4())


async def test_update_technical_configuration_applies_only_fields_sent(session):
    service = PlantService(session)
    plant = await service.get(PLANT_A2)
    payload = PlantTechnicalConfigurationUpdateRequest.model_validate(
        {"array_tilt_degrees": "12.50", "module_technology": "THIN_FILM"}
    )

    await service.update_technical_configuration(plant, payload)
    view = await service.technical_configuration(plant)

    assert view.array_tilt_degrees == Decimal("12.50")
    assert view.module_technology is ModuleTechnology.THIN_FILM
    assert plant.module_technology == "THIN_FILM"
    # Untouched fields keep their stored values.
    assert view.dc_capacity_kwp == Decimal("5.400")
    assert view.commissioned_on is None


async def test_update_technical_configuration_maps_dc_capacity_and_devices(session):
    service = PlantService(session)
    plant = await service.get(PLANT_A1)
    payload = PlantTechnicalConfigurationUpdateRequest.model_validate(
        {
            "dc_capacity_kwp": "6.600",
            "commissioned_on": "2024-03-01",
            "devices": [{"device_id": str(DEVICE_A1), "ac_capacity_kw": "5.000"}],
        }
    )

    await service.update_technical_configuration(plant, payload)
    view = await service.technical_configuration(plant)

    assert plant.installed_power_kwp == Decimal("6.600")
    assert view.commissioned_on == date(2024, 3, 1)
    (device,) = view.devices
    assert device.device_id == DEVICE_A1
    assert device.ac_capacity_kw == Decimal("5.000")
    assert device.dc_capacity_kwp is None


async def test_update_technical_configuration_rejects_device_from_other_plant(session):
    service = PlantService(session)
    plant = await service.get(PLANT_A1)
    payload = PlantTechnicalConfigurationUpdateRequest.model_validate(
        {"devices": [{"device_id": str(DEVICE_B1), "dc_capacity_kwp": "1.000"}]}
    )

    with pytest.raises(DeviceNotFoundError):
        await service.update_technical_configuration(plant, payload)

    foreign_device = await session.get(Device, DEVICE_B1)
    assert foreign_device is not None
    assert foreign_device.dc_capacity_kwp is None


async def test_update_financial_configuration_can_clear_a_field(session):
    service = PlantService(session)
    plant = await service.get(PLANT_A1)
    await service.update_financial_configuration(
        plant,
        PlantFinancialConfigurationUpdateRequest.model_validate(
            {"investment_amount_brl": "25000.00", "investment_recorded_on": "2024-01-10"}
        ),
    )

    await service.update_financial_configuration(
        plant,
        PlantFinancialConfigurationUpdateRequest.model_validate({"investment_recorded_on": None}),
    )
    view = PlantService.financial_configuration(plant)

    assert view.investment_amount_brl == Decimal("25000.00")
    assert view.investment_recorded_on is None


async def test_update_location_sets_coordinates(session):
    service = PlantService(session)
    plant = await service.get(PLANT_A1)

    await service.update_location(
        plant,
        PlantLocationUpdateRequest(latitude=Decimal("-17.74"), longitude=Decimal("-48.62")),
    )

    assert (plant.latitude, plant.longitude) == (Decimal("-17.74"), Decimal("-48.62"))


async def test_setup_status_counts_confirmed_and_pending_bills(session):
    from mplacas.billing.db_models import BillStatus, UtilityBillRecord

    def bill(month: str, status: BillStatus) -> UtilityBillRecord:
        return UtilityBillRecord(
            plant_id=PLANT_A1,
            distributor="EQUATORIAL_GO",
            reference_month=month,
            cycle_start=date(2026, 8, 17),
            cycle_end=date(2026, 9, 14),
            billed_days=29,
            imported_kwh=Decimal("221"),
            injected_kwh=Decimal("221"),
            compensated_kwh=Decimal("221"),
            credit_balance_kwh=Decimal("17.98"),
            total_amount_brl=Decimal("70.22"),
            status=status,
            source_hash=f"hash-{month}",
        )

    session.add_all(
        [
            bill("2026-08", BillStatus.CONFIRMED),
            bill("2026-09", BillStatus.PENDING_REVIEW),
            bill("2026-07", BillStatus.REJECTED),
        ]
    )
    await session.flush()

    plant = await PlantService(session).get(PLANT_A1)
    status = await PlantService(session).setup_status(plant)

    assert status.confirmed_bills == 1
    assert status.pending_bills == 1
    done = {item.key.value: item.done for item in status.items}
    assert done["CONFIRMED_BILL"] is True
    assert done["DC_CAPACITY"] is False
