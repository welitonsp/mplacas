from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum

from mplacas.billing.models import BillingReconciliation, UtilityBill, reconcile_bill


_ONE_DECIMAL = Decimal("0.1")


def _q1(value: Decimal) -> Decimal:
    return value.quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP)


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


# Motivos explícitos de por que a economia estimada não pôde ser calculada —
# nunca mostrar R$ 0,00 nesses casos, ver EnergyCycleIntelligence.estimated_savings_brl.
SAVINGS_UNAVAILABLE_TARIFF_NOT_REGISTERED = "TARIFF_NOT_AVAILABLE"
SAVINGS_UNAVAILABLE_NO_CONSUMPTION_DATA = "NO_CONSUMPTION_DATA"


@dataclass(frozen=True, slots=True)
class EnergyCycleIntelligence:
    reconciliation: BillingReconciliation
    grid_dependency_rate_percent: Decimal
    exported_generation_rate_percent: Decimal
    credit_coverage_rate_percent: Decimal
    bill_energy_component_brl: Decimal
    health_score: int
    diagnostics: tuple[EnergyDiagnostic, ...]
    # Campos financeiros do ciclo (Etapa 7 — "Quanto custou?"). Espelham direto
    # os campos correspondentes de `UtilityBill`/`UtilityBillRecord`, exceto
    # `estimated_savings_brl`, que é calculado (ver fórmula abaixo).
    total_amount_brl: Decimal = Decimal("0")
    public_lighting_brl: Decimal = Decimal("0")
    tariff_with_taxes_brl_kwh: Decimal | None = None
    tariff_without_taxes_brl_kwh: Decimal | None = None
    credit_balance_kwh: Decimal = Decimal("0")
    # `None` quando a fatura não tem tarifa registrada — nunca um R$ 0,00
    # fabricado. Ver `savings_unavailable_reason` para o motivo explícito.
    estimated_savings_brl: Decimal | None = None
    savings_unavailable_reason: str | None = None


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
    energy_component = max(
        Decimal("0"),
        bill.total_amount_brl - bill.public_lighting_brl,
    )

    # Economia estimada do ciclo: quanto teria custado comprar da rede toda a
    # energia efetivamente consumida (produção autoconsumida + energia
    # importada), à tarifa cheia com impostos, menos o que a fatura realmente
    # cobrou pelo componente de energia (já líquido de iluminação pública).
    # Ou seja: custo hipotético sem geração própria − custo real do ciclo.
    # Exige `tariff_with_taxes_brl_kwh` na fatura — quando ausente, o valor é
    # `None` (nunca R$ 0,00 fabricado) e o motivo fica explícito em
    # `savings_unavailable_reason`.
    estimated_savings_brl: Decimal | None
    savings_unavailable_reason: str | None
    if bill.tariff_with_taxes_brl_kwh is None:
        estimated_savings_brl = None
        savings_unavailable_reason = SAVINGS_UNAVAILABLE_TARIFF_NOT_REGISTERED
    elif reconciliation.estimated_total_consumption_kwh <= 0:
        # Consumo total zero normalmente significa "ainda sem dado do ciclo",
        # não "usina não consumiu nada". Sem isso, a fórmula abaixo devolveria
        # `-energy_component` — um número real, mas que pareceria "você pagou
        # a mais" quando na verdade é ausência de dado. Mesmo princípio de
        # nunca fabricar um valor enganoso que rege o ramo de tarifa ausente.
        estimated_savings_brl = None
        savings_unavailable_reason = SAVINGS_UNAVAILABLE_NO_CONSUMPTION_DATA
    else:
        hypothetical_grid_cost = (
            reconciliation.estimated_total_consumption_kwh * bill.tariff_with_taxes_brl_kwh
        )
        estimated_savings_brl = (hypothetical_grid_cost - energy_component).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        savings_unavailable_reason = None

    score = 100
    diagnostics: list[EnergyDiagnostic] = []

    if missing_days:
        score -= min(40, missing_days * 8)
        diagnostics.append(
            EnergyDiagnostic(
                code="MISSING_DAILY_DATA",
                severity=(
                    DiagnosticSeverity.CRITICAL
                    if missing_days >= 3
                    else DiagnosticSeverity.WARNING
                ),
                message=f"O ciclo possui {missing_days} dia(s) sem produção consolidada.",
                recommended_action=(
                    "Executar backfill e validar a comunicação dos microinversores."
                ),
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
                    recommended_action=(
                        "Verificar comunicação, sombreamento, sujeira e disponibilidade "
                        "dos equipamentos."
                    ),
                )
            )
        elif performance < Decimal("85"):
            score -= 15
            diagnostics.append(
                EnergyDiagnostic(
                    code="PRODUCTION_BELOW_EXPECTED",
                    severity=DiagnosticSeverity.WARNING,
                    message=f"A produção atingiu {_q1(performance)}% do valor esperado.",
                    recommended_action=(
                        "Comparar a curva diária com clima, histórico e disponibilidade "
                        "dos módulos."
                    ),
                )
            )

    if reconciliation.cycle_production_kwh == 0 and bill.imported_kwh > 0:
        score -= 35
        diagnostics.append(
            EnergyDiagnostic(
                code="ZERO_PRODUCTION_WITH_GRID_IMPORT",
                severity=DiagnosticSeverity.CRITICAL,
                message="Não houve produção registrada, mas houve consumo da rede.",
                recommended_action=(
                    "Verificar imediatamente a comunicação e o funcionamento da usina."
                ),
            )
        )

    if exported_rate > Decimal("85") and reconciliation.cycle_production_kwh > 0:
        score -= 5
        diagnostics.append(
            EnergyDiagnostic(
                code="LOW_SELF_CONSUMPTION",
                severity=DiagnosticSeverity.INFO,
                message=f"{_q1(exported_rate)}% da geração foi injetada na rede.",
                recommended_action=(
                    "Avaliar o deslocamento de cargas para o período de geração solar."
                ),
            )
        )

    if credit_coverage < Decimal("50") and bill.imported_kwh > 0:
        score -= 10
        diagnostics.append(
            EnergyDiagnostic(
                code="LOW_CREDIT_COVERAGE",
                severity=DiagnosticSeverity.WARNING,
                message=(
                    f"Os créditos compensaram {_q1(credit_coverage)}% da energia importada."
                ),
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
        bill_energy_component_brl=energy_component.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        ),
        health_score=max(0, min(100, score)),
        diagnostics=tuple(diagnostics),
        total_amount_brl=bill.total_amount_brl,
        public_lighting_brl=bill.public_lighting_brl,
        tariff_with_taxes_brl_kwh=bill.tariff_with_taxes_brl_kwh,
        tariff_without_taxes_brl_kwh=bill.tariff_without_taxes_brl_kwh,
        credit_balance_kwh=bill.credit_balance_kwh,
        estimated_savings_brl=estimated_savings_brl,
        savings_unavailable_reason=savings_unavailable_reason,
    )
