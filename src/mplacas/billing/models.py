from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

# Plausible upper bound for a R$/kWh tariff field. The parser anchors these
# fields by ordinal column position on the bill line (see ADR-056), which is
# structurally fragile to a distributor layout shift — a shifted column can
# silently capture an unrelated monetary total (e.g. R$ 48,69) instead of the
# R$/kWh rate (e.g. R$ 0,175126). 5 R$/kWh is generous headroom over today's
# real Brazilian residential tariff with taxes (~R$ 0.80/kWh) while still
# catching any order-of-magnitude column mismatch.
_MAX_PLAUSIBLE_TARIFF_BRL_KWH = Decimal("5")
# Bandeira vermelha patamar 2 com tributos fica perto de R$ 0,10/kWh; 0,5 dá
# folga e ainda pega uma coluna deslocada (valor total no lugar do preço).
_MAX_PLAUSIBLE_FLAG_BRL_KWH = Decimal("0.5")


@dataclass(frozen=True, slots=True)
class UtilityBill:
    distributor: str
    reference_month: str
    cycle_start: date
    cycle_end: date
    billed_days: int
    imported_kwh: Decimal
    injected_kwh: Decimal
    compensated_kwh: Decimal
    credit_balance_kwh: Decimal
    total_amount_brl: Decimal
    public_lighting_brl: Decimal = Decimal("0")
    generation_cycle_kwh: Decimal | None = None
    tariff_with_taxes_brl_kwh: Decimal | None = None
    tariff_without_taxes_brl_kwh: Decimal | None = None
    wire_b_tariff_brl_kwh: Decimal | None = None
    # Bloco SCEE (ADR-084): % da geração rateada para esta UC
    # ("CADASTRO RATEIO GERAÇÃO: UC … = N%") e créditos que vencem antes da
    # próxima fatura ("SALDO A EXPIRAR EM 30 DIAS KWH"). `None` quando a
    # fatura não traz a linha — nunca um valor presumido.
    generation_share_percent: Decimal | None = None
    credits_expiring_30d_kwh: Decimal | None = None
    # Bandeira tarifária do ciclo, com tributos, somando as linhas "ADC
    # BANDEIRA …" (pode haver duas cores no mesmo ciclo). Só aparece quando há
    # consumo não compensado; ausente é `None`, nunca zero presumido.
    flag_tariff_brl_kwh: Decimal | None = None
    # Créditos da fatura que não vêm das placas (compensação por interrupção
    # — DIC/FIC/DMIC/DICRI — e Bônus de Itaipu), em valor absoluto. Saem da
    # economia: o dono teria esse desconto com ou sem usina.
    non_energy_credits_brl: Decimal | None = None

    def validate(self) -> None:
        if self.cycle_end < self.cycle_start:
            raise ValueError("billing cycle end cannot precede start")
        expected_days = (self.cycle_end - self.cycle_start).days + 1
        if self.billed_days != expected_days:
            raise ValueError("billed days do not match inclusive billing cycle")
        numeric_values = (
            self.imported_kwh,
            self.injected_kwh,
            self.compensated_kwh,
            self.credit_balance_kwh,
            self.total_amount_brl,
            self.public_lighting_brl,
        )
        if any(value < 0 for value in numeric_values):
            raise ValueError("bill values cannot be negative")
        if self.generation_cycle_kwh is not None and self.generation_cycle_kwh < 0:
            raise ValueError("bill values cannot be negative")
        if self.credits_expiring_30d_kwh is not None and self.credits_expiring_30d_kwh < 0:
            raise ValueError("bill values cannot be negative")
        if self.non_energy_credits_brl is not None and self.non_energy_credits_brl < 0:
            raise ValueError("bill values cannot be negative")
        if self.flag_tariff_brl_kwh is not None and not (
            Decimal("0") < self.flag_tariff_brl_kwh <= _MAX_PLAUSIBLE_FLAG_BRL_KWH
        ):
            raise ValueError(f"flag tariff outside plausible range: {self.flag_tariff_brl_kwh}")
        if self.generation_share_percent is not None and not (
            Decimal("0") <= self.generation_share_percent <= Decimal("100")
        ):
            raise ValueError("generation share must be between 0 and 100 percent")
        optional_tariff_fields = (
            ("tariff_with_taxes_brl_kwh", self.tariff_with_taxes_brl_kwh),
            ("tariff_without_taxes_brl_kwh", self.tariff_without_taxes_brl_kwh),
            ("wire_b_tariff_brl_kwh", self.wire_b_tariff_brl_kwh),
        )
        if any(value is not None and value < 0 for _, value in optional_tariff_fields):
            raise ValueError("bill values cannot be negative")
        # Fail closed on an implausible tariff rather than persist a value that
        # would silently become a fabricated savings figure downstream — see
        # ADR-056. A shifted regex capture (e.g. a total in R$ instead of a
        # R$/kWh rate) lands well outside this range, so it is rejected here
        # instead of being written to the database as a plausible-looking number.
        for name, value in optional_tariff_fields:
            if value is not None and not (0 < value <= _MAX_PLAUSIBLE_TARIFF_BRL_KWH):
                raise ValueError(
                    f"{name} is outside the plausible tariff range "
                    f"(0, {_MAX_PLAUSIBLE_TARIFF_BRL_KWH}] BRL/kWh: {value}"
                )


@dataclass(frozen=True, slots=True)
class BillingReconciliation:
    cycle_production_kwh: Decimal
    imported_kwh: Decimal
    injected_kwh: Decimal
    estimated_self_consumption_kwh: Decimal
    estimated_total_consumption_kwh: Decimal
    self_consumption_rate_percent: Decimal
    self_sufficiency_rate_percent: Decimal
    # Three-way reconciliation fields — present only when the bill includes
    # generation_cycle_kwh (the concessionária's generation meter reading).
    generation_cycle_kwh: Decimal | None = None
    meter_vs_injection_delta_kwh: Decimal | None = None
    origin_vs_meter_delta_kwh: Decimal | None = None
    # Energia injetada que passou do consumo do ciclo e virou crédito
    # ("EXCEDENTE RECEBIDO" na fatura SCEE). Só existe quando a fatura traz o
    # registro do medidor; sem ele, `None` — nunca um zero fabricado.
    excess_credit_kwh: Decimal | None = None


def reconcile_bill(*, bill: UtilityBill, cycle_production_kwh: Decimal) -> BillingReconciliation:
    bill.validate()
    if cycle_production_kwh < 0:
        raise ValueError("cycle production cannot be negative")
    # Energia que de fato saiu para a rede. Na fatura SCEE da Equatorial a
    # linha "INJEÇÃO SCEE" (`injected_kwh`) é a energia COMPENSADA no ciclo; a
    # injeção real é o registro "ENERGIA GERAÇÃO" do medidor
    # (`generation_cycle_kwh`). Conferido na fatura real de set/2026:
    # INJEÇÃO SCEE 221 = consumo 221; ENERGIA GERAÇÃO 235; 235 − 221 = 14 kWh
    # de "EXCEDENTE RECEBIDO". Usar 221 inflava o autoconsumo (e a economia)
    # pelos 14 kWh que viraram crédito. Sem o registro do medidor (layouts
    # antigos), `injected_kwh` continua sendo a melhor informação disponível.
    grid_injection = (
        bill.generation_cycle_kwh if bill.generation_cycle_kwh is not None else bill.injected_kwh
    )
    self_consumption = max(Decimal("0"), cycle_production_kwh - grid_injection)
    total_consumption = bill.imported_kwh + self_consumption
    self_consumption_rate = (
        self_consumption / cycle_production_kwh * Decimal("100")
        if cycle_production_kwh
        else Decimal("0")
    )
    self_sufficiency_rate = (
        self_consumption / total_consumption * Decimal("100")
        if total_consumption
        else Decimal("0")
    )

    generation_cycle_kwh = bill.generation_cycle_kwh
    excess_credit: Decimal | None
    if generation_cycle_kwh is not None:
        meter_vs_injection = (generation_cycle_kwh - bill.injected_kwh).quantize(Decimal("0.001"))
        origin_vs_meter = (cycle_production_kwh - generation_cycle_kwh).quantize(Decimal("0.001"))
        excess_credit = max(Decimal("0"), generation_cycle_kwh - bill.compensated_kwh).quantize(
            Decimal("0.001")
        )
    else:
        meter_vs_injection = None
        origin_vs_meter = None
        excess_credit = None

    return BillingReconciliation(
        cycle_production_kwh=cycle_production_kwh.quantize(Decimal("0.001")),
        imported_kwh=bill.imported_kwh,
        injected_kwh=grid_injection,
        estimated_self_consumption_kwh=self_consumption.quantize(Decimal("0.001")),
        estimated_total_consumption_kwh=total_consumption.quantize(Decimal("0.001")),
        self_consumption_rate_percent=self_consumption_rate.quantize(Decimal("0.1")),
        self_sufficiency_rate_percent=self_sufficiency_rate.quantize(Decimal("0.1")),
        generation_cycle_kwh=generation_cycle_kwh,
        meter_vs_injection_delta_kwh=meter_vs_injection,
        origin_vs_meter_delta_kwh=origin_vs_meter,
        excess_credit_kwh=excess_credit,
    )
