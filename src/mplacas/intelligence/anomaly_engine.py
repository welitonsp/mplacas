from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum


_ONE_DECIMAL = Decimal("0.1")
_THREE_DECIMALS = Decimal("0.001")

#: A day counts as "low irradiation" when its irradiation falls below this
#: fraction of the local median irradiation for the analyzed window. Fixed
#: absolute thresholds (e.g. "below 2.0 kWh/m^2") do not generalize across
#: locations/seasons: real production data from Caldas Novas/GO showed a
#: 92-day minimum of 2.79 kWh/m^2, so an absolute 2.0 threshold never fired
#: and every cloudy day was misclassified as an unexplained anomaly.
DEFAULT_LOW_IRRADIATION_RELATIVE_THRESHOLD = Decimal("0.75")

#: Minimum number of historical days required before the local median is
#: trusted to classify a day as "explained by low irradiation". With too
#: few samples the median is unstable (a single very sunny or very cloudy
#: day can swing it disproportionately). Below this count we deliberately
#: fail toward alerting: `is_low_irradiation` returns False, which means
#: the caller cannot claim the drop was "just the weather" — it has to
#: keep looking for a technical cause instead. Five days was chosen as a
#: pragmatic floor: a solar-production median converges reasonably by then
#: even with cloudy-day noise, while still being reachable within the first
#: week of a plant coming online.
DEFAULT_MINIMUM_IRRADIATION_SAMPLE_DAYS = 5


def is_low_irradiation(
    irradiation_kwh_m2: Decimal | None,
    irradiation_median_kwh_m2: Decimal | None,
    irradiation_sample_days: int,
    *,
    relative_threshold: Decimal = DEFAULT_LOW_IRRADIATION_RELATIVE_THRESHOLD,
    minimum_sample_days: int = DEFAULT_MINIMUM_IRRADIATION_SAMPLE_DAYS,
) -> bool:
    """Whether `irradiation_kwh_m2` is low relative to the local median.

    Returns False (never "explained by weather") whenever there is not
    enough information to trust the comparison: missing irradiation,
    missing/non-positive median, or too few historical samples to make the
    median reliable. Weather is only ever used to excuse a production drop
    when the evidence for it is solid.
    """
    if irradiation_kwh_m2 is None or irradiation_median_kwh_m2 is None:
        return False
    if irradiation_median_kwh_m2 <= 0:
        return False
    if irradiation_sample_days < minimum_sample_days:
        return False
    return irradiation_kwh_m2 < irradiation_median_kwh_m2 * relative_threshold


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
    #: Median irradiation over the analyzed window, excluding the day being
    #: assessed. Used to classify "low irradiation" relative to local
    #: conditions instead of a fixed absolute number. `None` when there is
    #: no historical window to compute it from.
    irradiation_median_kwh_m2: Decimal | None = None
    #: How many historical days fed `irradiation_median_kwh_m2`. Used to
    #: gate whether the median is trustworthy enough to explain a drop as
    #: weather (see `is_low_irradiation`).
    irradiation_sample_days: int = 0

    def validate(self) -> None:
        if self.actual_production_kwh < 0:
            raise ValueError("actual production cannot be negative")
        if self.expected_production_kwh is not None and self.expected_production_kwh < 0:
            raise ValueError("expected production cannot be negative")
        if self.irradiation_kwh_m2 is not None and self.irradiation_kwh_m2 < 0:
            raise ValueError("irradiation cannot be negative")
        if self.irradiation_median_kwh_m2 is not None and self.irradiation_median_kwh_m2 < 0:
            raise ValueError("irradiation median cannot be negative")
        if self.irradiation_sample_days < 0:
            raise ValueError("irradiation sample days cannot be negative")


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
    low_irradiation_relative_threshold: Decimal = DEFAULT_LOW_IRRADIATION_RELATIVE_THRESHOLD,
    minimum_irradiation_sample_days: int = DEFAULT_MINIMUM_IRRADIATION_SAMPLE_DAYS,
) -> DailyAnomalyAssessment:
    """Classify performance without assigning a cause that is not supported by evidence."""
    data.validate()
    thresholds = (
        attention_threshold_percent,
        anomaly_threshold_percent,
        critical_threshold_percent,
        low_irradiation_relative_threshold,
    )
    if any(value < 0 for value in thresholds):
        raise ValueError("thresholds cannot be negative")
    if minimum_irradiation_sample_days < 0:
        raise ValueError("minimum irradiation sample days cannot be negative")
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
    low_irradiation = is_low_irradiation(
        data.irradiation_kwh_m2,
        data.irradiation_median_kwh_m2,
        data.irradiation_sample_days,
        relative_threshold=low_irradiation_relative_threshold,
        minimum_sample_days=minimum_irradiation_sample_days,
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
