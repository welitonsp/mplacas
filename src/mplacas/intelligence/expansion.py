"""Vale a pena ampliar a usina? (ADR-089).

Funções puras, só ``Decimal``, sem I/O. Responde, com as faturas e a produção
medida, se a usina deixou de cobrir o consumo — e de quanto seria a ampliação.

Regras (validadas com os especialistas de domínio e financeiro):

* **Déficit estrutural** = Σ consumo da rede − Σ envio registrado pelo medidor
  nos 12 últimos ciclos. Créditos atravessam meses (60 meses, Lei 14.300), por
  isso o balanço é anual; "créditos usados" não serve, porque inclui o saldo
  antigo que já acabou. O mínimo faturável (30/50/100 kWh) NÃO é descontado:
  pelo art. 16 §1º ele só pesa quando o consumo medido da rede fica abaixo do
  mínimo, e no layout SCEE atual o compensado já sai limitado pela fatura.
* **Veredito** pelo sinal do déficit, com tolerância de 5% do consumo da rede
  no ano: acima → AMPLIAR; abaixo de −5% → NAO_VALE; no meio → EQUILIBRADO.
  Antes disso: dados insuficientes → INDISPONIVEL; usina com problema
  (prejuízo, envio impossível ou produção muito abaixo do esperado) →
  CORRIGIR_ANTES. Suspeita (fração enviada à rede caiu) só gera aviso.
* **Tamanho** = déficit ÷ rendimento anual medido da própria usina
  (kWh/kWp/ano), só ciclos sem dia estimado. Vale para placas novas com a mesma
  orientação e inclinação — premissa declarada.
* **Dinheiro**: a parte ampliada pedida agora é GD II (art. 26 §2º III) e paga
  a parcela do Fio B do art. 27 (60% 2026, 75% 2027, 90% 2028). De 2029 em
  diante vale o art. 17, ainda sem regra da ANEEL: Fio B integral, como
  cenário — nunca como fato. Valor de 1 kWh novo no ano y =
  tarifa cheia com impostos − Fio B pleno × parcela(y). A bandeira fica de
  fora (não é presumida). Sem tarifa cheia homologada ou Fio B na fatura, ou se
  a fatura refeita não fecha, não há valor em reais (``None`` com motivo).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from mplacas.intelligence.investor_metrics import months_between, wire_b_share

STATUS_EXPAND = "AMPLIAR"
STATUS_NOT_WORTH = "NAO_VALE"
STATUS_BALANCED = "EQUILIBRADO"
STATUS_FIX_FIRST = "CORRIGIR_ANTES"
STATUS_UNAVAILABLE = "INDISPONIVEL"

INVERTER_OK = "OK"
INVERTER_CHECK_DATASHEET = "VERIFICAR_DATASHEET"
INVERTER_NEW_NEEDED = "NOVO_INVERSOR"
INVERTER_MICRO = "MICROINVERSORES"
INVERTER_UNKNOWN = "DESCONHECIDO"

WINDOW_CYCLES = 12
MIN_MEASURED_CYCLES = 10
TOLERANCE_FRACTION = Decimal("0.05")
# Relação potência das placas ÷ potência do inversor (DC/AC). Até 1,30 é
# normal no Brasil Central; até 1,50 depende do datasheet (perda por corte de
# potência provável em Goiás); acima disso, outro inversor.
DC_AC_OK = Decimal("1.30")
DC_AC_LIMIT = Decimal("1.50")
# Abaixo disso de consumo da rede num ciclo, o mínimo faturável pode pesar
# (30/50/100 kWh conforme a ligação, que o sistema não conhece).
MINIMUM_BILLING_WARNING_KWH = Decimal("100")
FIRST_SCENARIO_YEAR = 2029
LAST_TRANSITION_YEAR = 2028
# Prejuízo e envio impossível bloqueiam. Suspeita (fração enviada à rede
# caiu) NÃO bloqueia: é justamente o sinal de consumo diurno maior — vira aviso.
_PROBLEM_VERDICTS = frozenset({"LOSS", "IMPOSSIBLE"})
_DAYS_PER_YEAR = Decimal("365")
_ONE_DECIMAL = Decimal("0.1")
_CENTS = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class ExpansionCycle:
    reference_month: str
    imported_kwh: Decimal | None
    meter_export_kwh: Decimal | None
    production_kwh: Decimal | None
    # Ciclo com dia estimado/sem leitura: não entra no rendimento.
    production_estimated: bool
    cycle_days: int | None
    utility_verdict: str
    production_well_below_expected: bool
    generation_share_percent: Decimal | None
    credit_balance_kwh: Decimal | None


@dataclass(frozen=True, slots=True)
class MoneyInputs:
    """Preços do ciclo mais recente (todos com impostos, da própria fatura)."""

    reference_month: str
    full_tariff_brl_kwh: Decimal | None
    wire_b_tariff_brl_kwh: Decimal | None
    # Fatura refeita com esses preços fecha com a real (credit_unit_value_brl
    # não é None) — senão o kWh compensado custava outra coisa.
    model_matches_bill: bool
    # Usina atual comprovadamente na regra do art. 27 (Fio B na fatura e
    # ligada depois da janela de 2023): só aí o Fio B pleno sai da fatura.
    regime_confirmed: bool


@dataclass(frozen=True, slots=True)
class YearValue:
    year: int
    wire_b_share: Decimal
    value_brl_kwh: Decimal
    scenario: bool


@dataclass(frozen=True, slots=True)
class ExpansionMoney:
    unavailable_reason: str | None
    request_year: int
    values_by_year: tuple[YearValue, ...] = ()
    monthly_saving_first_year_brl: Decimal | None = None
    monthly_saving_scenario_brl: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ExpansionAssessment:
    status: str
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    first_month: str | None
    last_month: str | None
    cycles_used: int
    imported_kwh_total: Decimal | None = None
    exported_kwh_total: Decimal | None = None
    deficit_kwh_year: Decimal | None = None
    deficit_kwh_month: Decimal | None = None
    # FALTA, SOBRA ou ZERO — o rótulo vem pronto, a tela não decide pelo sinal.
    direction: str | None = None
    tolerance_kwh_year: Decimal | None = None
    balance_before_kwh: Decimal | None = None
    balance_after_kwh: Decimal | None = None
    installed_kwp: Decimal | None = None
    measured_cycles: int = 0
    yield_kwh_per_kwp_year: Decimal | None = None
    extra_kwp: Decimal | None = None
    inverter_status: str = INVERTER_UNKNOWN
    dc_ac_ratio_after: Decimal | None = None
    money: ExpansionMoney | None = None
    problem_months: tuple[str, ...] = field(default=())


def year_values(
    *,
    full_tariff_brl_kwh: Decimal,
    wire_b_tariff_brl_kwh: Decimal,
    bill_year: int,
    request_year: int,
) -> tuple[YearValue, ...]:
    """Valor de 1 kWh da parte ampliada, do ano do pedido até 2029 (cenário).

    O Fio B da fatura já vem com a parcela do ano da fatura aplicada; o pleno
    é ele ÷ parcela(ano da fatura).
    """
    bill_share = wire_b_share(bill_year)
    full_wire_b = wire_b_tariff_brl_kwh / bill_share
    values: list[YearValue] = []
    start = min(max(request_year, 2026), FIRST_SCENARIO_YEAR)
    for year in range(start, FIRST_SCENARIO_YEAR + 1):
        share = wire_b_share(year)
        value = full_tariff_brl_kwh - full_wire_b * share
        values.append(
            YearValue(
                year=year,
                wire_b_share=share,
                value_brl_kwh=max(Decimal("0"), value).quantize(Decimal("0.000001")),
                scenario=year > LAST_TRANSITION_YEAR,
            )
        )
    return tuple(values)


def _money(
    *, deficit_kwh_year: Decimal, inputs: MoneyInputs | None, request_year: int
) -> ExpansionMoney:
    def unavailable(reason: str) -> ExpansionMoney:
        return ExpansionMoney(unavailable_reason=reason, request_year=request_year)

    if inputs is None or inputs.full_tariff_brl_kwh is None:
        return unavailable("FULL_TARIFF_MISSING")
    if inputs.wire_b_tariff_brl_kwh is None or inputs.wire_b_tariff_brl_kwh <= 0:
        return unavailable("WIRE_B_MISSING")
    if not inputs.regime_confirmed:
        return unavailable("REGIME_NOT_CONFIRMED")
    if not inputs.model_matches_bill:
        return unavailable("BILL_MODEL_MISMATCH")
    bill_year = int(inputs.reference_month[:4])
    if bill_year > LAST_TRANSITION_YEAR:
        # Fio B do art. 17 (2029+) ainda sem regra: não dá para deduzir o pleno.
        return unavailable("TRANSITION_ENDED")
    if wire_b_share(bill_year) <= 0:
        return unavailable("REGIME_NOT_CONFIRMED")
    values = year_values(
        full_tariff_brl_kwh=inputs.full_tariff_brl_kwh,
        wire_b_tariff_brl_kwh=inputs.wire_b_tariff_brl_kwh,
        bill_year=bill_year,
        request_year=request_year,
    )
    monthly_kwh = deficit_kwh_year / 12
    first = values[0].value_brl_kwh * monthly_kwh
    scenario = values[-1].value_brl_kwh * monthly_kwh
    return ExpansionMoney(
        unavailable_reason=None,
        request_year=request_year,
        values_by_year=values,
        monthly_saving_first_year_brl=first.quantize(_CENTS, rounding=ROUND_HALF_UP),
        monthly_saving_scenario_brl=scenario.quantize(_CENTS, rounding=ROUND_HALF_UP),
    )


def inverter_check(
    *,
    installed_kwp: Decimal,
    extra_kwp: Decimal,
    device_count: int,
    inverter_ac_kw: Decimal | None,
) -> tuple[str, Decimal | None]:
    """Cabe no inversor atual? Microinversor (vários aparelhos) não tem
    relação da usina inteira: ampliar é somar microinversores."""
    if device_count > 1:
        return INVERTER_MICRO, None
    if device_count != 1 or inverter_ac_kw is None or inverter_ac_kw <= 0:
        return INVERTER_UNKNOWN, None
    ratio = ((installed_kwp + extra_kwp) / inverter_ac_kw).quantize(Decimal("0.01"))
    if ratio <= DC_AC_OK:
        return INVERTER_OK, ratio
    if ratio <= DC_AC_LIMIT:
        return INVERTER_CHECK_DATASHEET, ratio
    return INVERTER_NEW_NEEDED, ratio


def assess_expansion(
    *,
    cycles: list[ExpansionCycle],
    previous_balance_kwh: Decimal | None,
    installed_kwp: Decimal | None,
    device_count: int,
    inverter_ac_kw: Decimal | None,
    money_inputs: MoneyInputs | None,
    request_year: int,
) -> ExpansionAssessment:
    """``cycles`` em ordem cronológica, só ciclos posteriores à ligação."""
    window = cycles[-WINDOW_CYCLES:]
    first = window[0].reference_month if window else None
    last = window[-1].reference_month if window else None

    def unavailable(*reasons: str, **extra: object) -> ExpansionAssessment:
        return ExpansionAssessment(
            status=STATUS_UNAVAILABLE,
            reasons=reasons,
            warnings=(),
            first_month=first,
            last_month=last,
            cycles_used=len(window),
            installed_kwp=installed_kwp,
            **extra,  # type: ignore[arg-type]
        )

    if len(window) < WINDOW_CYCLES:
        return unavailable("NOT_ENOUGH_CYCLES")
    if months_between(window[0].reference_month, window[-1].reference_month) != WINDOW_CYCLES - 1:
        return unavailable("CYCLES_NOT_CONTIGUOUS")

    if any(c.imported_kwh is None or c.meter_export_kwh is None for c in window):
        return unavailable("MISSING_METER_OR_CONSUMPTION")
    shares = [c.generation_share_percent for c in window]
    if any(s is not None and s != Decimal("100") for s in shares) or shares[-1] != Decimal("100"):
        # Rateio ou autoconsumo remoto: o balanço teria de somar as outras UCs.
        return unavailable("SHARE_NOT_CONFIRMED")

    # Usina com problema: ampliar não resolve defeito nem perda. Vem depois do
    # rateio — com rateio < 100%, a conferência marca LOSS sem prova de perda.
    problem_months = tuple(
        c.reference_month for c in window if c.utility_verdict in _PROBLEM_VERDICTS
    ) + tuple(c.reference_month for c in window[-3:] if c.production_well_below_expected)
    if problem_months:
        return ExpansionAssessment(
            status=STATUS_FIX_FIRST,
            reasons=("PLANT_OR_UTILITY_PROBLEM",),
            warnings=(),
            first_month=first,
            last_month=last,
            cycles_used=len(window),
            installed_kwp=installed_kwp,
            problem_months=tuple(sorted(set(problem_months))),
        )

    imported = sum((c.imported_kwh for c in window if c.imported_kwh is not None), Decimal("0"))
    exported = sum(
        (c.meter_export_kwh for c in window if c.meter_export_kwh is not None), Decimal("0")
    )
    deficit = imported - exported
    tolerance = (imported * TOLERANCE_FRACTION).quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP)
    warnings: list[str] = []
    if any(c.utility_verdict == "SUSPECT" for c in window):
        warnings.append("SUSPECT_CYCLES")
    if any(
        c.imported_kwh is not None and c.imported_kwh < MINIMUM_BILLING_WARNING_KWH for c in window
    ):
        warnings.append("MINIMUM_BILLING_MAY_APPLY")

    base = dict(
        first_month=first,
        last_month=last,
        cycles_used=len(window),
        imported_kwh_total=imported,
        exported_kwh_total=exported,
        deficit_kwh_year=deficit,
        deficit_kwh_month=(deficit / 12).quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP),
        direction="FALTA" if deficit > 0 else "SOBRA" if deficit < 0 else "ZERO",
        tolerance_kwh_year=tolerance,
        balance_before_kwh=previous_balance_kwh,
        balance_after_kwh=window[-1].credit_balance_kwh,
        installed_kwp=installed_kwp,
    )

    if deficit < -tolerance:
        return ExpansionAssessment(
            status=STATUS_NOT_WORTH,
            reasons=(),
            warnings=tuple(warnings),
            **base,  # type: ignore[arg-type]
        )
    if deficit <= tolerance:
        return ExpansionAssessment(
            status=STATUS_BALANCED,
            reasons=(),
            warnings=tuple(warnings),
            **base,  # type: ignore[arg-type]
        )

    # AMPLIAR: tamanho pelo rendimento anual medido da própria usina.
    measured = [
        c
        for c in window
        if not c.production_estimated
        and c.production_kwh is not None
        and c.production_kwh > 0
        and c.cycle_days
    ]
    money = _money(deficit_kwh_year=deficit, inputs=money_inputs, request_year=request_year)
    if installed_kwp is None or installed_kwp <= 0:
        return ExpansionAssessment(
            status=STATUS_EXPAND,
            reasons=("INSTALLED_POWER_UNKNOWN",),
            warnings=tuple(warnings),
            measured_cycles=len(measured),
            money=money,
            **base,  # type: ignore[arg-type]
        )
    if len(measured) < MIN_MEASURED_CYCLES:
        return ExpansionAssessment(
            status=STATUS_EXPAND,
            reasons=("NOT_ENOUGH_MEASURED_PRODUCTION",),
            warnings=tuple(warnings),
            measured_cycles=len(measured),
            money=money,
            **base,  # type: ignore[arg-type]
        )
    production = sum((c.production_kwh for c in measured if c.production_kwh), Decimal("0"))
    days = sum((c.cycle_days or 0 for c in measured), 0)
    yield_year = production / Decimal(days) * _DAYS_PER_YEAR / installed_kwp
    extra = (deficit / yield_year).quantize(_ONE_DECIMAL, rounding=ROUND_CEILING)
    inverter_status, ratio = inverter_check(
        installed_kwp=installed_kwp,
        extra_kwp=extra,
        device_count=device_count,
        inverter_ac_kw=inverter_ac_kw,
    )
    return ExpansionAssessment(
        status=STATUS_EXPAND,
        reasons=(),
        warnings=tuple(warnings),
        measured_cycles=len(measured),
        yield_kwh_per_kwp_year=yield_year.quantize(Decimal("1"), rounding=ROUND_HALF_UP),
        extra_kwp=extra,
        inverter_status=inverter_status,
        dc_ac_ratio_after=ratio,
        money=money,
        **base,  # type: ignore[arg-type]
    )
