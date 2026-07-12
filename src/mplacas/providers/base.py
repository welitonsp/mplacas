from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


class ProviderError(RuntimeError):
    """Erro base de integração com provedor externo."""


class ProviderAuthError(ProviderError):
    """Falha de autenticação sem exposição de credenciais."""


class ProviderSchemaError(ProviderError):
    """Resposta incompatível com o contrato esperado."""


class ProviderUnavailableError(ProviderError):
    """Serviço externo temporariamente indisponível."""


@dataclass(frozen=True, slots=True)
class SolarDevice:
    serial_number: str
    model_name: str | None
    city: str | None
    last_update: datetime | None


@dataclass(frozen=True, slots=True)
class DeviceOverview:
    serial_number: str
    current_power_w: Decimal
    today_energy_kwh: Decimal
    last_update: datetime | None
    status: str | None


@dataclass(frozen=True, slots=True)
class DailyEnergy:
    production_date: date
    energy_kwh: Decimal


class SolarProvider(ABC):
    @abstractmethod
    async def list_devices(self) -> list[SolarDevice]: ...

    @abstractmethod
    async def get_overview(self, serial_number: str) -> DeviceOverview: ...

    @abstractmethod
    async def get_daily_energy(
        self, serial_number: str, start: date, end: date
    ) -> list[DailyEnergy]: ...
