"""Domain operations on plants, independent of the HTTP layer.

The router owns the transaction boundary (opening the session, applying the
tenant context, recording the audit event and committing); this service owns
the queries, the field-level mutation rules and the response views. It raises
domain errors instead of ``HTTPException`` so it can be exercised without a
FastAPI app.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.core.authorization import PlantScope
from mplacas.db.models import Device, Plant
from mplacas.organizations.db_models import OrganizationRecord
from mplacas.plants.schemas import (
    DevicePowerConfigurationView,
    ModuleTechnology,
    PlantFinancialConfigurationUpdateRequest,
    PlantFinancialConfigurationView,
    PlantLocationUpdateRequest,
    PlantSetupItem,
    PlantSetupItemKey,
    PlantSetupView,
    PlantTechnicalConfigurationUpdateRequest,
    PlantTechnicalConfigurationView,
)

# Plain plant columns that the technical-configuration payload maps 1:1.
# ``dc_capacity_kwp`` (stored as ``installed_power_kwp``) and
# ``module_technology`` (stored as the enum's value) need translation and are
# handled separately.
_TECHNICAL_PASSTHROUGH_FIELDS = (
    "ac_capacity_kw",
    "array_tilt_degrees",
    "array_azimuth_degrees",
    "commissioned_on",
)
_FINANCIAL_FIELDS = ("investment_amount_brl", "investment_recorded_on")


class PlantNotFoundError(LookupError):
    """The plant does not exist (or is not visible under the tenant context)."""


class DeviceNotFoundError(LookupError):
    """At least one requested device does not belong to the plant."""


@dataclass(frozen=True, slots=True)
class PlantListEntry:
    plant: Plant
    is_default: bool


class PlantService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_visible(
        self,
        *,
        organization_id: uuid.UUID | None,
        plant_scope: PlantScope,
    ) -> list[PlantListEntry]:
        """List plants visible to a caller (ADR-069, Etapa A + E8).

        ``organization_id`` is ``None`` for a static platform operational key,
        which lists across every organization. The result is then intersected
        with ``plant_scope``, since a persisted credential (ADR-043) may carry
        a scope restricted to a subset of the organization's plants.

        ``is_default`` is resolved per plant against *its own* organization's
        ``default_plant_id`` (ADR-069, § E.8) -- never a single global
        default -- using one bulk query to avoid an N+1 per item.
        """
        statement = select(Plant).order_by(Plant.name, Plant.id)
        if organization_id is not None:
            statement = statement.where(Plant.organization_id == organization_id)
        plants = list(await self._session.scalars(statement))

        default_plant_ids = await self._default_plant_ids(
            {plant.organization_id for plant in plants}
        )
        return [
            PlantListEntry(
                plant=plant,
                is_default=default_plant_ids.get(plant.organization_id) == plant.id,
            )
            for plant in plants
            if plant_scope.allows(plant.id)
        ]

    async def get(self, plant_id: uuid.UUID) -> Plant:
        plant = await self._session.get(Plant, plant_id)
        if plant is None:
            raise PlantNotFoundError(plant_id)
        return plant

    async def technical_configuration(self, plant: Plant) -> PlantTechnicalConfigurationView:
        devices = (
            await self._session.scalars(
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

    async def update_technical_configuration(
        self,
        plant: Plant,
        payload: PlantTechnicalConfigurationUpdateRequest,
    ) -> None:
        """Apply only the fields present in the payload, then flush.

        Raises ``DeviceNotFoundError`` -- after the plant fields may already
        have been mutated -- when any requested device is not on this plant;
        the caller must roll back so the update stays atomic.
        """
        plant_fields = payload.model_fields_set - {"devices"}
        if "dc_capacity_kwp" in plant_fields:
            plant.installed_power_kwp = payload.dc_capacity_kwp
        for field_name in _TECHNICAL_PASSTHROUGH_FIELDS:
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
                await self._session.scalars(
                    select(Device).where(
                        Device.plant_id == plant.id,
                        Device.id.in_(requested_ids),
                    )
                )
            ).all()
            devices_by_id = {device.id: device for device in device_rows}
            if devices_by_id.keys() != requested_ids:
                raise DeviceNotFoundError(requested_ids - devices_by_id.keys())
            for item in payload.devices:
                device = devices_by_id[item.device_id]
                if "dc_capacity_kwp" in item.model_fields_set:
                    device.dc_capacity_kwp = item.dc_capacity_kwp
                if "ac_capacity_kw" in item.model_fields_set:
                    device.ac_capacity_kw = item.ac_capacity_kw

        await self._session.flush()

    @staticmethod
    def financial_configuration(plant: Plant) -> PlantFinancialConfigurationView:
        return PlantFinancialConfigurationView(
            plant_id=plant.id,
            investment_amount_brl=plant.investment_amount_brl,
            investment_recorded_on=plant.investment_recorded_on,
        )

    async def update_financial_configuration(
        self,
        plant: Plant,
        payload: PlantFinancialConfigurationUpdateRequest,
    ) -> None:
        for field_name in _FINANCIAL_FIELDS:
            if field_name in payload.model_fields_set:
                setattr(plant, field_name, getattr(payload, field_name))
        await self._session.flush()

    async def setup_status(self, plant: Plant) -> PlantSetupView:
        """Estado do cadastro da usina: o que já foi informado e o que falta.

        Cada item libera uma parte do sistema (localização → clima e
        irradiância; potência → produção esperada; data de ligação → retorno
        do investimento; etc.). A regra de "feito" fica aqui, num lugar só.
        """
        rows = (
            await self._session.execute(
                select(UtilityBillRecord.status, func.count())
                .where(UtilityBillRecord.plant_id == plant.id)
                .group_by(UtilityBillRecord.status)
            )
        ).all()
        counts: dict[BillStatus, int] = {status: int(total) for status, total in rows}
        confirmed = int(counts.get(BillStatus.CONFIRMED, 0))
        pending = int(counts.get(BillStatus.PENDING_REVIEW, 0))
        done_by_key = {
            PlantSetupItemKey.LOCATION: plant.latitude is not None and plant.longitude is not None,
            PlantSetupItemKey.DC_CAPACITY: plant.installed_power_kwp is not None,
            PlantSetupItemKey.COMMISSIONED_ON: plant.commissioned_on is not None,
            PlantSetupItemKey.ORIENTATION: (
                plant.array_tilt_degrees is not None and plant.array_azimuth_degrees is not None
            ),
            PlantSetupItemKey.MODULE_TECHNOLOGY: plant.module_technology is not None,
            PlantSetupItemKey.INVESTMENT: plant.investment_amount_brl is not None,
            PlantSetupItemKey.CONFIRMED_BILL: confirmed > 0,
        }
        items = tuple(PlantSetupItem(key=key, done=done_by_key[key]) for key in PlantSetupItemKey)
        return PlantSetupView(
            plant_id=plant.id,
            name=plant.name,
            technical=await self.technical_configuration(plant),
            latitude=plant.latitude,
            longitude=plant.longitude,
            financial=self.financial_configuration(plant),
            confirmed_bills=confirmed,
            pending_bills=pending,
            items=items,
            completed=sum(1 for item in items if item.done),
            total=len(items),
        )

    async def update_location(self, plant: Plant, payload: PlantLocationUpdateRequest) -> None:
        plant.latitude = payload.latitude
        plant.longitude = payload.longitude
        await self._session.flush()

    async def _default_plant_ids(
        self, organization_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, uuid.UUID | None]:
        if not organization_ids:
            return {}
        rows = await self._session.execute(
            select(OrganizationRecord.id, OrganizationRecord.default_plant_id).where(
                OrganizationRecord.id.in_(organization_ids)
            )
        )
        return {row[0]: row[1] for row in rows.all()}
