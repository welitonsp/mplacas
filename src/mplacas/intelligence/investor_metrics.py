"""Métricas de investidor da usina: realizado versus CDI e projeção de vida útil (ADR-079).

Funções puras, só ``Decimal``, sem I/O. Duas camadas que nunca se misturam:

* **Realizado** — usa apenas economia de faturas confirmadas (snapshots) e o
  CDI efetivo de cada mês (BCB/SGS 4391). Compara dois caminhos para o mesmo
  dinheiro: (A) o investimento aplicado num CDB a 100% do CDI desde a ligação
  e (B) cada economia mensal aplicada no mesmo CDB. Os dois são líquidos de IR
  (tabela regressiva, cobrado no resgate sobre o ganho de cada aplicação). O
  caminho B NÃO inclui o valor da usina em si, que continua gerando: por isso,
  nos primeiros anos, A fica à frente — e é exatamente o que a projeção mostra
  se inverter.
* **Projeção** — fluxo de caixa mensal da vida útil (25 anos), com premissas
  explícitas e devolvidas junto do resultado: reajuste da tarifa, degradação
  dos módulos, O&M, troca do inversor, aumento do Fio B (Lei 14.300, art. 27)
  e CDI futuro constante. Resulta em TIR, VPL ao CDI líquido, paybacks e a
  evolução do patrimônio nos dois caminhos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext

_ONE = Decimal("1")
_HUNDRED = Decimal("100")
_CENTS = Decimal("0.01")
_DAYS_PER_MONTH = Decimal("30.4375")

# Lei 14.300/2022, art. 27: parcela do Fio B NÃO compensada para GD II
# (sistemas protocolados a partir de 07/01/2023), por ano. De 2029 em diante
# vale o art. 17, ainda sem regulamentação da ANEEL — premissa conservadora:
# Fio B integral (100%).
WIRE_B_SHARE_BY_YEAR: dict[int, Decimal] = {
    2023: Decimal("0.15"),
    2024: Decimal("0.30"),
    2025: Decimal("0.45"),
    2026: Decimal("0.60"),
    2027: Decimal("0.75"),
    2028: Decimal("0.90"),
}
WIRE_B_SHARE_FROM_2029 = Decimal("1.00")
GD_II_CUTOFF = date(2023, 1, 7)


def wire_b_share(year: int) -> Decimal:
    if year < 2023:
        return Decimal("0")
    return WIRE_B_SHARE_BY_YEAR.get(year, WIRE_B_SHARE_FROM_2029)


def income_tax_rate(days_held: Decimal) -> Decimal:
    """Tabela regressiva da renda fixa (vigente em 2026; a MP 1.303 caducou)."""
    if days_held <= 180:
        return Decimal("0.225")
    if days_held <= 360:
        return Decimal("0.20")
    if days_held <= 720:
        return Decimal("0.175")
    return Decimal("0.15")


def add_months(month: str, count: int) -> str:
    year, m = (int(part) for part in month.split("-"))
    total = year * 12 + (m - 1) + count
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def months_between(start: str, end: str) -> int:
    sy, sm = (int(part) for part in start.split("-"))
    ey, em = (int(part) for part in end.split("-"))
    return (ey - sy) * 12 + (em - sm)


def _q(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _net_of_tax(principal: Decimal, gross: Decimal, months_held: int) -> Decimal:
    gain = gross - principal
    if gain <= 0:
        return gross
    return gross - gain * income_tax_rate(_DAYS_PER_MONTH * months_held)


# ---------------------------------------------------------------------------
# Realizado
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RealizedComparison:
    as_of_month: str
    months_elapsed: int
    investment_brl: Decimal
    accumulated_savings_brl: Decimal
    cycles_counted: int
    cdi_path_net_brl: Decimal  # A: investimento no CDB, líquido de IR
    solar_path_net_brl: Decimal  # B: economias aplicadas no CDB, líquido de IR
    cdi_accumulated_percent: Decimal  # CDI bruto acumulado no período


def realized_comparison(
    *,
    investment_brl: Decimal,
    start_month: str,
    savings_by_month: dict[str, Decimal],
    cdi_by_month: dict[str, Decimal],
    as_of_month: str,
) -> RealizedComparison | None:
    """Caminho A × caminho B até ``as_of_month``. ``None`` se faltar CDI."""
    if months_between(start_month, as_of_month) < 0:
        return None
    months = [
        add_months(start_month, k) for k in range(1, months_between(start_month, as_of_month) + 1)
    ]
    if any(month not in cdi_by_month for month in months):
        return None
    with localcontext() as ctx:
        ctx.prec = 34
        factor_from: dict[str, Decimal] = {}
        running = _ONE
        # fator acumulado do CDI de cada mês até o fim (de trás para frente)
        for month in reversed(months):
            factor_from[month] = running
            running *= _ONE + cdi_by_month[month] / _HUNDRED
        total_factor = running  # do mês seguinte à ligação até as_of

        cdi_gross = investment_brl * total_factor
        cdi_net = _net_of_tax(investment_brl, cdi_gross, len(months))

        solar_net = Decimal("0")
        accumulated = Decimal("0")
        counted = 0
        for month, saving in sorted(savings_by_month.items()):
            # Só ciclos posteriores à ligação, a mesma regra da projeção: a
            # fatura do mês da ligação é de geração parcial, e contá-la aqui
            # inflaria a cobertura (faturas ÷ meses decorridos) em 1.
            if month <= start_month or month > as_of_month:
                continue
            accumulated += saving
            counted += 1
            # economia do mês m entra no fim de m e rende de m+1 até as_of
            held = months_between(month, as_of_month)
            growth = _ONE if held <= 0 else factor_from[month]
            if saving > 0:
                solar_net += _net_of_tax(saving, saving * growth, held)
            else:
                solar_net += saving
        return RealizedComparison(
            as_of_month=as_of_month,
            months_elapsed=len(months),
            investment_brl=_q(investment_brl),
            accumulated_savings_brl=_q(accumulated),
            cycles_counted=counted,
            cdi_path_net_brl=_q(cdi_net),
            solar_path_net_brl=_q(solar_net),
            cdi_accumulated_percent=((total_factor - _ONE) * _HUNDRED).quantize(Decimal("0.01")),
        )


# ---------------------------------------------------------------------------
# Projeção
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InvestorPremises:
    cdi_per_year: Decimal  # ex.: 0.1365 (13,65% a.a.), CDI dos últimos 12 meses
    ipca_per_year: Decimal  # IPCA dos últimos 12 meses
    tariff_growth_per_year: Decimal  # reajuste anual da tarifa (padrão: IPCA)
    horizon_years: int = 25
    degradation_per_year: Decimal = Decimal("0.005")
    om_per_year_fraction: Decimal = Decimal("0.005")  # O&M: 0,5% do investimento ao ano
    inverter_replacement_year: int = 12
    inverter_replacement_fraction: Decimal = Decimal("0.15")
    long_term_income_tax: Decimal = Decimal("0.15")


@dataclass(frozen=True, slots=True)
class PatrimonyPoint:
    year: int
    cdi_path_brl: Decimal
    solar_path_brl: Decimal


@dataclass(frozen=True, slots=True)
class Projection:
    baseline_monthly_savings_brl: Decimal
    irr_per_year: Decimal | None
    irr_real_per_year: Decimal | None
    cdi_net_per_year: Decimal  # taxa líquida efetiva do CDB mantido até o horizonte
    npv_at_cdi_net_brl: Decimal
    payback_simple_months: int | None
    payback_discounted_months: int | None
    lifetime_savings_brl: Decimal
    wire_b_applied: bool
    patrimony: tuple[PatrimonyPoint, ...]


def _monthly_rate(per_year: Decimal) -> Decimal:
    return (_ONE + per_year) ** (_ONE / Decimal(12)) - _ONE


def _npv(flows: list[Decimal], monthly_rate: Decimal) -> Decimal:
    total = Decimal("0")
    discount = _ONE
    step = _ONE / (_ONE + monthly_rate)
    for flow in flows:
        total += flow * discount
        discount *= step
    return total


def _irr_monthly(flows: list[Decimal]) -> Decimal | None:
    """TIR mensal por bisseção; ``None`` se o fluxo nunca fica positivo."""
    if sum(flows) <= 0 or flows[0] >= 0:
        return None
    low, high = Decimal("-0.99"), Decimal("1")
    if _npv(flows, high) > 0:
        return None
    for _ in range(80):
        mid = (low + high) / 2
        if _npv(flows, mid) > 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def project(
    *,
    investment_brl: Decimal,
    start_month: str,
    commissioned_on: date,
    savings_by_month: dict[str, Decimal],
    compensated_kwh_per_month: Decimal | None,
    wire_b_tariff_brl_kwh: Decimal | None,
    wire_b_reference_year: int | None,
    premises: InvestorPremises,
) -> Projection | None:
    """Fluxo de caixa mensal da vida útil. ``None`` sem nenhuma economia real."""
    realized = {m: v for m, v in savings_by_month.items() if m > start_month}
    if not realized or investment_brl <= 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 34
        baseline = sum(realized.values(), Decimal("0")) / len(realized)
        last_realized = max(realized)
        anchor = months_between(start_month, last_realized)
        growth = _ONE + premises.tariff_growth_per_year
        inflation = _ONE + premises.ipca_per_year

        # Fio B: só GD II, e só quando a fatura trouxe a tarifa do Fio B do
        # ano de referência (para inferir a tarifa cheia).
        reference_share = (
            wire_b_share(wire_b_reference_year) if wire_b_reference_year else Decimal("0")
        )
        wire_b_applied = (
            commissioned_on >= GD_II_CUTOFF
            and compensated_kwh_per_month is not None
            and wire_b_tariff_brl_kwh is not None
            and reference_share > 0
        )
        wire_b_full = (
            wire_b_tariff_brl_kwh / reference_share
            if wire_b_applied and wire_b_tariff_brl_kwh is not None
            else Decimal("0")
        )

        horizon = premises.horizon_years * 12
        flows: list[Decimal] = [-investment_brl]
        lifetime_savings = Decimal("0")
        for k in range(1, horizon + 1):
            month = add_months(start_month, k)
            if month in realized:
                saving = realized[month]
            else:
                years_after_anchor = Decimal(max(0, k - anchor)) / Decimal(12)
                tariff_factor = growth**years_after_anchor
                degradation = (_ONE - premises.degradation_per_year) ** (Decimal(k) / Decimal(12))
                saving = baseline * tariff_factor * degradation
                if wire_b_applied and compensated_kwh_per_month is not None:
                    year = int(month[:4])
                    extra_share = max(Decimal("0"), wire_b_share(year) - reference_share)
                    saving -= compensated_kwh_per_month * wire_b_full * extra_share * tariff_factor
            lifetime_savings += saving
            years = Decimal(k) / Decimal(12)
            cost = investment_brl * premises.om_per_year_fraction / Decimal(12) * (inflation**years)
            if k == premises.inverter_replacement_year * 12:
                cost += (
                    investment_brl
                    * premises.inverter_replacement_fraction
                    * (inflation ** Decimal(premises.inverter_replacement_year))
                )
            flows.append(saving - cost)

        # Régua: CDB a 100% do CDI comprado na ligação e resgatado no mês k,
        # com IR regressivo sobre o ganho NO RESGATE — o mesmo método do
        # realizado. (A versão anterior descontava 15% da taxa todo ano, como
        # um come-cotas permanente, e subestimava o CDB em ~25% em 25 anos.)
        cdi_monthly = _monthly_rate(premises.cdi_per_year)
        g = _ONE + cdi_monthly
        powers = [_ONE]
        for _ in range(horizon):
            powers.append(powers[-1] * g)
        # Valor líquido, n meses depois, de R$ 1 aplicado: bruto menos IR
        # sobre o ganho pela tabela regressiva do prazo.
        net_factor = [
            p - (p - _ONE) * income_tax_rate(_DAYS_PER_MONTH * n) if p > _ONE else p
            for n, p in enumerate(powers)
        ]

        def cdi_path(k: int) -> Decimal:
            return investment_brl * net_factor[k]

        def solar_path(k: int) -> Decimal:
            # Cada fluxo do mês j é aplicado no CDB e resgatado em k, com IR
            # próprio pelo prazo k − j. Custo (fluxo negativo) é retirada: tira
            # o valor e o rendimento bruto que ele teria, sem IR.
            total = Decimal("0")
            for j in range(1, k + 1):
                flow = flows[j]
                total += flow * (net_factor[k - j] if flow > 0 else powers[k - j])
            return total

        solar_series = [Decimal("0")]
        for k in range(1, horizon + 1):
            solar_series.append(solar_path(k))

        # Taxa líquida efetiva de quem fica no CDB até o fim do horizonte:
        # (líquido no resgate ÷ aplicado)^(1/anos) − 1. É a taxa de desconto do
        # VPL e a régua contra a TIR.
        cdi_net_year = net_factor[horizon] ** (_ONE / Decimal(premises.horizon_years)) - _ONE
        discount_monthly = _monthly_rate(cdi_net_year)
        npv = _npv(flows, discount_monthly)

        irr_m = _irr_monthly(flows)
        irr_year = (_ONE + irr_m) ** 12 - _ONE if irr_m is not None else None
        irr_real = (_ONE + irr_year) / inflation - _ONE if irr_year is not None else None

        payback_simple: int | None = None
        cumulative = Decimal("0")
        for k, flow in enumerate(flows):
            cumulative += flow
            if payback_simple is None and k > 0 and cumulative >= 0:
                payback_simple = k
                break
        # "Contando o CDI": primeiro mês em que as economias aplicadas no CDB
        # valem, líquidas, tanto quanto o investimento teria rendido no CDB.
        # É exatamente o cruzamento das linhas do gráfico de patrimônio.
        payback_disc = next(
            (k for k in range(1, horizon + 1) if solar_series[k] >= cdi_path(k)), None
        )

        patrimony = [
            PatrimonyPoint(
                year=k // 12,
                cdi_path_brl=_q(cdi_path(k)),
                solar_path_brl=_q(solar_series[k]),
            )
            for k in range(0, horizon + 1, 12)
        ]

        return Projection(
            baseline_monthly_savings_brl=_q(baseline),
            irr_per_year=irr_year.quantize(Decimal("0.0001")) if irr_year is not None else None,
            irr_real_per_year=irr_real.quantize(Decimal("0.0001"))
            if irr_real is not None
            else None,
            cdi_net_per_year=cdi_net_year.quantize(Decimal("0.0001")),
            npv_at_cdi_net_brl=_q(npv),
            payback_simple_months=payback_simple,
            payback_discounted_months=payback_disc,
            lifetime_savings_brl=_q(lifetime_savings),
            wire_b_applied=wire_b_applied,
            patrimony=tuple(patrimony),
        )


def annualize(monthly_percents: list[Decimal]) -> Decimal:
    """Taxa anual (fração) encadeando taxas mensais em %: Π(1 + r/100) − 1."""
    with localcontext() as ctx:
        ctx.prec = 34
        factor = _ONE
        for rate in monthly_percents:
            factor *= _ONE + rate / _HUNDRED
        return factor - _ONE
