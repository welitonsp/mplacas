from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.audit.repository import AuditEventRepository
from mplacas.core.tenancy import AdminPlantPath, ReadPlantPath
from mplacas.db.models import Device, Plant
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_principal_context

router = APIRouter(prefix="/plants", tags=["plants"])


class PlantLocationUpdateRequest(BaseModel):
    """Geographic coordinates enabling climate collection for a plant.

    Bounds match the ones already enforced defensively in
    ``climate.collection_service.collect_and_persist_daily_climate`` (a plant
    with out-of-range coordinates would otherwise persist here only to be
    rejected there, opaquely, the next time collection runs).
    """

    latitude: Decimal = Field(ge=-90, le=90)
    longitude: Decimal = Field(ge=-180, le=180)


class ModuleTechnology(str, enum.Enum):
    MONOCRYSTALLINE_SILICON = "MONOCRYSTALLINE_SILICON"
    POLYCRYSTALLINE_SILICON = "POLYCRYSTALLINE_SILICON"
    THIN_FILM = "THIN_FILM"
    OTHER = "OTHER"


class DevicePowerConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: uuid.UUID
    dc_capacity_kwp: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    ac_capacity_kw: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)

    @model_validator(mode="after")
    def validate_at_least_one_rating(self) -> DevicePowerConfiguration:
        if not ({"dc_capacity_kwp", "ac_capacity_kw"} & self.model_fields_set):
            raise ValueError("at least one device power rating is required")
        return self


class PlantTechnicalConfigurationUpdateRequest(BaseModel):
    """Full technical input required by the versioned photovoltaic models."""

    model_config = ConfigDict(extra="forbid")

    dc_capacity_kwp: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    ac_capacity_kw: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    array_tilt_degrees: Decimal | None = Field(
        default=None, ge=0, le=90, max_digits=5, decimal_places=2
    )
    array_azimuth_degrees: Decimal | None = Field(
        default=None, ge=0, lt=360, max_digits=5, decimal_places=2
    )
    module_technology: ModuleTechnology | None = None
    commissioned_on: date | None = None
    devices: tuple[DevicePowerConfiguration, ...] | None = None

    @model_validator(mode="after")
    def validate_unique_devices(self) -> PlantTechnicalConfigurationUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("at least one technical configuration field is required")
        if self.devices is None:
            return self
        ids = [device.device_id for device in self.devices]
        if len(ids) != len(set(ids)):
            raise ValueError("devices must not contain duplicate device_id values")
        return self


class PlantFinancialConfigurationUpdateRequest(BaseModel):
    """CAPEX input backing the financial-return indicator (ADR-067).

    No coherence rule between ``investment_recorded_on`` and
    ``commissioned_on`` is enforced by design (ADR-067, Decisão item 4): the
    date is informative only, and ``commissioned_on`` remains the sole
    reference date for calculations.
    """

    model_config = ConfigDict(extra="forbid")

    investment_amount_brl: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    investment_recorded_on: date | None = None

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> PlantFinancialConfigurationUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("at least one financial configuration field is required")
        return self


class PlantFinancialConfigurationView(BaseModel):
    plant_id: uuid.UUID
    investment_amount_brl: Decimal | None
    investment_recorded_on: date | None


class DevicePowerConfigurationView(BaseModel):
    device_id: uuid.UUID
    serial_number: str
    dc_capacity_kwp: Decimal | None
    ac_capacity_kw: Decimal | None


class PlantTechnicalConfigurationView(BaseModel):
    plant_id: uuid.UUID
    dc_capacity_kwp: Decimal | None
    ac_capacity_kw: Decimal | None
    array_tilt_degrees: Decimal | None
    array_azimuth_degrees: Decimal | None
    module_technology: ModuleTechnology | None
    commissioned_on: date | None
    devices: tuple[DevicePowerConfigurationView, ...]


def _plant_location_view(plant: Plant) -> dict[str, object]:
    return {
        "plant_id": str(plant.id),
        "latitude": plant.latitude,
        "longitude": plant.longitude,
    }


async def _technical_configuration_view(
    session: AsyncSession, plant: Plant
) -> PlantTechnicalConfigurationView:
    devices = (
        await session.scalars(
            select(Device).where(Device.plant_id == plant.id).order_by(Device.serial_number)
        )
    ).all()
    return PlantTechnicalConfigurationView(
        plant_id=plant.id,
        dc_capacity_kwp=plant.installed_power_kwp,
        ac_capacity_kw=plant.ac_capacity_kw,
        array_tilt_degrees=plant.array_tilt_degrees,
        array_azimuth_degrees=plant.array_azimuth_degrees,
        module_technology=(
            ModuleTechnology(plant.module_technology)
            if plant.module_technology is not None
            else None
        ),
        commissioned_on=plant.commissioned_on,
        devices=tuple(
            DevicePowerConfigurationView(
                device_id=device.id,
                serial_number=device.serial_number,
                dc_capacity_kwp=device.dc_capacity_kwp,
                ac_capacity_kw=device.ac_capacity_kw,
            )
            for device in devices
        ),
    )


@router.get(
    "/{plant_id}/technical-configuration",
    response_model=PlantTechnicalConfigurationView,
)
async def get_plant_technical_configuration(
    scoped: ReadPlantPath,
) -> PlantTechnicalConfigurationView:
    """Return plant geometry and power ratings within the caller's tenant."""
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        plant = await session.get(Plant, scoped.plant_id)
        if plant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="plant not found"
            )
        return await _technical_configuration_view(session, plant)


@router.patch(
    "/{plant_id}/technical-configuration",
    response_model=PlantTechnicalConfigurationView,
)
async def update_plant_technical_configuration(
    request: Request,
    scoped: AdminPlantPath,
    payload: PlantTechnicalConfigurationUpdateRequest,
) -> PlantTechnicalConfigurationView:
    """Atomically update plant and inverter technical configuration."""
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        plant = await session.get(Plant, scoped.plant_id)
        if plant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="plant not found"
            )

        plant_fields = payload.model_fields_set - {"devices"}
        if "dc_capacity_kwp" in plant_fields:
            plant.installed_power_kwp = payload.dc_capacity_kwp
        for field_name in (
            "ac_capacity_kw",
            "array_tilt_degrees",
            "array_azimuth_degrees",
            "commissioned_on",
        ):
            if field_name in plant_fields:
                setattr(plant, field_name, getattr(payload, field_name))
        if "module_technology" in plant_fields:
            plant.module_technology = (
                payload.module_technology.value
                if payload.module_technology is not None
                else None
            )

        if "devices" in payload.model_fields_set and payload.devices is not None:
            requested_ids = {item.device_id for item in payload.devices}
            device_rows = (
                await session.scalars(
                    select(Device).where(
                        Device.plant_id == plant.id,
                        Device.id.in_(requested_ids),
                    )
                )
            ).all()
            devices_by_id = {device.id: device for device in device_rows}
            if devices_by_id.keys() != requested_ids:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="device not found",
                )
            for item in payload.devices:
                device = devices_by_id[item.device_id]
                if "dc_capacity_kwp" in item.model_fields_set:
                    device.dc_capacity_kwp = item.dc_capacity_kwp
                if "ac_capacity_kw" in item.model_fields_set:
                    device.ac_capacity_kw = item.ac_capacity_kw

        await session.flush()
        await AuditEventRepository(session).record(
            request,
            action="plant.technical_configuration_updated",
            resource_type="plant",
            resource_id=str(plant.id),
            outcome="SUCCEEDED",
            details=payload.model_dump(mode="json", exclude_unset=True),
        )
        response = await _technical_configuration_view(session, plant)
        await session.commit()
        return response


def _financial_configuration_view(plant: Plant) -> PlantFinancialConfigurationView:
    return PlantFinancialConfigurationView(
        plant_id=plant.id,
        investment_amount_brl=plant.investment_amount_brl,
        investment_recorded_on=plant.investment_recorded_on,
    )


@router.get(
    "/{plant_id}/financial-configuration",
    response_model=PlantFinancialConfigurationView,
)
async def get_plant_financial_configuration(
    scoped: ReadPlantPath,
) -> PlantFinancialConfigurationView:
    """Return the plant's CAPEX input (ADR-067) within the caller's tenant."""
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        plant = await session.get(Plant, scoped.plant_id)
        if plant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="plant not found"
            )
        return _financial_configuration_view(plant)


@router.patch(
    "/{plant_id}/financial-configuration",
    response_model=PlantFinancialConfigurationView,
)
async def update_plant_financial_configuration(
    request: Request,
    scoped: AdminPlantPath,
    payload: PlantFinancialConfigurationUpdateRequest,
) -> PlantFinancialConfigurationView:
    """Set or clear the plant's CAPEX input feeding the financial-return
    indicator (ADR-067).

    ``AdminPlantPath`` resolves ``plant_id`` from the URL path and validates
    it against the caller's organization scope, returning 404 (not 403) for
    a plant belonging to another organization — the same convention used by
    every other plant-scoped router (see ``core.tenancy`` and
    ``update_plant_location`` above).
    """
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        plant = await session.get(Plant, scoped.plant_id)
        if plant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="plant not found"
            )

        for field_name in ("investment_amount_brl", "investment_recorded_on"):
            if field_name in payload.model_fields_set:
                setattr(plant, field_name, getattr(payload, field_name))

        await session.flush()
        await AuditEventRepository(session).record(
            request,
            action="plant.financial_configuration_updated",
            resource_type="plant",
            resource_id=str(plant.id),
            outcome="SUCCEEDED",
            details=payload.model_dump(mode="json", exclude_unset=True),
        )
        response = _financial_configuration_view(plant)
        await session.commit()
        return response


@router.patch("/{plant_id}/location")
async def update_plant_location(
    request: Request,
    scoped: AdminPlantPath,
    payload: PlantLocationUpdateRequest,
) -> dict[str, object]:
    """Set the latitude/longitude used by climate collection for a plant.

    ``AdminPlantPath`` resolves ``plant_id`` from the URL path and validates it
    against the caller's organization scope, returning 404 (not 403) for a
    plant belonging to another organization — the same convention used by
    every other plant-scoped router (see ``core.tenancy``).
    """
    plant_id = scoped.plant_id
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        # ``AdminPlantPath`` already proved ``plant_id`` exists and is in scope
        # (it queries ``Plant.id`` to build the caller's ``PlantScope``), so a
        # missing row here would indicate a race (e.g. the plant was deleted
        # between scope resolution and this fetch), not an authorization gap.
        plant = await session.get(Plant, plant_id)
        if plant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="plant not found"
            )

        plant.latitude = payload.latitude
        plant.longitude = payload.longitude
        await session.flush()

        await AuditEventRepository(session).record(
            request,
            action="plant.location_updated",
            resource_type="plant",
            resource_id=str(plant.id),
            outcome="SUCCEEDED",
            details={
                "latitude": str(payload.latitude),
                "longitude": str(payload.longitude),
            },
        )
        await session.commit()

        return _plant_location_view(plant)
