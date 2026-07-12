from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum

from mplacas.billing.models import BillingReconciliation, UtilityBill, reconcile_bill


_ONE_DECIMAL = Decimal("0.1")
_THREE_DECIMALS = Decimal("0.001")


def _q1(value: Decimal) -> Decimal:
    return value.quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP)


def _q3(value: Decimal) -> Decimal:
    return value.quantize(_THREE_DECIMALS, rounding=ROUND_HALF_UP)


def _clamp_percent(value: Decimal) -> Decimal:
    return min(Decimal("100"), max(Decimal("0"), value))


class DiagnosticSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class EnergyDiagnostic:
    code: str
    severity: DiagnosticSeverity
    message: str
    recommended_action: str


@dataclass(frozen=True, slots=True)
class EnergyCycleIntelligence:
    reconciliation: BillingReconciliation
    grid_dependency_rate_percent: Decimal
    exported_generation_rate_percent: Decimal
    credit_coverage_rate_percent: Decimal
    bill_energy_component_brl: Decimal
    health_score: int
    diagnostics: tuple[EnergyDiagnostic, ...]


def analyze_energy_cycle(
    *,
    bill: UtilityBill,
    cycle_production_kwh: Decimal,
    expected_production_kwh: Decimal | None = None,
    missing_days: int = 0,
    provisional_days: int = 0,
) -> EnergyCycleIntelligence:
    """Calcula indicadores e diagnósticos auditáveis sem uso de IA generativa."""
    if missing_days < 0 or provisional_days < 0:
        raise ValueError("data quality counters cannot be negative")
    if expected_production_kwh is not None and expected_production_kwh < 0:
        raise ValueError("expected production cannot be negative")

    reconciliation = reconcile_bill(bill=bill, cycle_production_kwh=cycle_production_kwh)
    total_consumption = reconciliation.estimated_total_consumption_kwh
    grid_dependency = (
        reconciliation.imported_kwh / total_consumption * Decimal("100")
        if total_consumption
        else Decimal("0")
    )
    exported_rate = (
        reconciliation.injected_kwh / reconciliation.cycle_production_kwh * Decimal("100")
        if reconciliation.cycle_production_kwh
        else Decimal("0")
    )
    credit_coverage = (
        bill.compensated_kwh / bill.imported_kwh * Decimal("100")
        if bill.imported_kwh
        else Decimal("0")
    )
    energy_component = max(Decimal("0"), bill.total_amount_brl - bill.public_lighting_brl)

    score = 100
    diagnostics: list[EnergyDiagnostic] = []

    if missing_days:
        score -= min(40, missing_days * 8)
        diagnostics.append(
            EnergyDiagnostic(
                code="MISSING_DAILY_DATA",
                severity=DiagnosticSeverity.CRITICAL if missing_days >= 3 else DiagnosticSeverity.WARNING,
                message=f"O ciclo possui {missing_days} dia(s) sem produção consolidada.",
                recommended_action="Executar backfill e validar a comunicação dos microinversores.",
            )
        )

    if provisional_days:
        score -= min(15, provisional_days * 3)
        diagnostics.append(
            EnergyDiagnostic(
                code="PROVISIONAL_DAILY_DATA",
                severity=DiagnosticSeverity.WARNING,
                message=f"O ciclo possui {provisional_days} dia(s) ainda provisório(s).",
                recommended_action="Aguardar a consolidação D+1 antes de fechar o ciclo.",
            )
        )

    if expected_production_kwh and expected_production_kwh > 0:
        performance = cycle_production_kwh / expected_production_kwh * Decimal("100")
        if performance < Decimal("70"):
            score -= 30
            diagnostics.append(
                EnergyDiagnostic(
                    code="PRODUCTION_WELL_BELOW_EXPECTED",
                    severity=DiagnosticSeverity.CRITICAL,
                    message=f"A produção atingiu {_q1(performance)}% do valor esperado.",
                    recommended_action="Verificar comunicação, sombreamento, sujeira e disponibilidade dos equipamentos.",
                )
            )
        elif performance < Decimal("85"):
            score -= 15
            diagnostics.append(
                EnergyDiagnostic(
                    code="PRODUCTION_BELOW_EXPECTED",
                    severity=DiagnosticSeverity.WARNING,
                    message=f"A produção atingiu {_q1(performance)}% do valor esperado.",
                    recommended_action="Comparar a curva diária com clima, histórico e disponibilidade dos módulos.",
                )
            )

    if reconciliation.cycle_production_kwh == 0 and bill.imported_kwh > 0:
        score -= 35
        diagnostics.append(
            EnergyDiagnostic(
                code="ZERO_PRODUCTION_WITH_GRID_IMPORT",
                severity=DiagnosticSeverity.CRITICAL,
                message="Não houve produção registrada, mas houve consumo da rede.",
                recommended_action="Verificar imediatamente a comunicação e o funcionamento da usina.",
            )
        )

    if exported_rate > Decimal("85") and reconciliation.cycle_production_kwh > 0:
        score -= 5
        diagnostics.append(
            EnergyDiagnostic(
                code="LOW_SELF_CONSUMPTION",
                severity=DiagnosticSeverity.INFO,
                message=f"{_q1(exported_rate)}% da geração foi injetada na rede.",
                recommended_action="Avaliar o deslocamento de cargas para o período de geração solar.",
            )
        )

    if credit_coverage < Decimal("50") and bill.imported_kwh > 0:
        score -= 10
        diagnostics.append(
            EnergyDiagnostic(
                code="LOW_CREDIT_COVERAGE",
                severity=DiagnosticSeverity.WARNING,
                message=f"Os créditos compensaram {_q1(credit_coverage)}% da energia importada.",
                recommended_action="Revisar geração, consumo e saldo de créditos do ciclo.",
            )
        )

    if not diagnostics:
        diagnostics.append(
            EnergyDiagnostic(
                code="CYCLE_WITHIN_EXPECTED_PARAMETERS",
                severity=DiagnosticSeverity.INFO,
                message="O ciclo está dentro dos parâmetros avaliados.",
                recommended_action="Manter o acompanhamento periódico.",
            )
        )

    return EnergyCycleIntelligence(
        reconciliation=reconciliation,
        grid_dependency_rate_percent=_q1(_clamp_percent(grid_dependency)),
        exported_generation_rate_percent=_q1(_clamp_percent(exported_rate)),
        credit_coverage_rate_percent=_q1(_clamp_percent(credit_coverage)),
        bill_energy_component_brl=energy_component.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        health_score=max(0, min(100, score)),
        diagnostics=tuple(diagnostics),
    )
