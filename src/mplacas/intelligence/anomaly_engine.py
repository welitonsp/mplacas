from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum


_ONE_DECIMAL = Decimal("0.1")
_THREE_DECIMALS = Decimal("0.001")


class AnomalyLevel(StrEnum):
    NORMAL = "NORMAL"
    ATTENTION = "ATTENTION"
    ANOMALY = "ANOMALY"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class DailyPerformanceInput:
    actual_production_kwh: Decimal
    expected_production_kwh: Decimal | None
    irradiation_kwh_m2: Decimal | None
    data_complete: bool = True

    def validate(self) -> None:
        if self.actual_production_kwh < 0:
            raise ValueError("actual production cannot be negative")
        if self.expected_production_kwh is not None and self.expected_production_kwh < 0:
            raise ValueError("expected production cannot be negative")
        if self.irradiation_kwh_m2 is not None and self.irradiation_kwh_m2 < 0:
            raise ValueError("irradiation cannot be negative")


@dataclass(frozen=True, slots=True)
class AnomalyDiagnostic:
    code: str
    level: AnomalyLevel
    message: str
    recommended_action: str


@dataclass(frozen=True, slots=True)
class DailyAnomalyAssessment:
    level: AnomalyLevel
    deviation_kwh: Decimal | None
    deviation_percent: Decimal | None
    climate_context_available: bool
    diagnostics: tuple[AnomalyDiagnostic, ...]


def assess_daily_performance(
    data: DailyPerformanceInput,
    *,
    attention_threshold_percent: Decimal = Decimal("15"),
    anomaly_threshold_percent: Decimal = Decimal("30"),
    critical_threshold_percent: Decimal = Decimal("50"),
    low_irradiation_threshold_kwh_m2: Decimal = Decimal("2.0"),
) -> DailyAnomalyAssessment:
    """Classify performance without assigning a cause that is not supported by evidence."""
    data.validate()
    thresholds = (
        attention_threshold_percent,
        anomaly_threshold_percent,
        critical_threshold_percent,
        low_irradiation_threshold_kwh_m2,
    )
    if any(value < 0 for value in thresholds):
        raise ValueError("thresholds cannot be negative")
    if not attention_threshold_percent <= anomaly_threshold_percent <= critical_threshold_percent:
        raise ValueError("anomaly thresholds must be ordered")

    if not data.data_complete:
        diagnostic = AnomalyDiagnostic(
            code="INCOMPLETE_INPUT_DATA",
            level=AnomalyLevel.ATTENTION,
            message="Os dados do dia estão incompletos; a classificação de desempenho é limitada.",
            recommended_action=(
                "Consolidar os dados de produção e clima antes de concluir a análise."
            ),
        )
        return DailyAnomalyAssessment(
            level=AnomalyLevel.ATTENTION,
            deviation_kwh=None,
            deviation_percent=None,
            climate_context_available=data.irradiation_kwh_m2 is not None,
            diagnostics=(diagnostic,),
        )

    if data.expected_production_kwh is None or data.expected_production_kwh == 0:
        diagnostic = AnomalyDiagnostic(
            code="EXPECTED_PRODUCTION_UNAVAILABLE",
            level=AnomalyLevel.ATTENTION,
            message="Não há produção esperada válida para calcular o desvio do dia.",
            recommended_action=(
                "Disponibilizar uma linha de base técnica antes de classificar anomalias."
            ),
        )
        return DailyAnomalyAssessment(
            level=AnomalyLevel.ATTENTION,
            deviation_kwh=None,
            deviation_percent=None,
            climate_context_available=data.irradiation_kwh_m2 is not None,
            diagnostics=(diagnostic,),
        )

    deviation_kwh = (data.actual_production_kwh - data.expected_production_kwh).quantize(
        _THREE_DECIMALS,
        rounding=ROUND_HALF_UP,
    )
    deviation_percent = (
        deviation_kwh / data.expected_production_kwh * Decimal("100")
    ).quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP)

    if deviation_percent >= -attention_threshold_percent:
        level = AnomalyLevel.NORMAL
    elif deviation_percent > -anomaly_threshold_percent:
        level = AnomalyLevel.ATTENTION
    elif deviation_percent > -critical_threshold_percent:
        level = AnomalyLevel.ANOMALY
    else:
        level = AnomalyLevel.CRITICAL

    diagnostics: list[AnomalyDiagnostic] = []
    low_irradiation = (
        data.irradiation_kwh_m2 is not None
        and data.irradiation_kwh_m2 < low_irradiation_threshold_kwh_m2
    )

    if level is AnomalyLevel.NORMAL:
        diagnostics.append(
            AnomalyDiagnostic(
                code="PERFORMANCE_WITHIN_EXPECTED_RANGE",
                level=level,
                message="A produção ficou dentro da faixa esperada pelos critérios atuais.",
                recommended_action="Manter o acompanhamento da série histórica.",
            )
        )
    elif low_irradiation:
        diagnostics.append(
            AnomalyDiagnostic(
                code="LOW_PRODUCTION_WITH_LOW_IRRADIATION",
                level=level,
                message="A produção ficou abaixo do esperado em um dia de baixa irradiação.",
                recommended_action="Acompanhar os próximos dias antes de atribuir causa técnica.",
            )
        )
    elif data.irradiation_kwh_m2 is None:
        diagnostics.append(
            AnomalyDiagnostic(
                code="LOW_PRODUCTION_WITHOUT_CLIMATE_CONTEXT",
                level=level,
                message=(
                    "A produção ficou abaixo do esperado, mas não há contexto "
                    "climático disponível."
                ),
                recommended_action=(
                    "Coletar dados climáticos e verificar disponibilidade e "
                    "comunicação do sistema."
                ),
            )
        )
    else:
        diagnostics.append(
            AnomalyDiagnostic(
                code="LOW_PRODUCTION_NOT_EXPLAINED_BY_LOW_IRRADIATION",
                level=level,
                message=(
                    "A produção ficou abaixo do esperado sem baixa irradiação "
                    "suficiente para explicar o desvio."
                ),
                recommended_action=(
                    "Verificar inversor, comunicação, sombreamento, sujeira e "
                    "indisponibilidade operacional."
                ),
            )
        )

    return DailyAnomalyAssessment(
        level=level,
        deviation_kwh=deviation_kwh,
        deviation_percent=deviation_percent,
        climate_context_available=data.irradiation_kwh_m2 is not None,
        diagnostics=tuple(diagnostics),
    )
