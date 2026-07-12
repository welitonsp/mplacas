from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class HealthInputs:
    availability_percent: Decimal
    performance_percent: Decimal
    communication_percent: Decimal
    data_quality_score: Decimal
    active_critical_anomalies: int = 0
    active_warning_anomalies: int = 0


@dataclass(frozen=True, slots=True)
class PlantHealthIndex:
    score: Decimal
    classification: str
    components: dict[str, Decimal]
    penalties: dict[str, Decimal]


def _bounded(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("100"), value))


def calculate_plant_health(inputs: HealthInputs) -> PlantHealthIndex:
    """Calcula o Índice de Saúde da Usina sem IA e com pesos auditáveis."""

    components = {
        "availability": _bounded(inputs.availability_percent),
        "performance": _bounded(inputs.performance_percent),
        "communication": _bounded(inputs.communication_percent),
        "data_quality": _bounded(inputs.data_quality_score),
    }
    weighted = (
        components["availability"] * Decimal("0.35")
        + components["performance"] * Decimal("0.30")
        + components["communication"] * Decimal("0.20")
        + components["data_quality"] * Decimal("0.15")
    )

    penalties = {
        "critical_anomalies": Decimal(max(0, inputs.active_critical_anomalies)) * Decimal("12"),
        "warning_anomalies": Decimal(max(0, inputs.active_warning_anomalies)) * Decimal("3"),
    }
    score = _bounded(weighted - sum(penalties.values(), Decimal("0"))).quantize(Decimal("0.1"))

    if score >= Decimal("90"):
        classification = "EXCELLENT"
    elif score >= Decimal("75"):
        classification = "GOOD"
    elif score >= Decimal("60"):
        classification = "ATTENTION"
    elif score >= Decimal("40"):
        classification = "POOR"
    else:
        classification = "CRITICAL"

    return PlantHealthIndex(
        score=score,
        classification=classification,
        components=components,
        penalties=penalties,
    )
