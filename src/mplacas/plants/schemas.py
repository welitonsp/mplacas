"""Request and response models for the ``/plants`` API.

Moved verbatim from ``plants.router`` so that ``plants.service`` can build the
response views without importing the HTTP layer.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class PlantExpansionProposalUpdateRequest(BaseModel):
    """Proposta de ampliação (ADR-089, etapa 2): valor TOTAL da proposta
    (placas, inversor, instalação, homologação). ``amount_brl=None`` apaga a
    proposta. A data é a do registro, gravada pelo servidor."""

    model_config = ConfigDict(extra="forbid")

    amount_brl: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    includes_inverter: bool = False


class PlantExpansionProposalView(BaseModel):
    plant_id: uuid.UUID
    amount_brl: Decimal | None
    includes_inverter: bool | None
    recorded_on: date | None


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


class PlantSetupItemKey(str, enum.Enum):
    """Itens do cadastro da usina, na ordem em que a tela os apresenta.

    A regra de "feito" de cada item mora em ``PlantService.setup_status`` — a
    tela só mostra; nunca decide sozinha o que falta.
    """

    LOCATION = "LOCATION"
    DC_CAPACITY = "DC_CAPACITY"
    COMMISSIONED_ON = "COMMISSIONED_ON"
    ORIENTATION = "ORIENTATION"
    MODULE_TECHNOLOGY = "MODULE_TECHNOLOGY"
    INVESTMENT = "INVESTMENT"
    CONFIRMED_BILL = "CONFIRMED_BILL"


class PlantSetupItem(BaseModel):
    key: PlantSetupItemKey
    done: bool


class PlantSetupView(BaseModel):
    """Tudo o que o dono da usina informou (ou falta informar), numa leitura.

    Base da área "Dados da usina": o checklist e os formulários pré-preenchidos.
    """

    plant_id: uuid.UUID
    name: str
    technical: PlantTechnicalConfigurationView
    latitude: Decimal | None
    longitude: Decimal | None
    financial: PlantFinancialConfigurationView
    confirmed_bills: int
    pending_bills: int
    items: tuple[PlantSetupItem, ...]
    completed: int
    total: int
