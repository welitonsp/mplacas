from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AnomalyType(StrEnum):
    COMMUNICATION_LOSS = "COMMUNICATION_LOSS"
    ZERO_PRODUCTION = "ZERO_PRODUCTION"
    LOW_DAILY_YIELD = "LOW_DAILY_YIELD"


@dataclass(frozen=True, slots=True)
class Anomaly:
    anomaly_type: AnomalyType
    severity: Severity
    evidence: str
    recommended_action: str


class AnomalyEngine:
    def detect_communication_loss(
        self,
        *,
        last_update: datetime | None,
        now: datetime,
        threshold: timedelta = timedelta(minutes=30),
    ) -> Anomaly | None:
        if last_update is None or now - last_update > threshold:
            return Anomaly(
                anomaly_type=AnomalyType.COMMUNICATION_LOSS,
                severity=Severity.WARNING,
                evidence="Equipamento sem atualização dentro da janela esperada.",
                recommended_action="Confirmar internet, energia e estado do microinversor.",
            )
        return None

    def detect_daily_yield(
        self,
        *,
        energy_kwh: Decimal,
        installed_power_kwp: Decimal,
        minimum_specific_yield: Decimal = Decimal("0.50"),
    ) -> Anomaly | None:
        if energy_kwh == 0:
            return Anomaly(
                anomaly_type=AnomalyType.ZERO_PRODUCTION,
                severity=Severity.CRITICAL,
                evidence="Produção diária consolidada igual a zero.",
                recommended_action="Verificar comunicação, rede elétrica e alarmes do equipamento.",
            )
        specific_yield = energy_kwh / installed_power_kwp
        if specific_yield < minimum_specific_yield:
            return Anomaly(
                anomaly_type=AnomalyType.LOW_DAILY_YIELD,
                severity=Severity.WARNING,
                evidence=f"Geração específica de {specific_yield:.3f} kWh/kWp.",
                recommended_action="Comparar com clima e histórico antes de solicitar manutenção.",
            )
        return None
