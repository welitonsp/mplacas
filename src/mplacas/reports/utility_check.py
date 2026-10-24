"""Conferência da distribuidora, ciclo a ciclo (ADR-084).

Responde a pergunta do dono: "estou tendo prejuízo com a distribuidora?".
Só usa o que já está gravado — fatura confirmada e snapshot do ciclo —, sem
recalcular nada (ADR-038).

O medidor da distribuidora não mede a produção: só registra o que SAI da casa
para a rede. A diferença para o inversor é o consumo simultâneo, não perda.
Por isso a conferência não compara produção com injeção como prova; ela
verifica o que a fatura permite provar e vigia o que é fisicamente possível:

1. ``CREDITS_MISSING`` — prejuízo comprovado pela própria fatura: créditos
   disponíveis (injeção do medidor + saldo anterior) − créditos usados ≠
   saldo novo. Todo kWh registrado tem de virar abatimento ou saldo.
2. ``IMPOSSIBLE_EXPORT`` — a distribuidora registrou mais envio à rede do que
   o inversor produziu no ciclo (com folga para a precisão do inversor).
3. ``EXPORT_SHARE_DROP`` — a fração da produção enviada à rede caiu muito
   abaixo do histórico. Suspeita, nunca prova: pode ser o medidor ou mais
   consumo durante o dia.

Sem dado para conferir, o veredito é ``UNVERIFIABLE`` com o motivo — nunca
"sem prejuízo" por omissão.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import median

from mplacas.billing.models import UtilityBill

# Créditos são kWh com 2 casas na fatura: diferença até 1 centésimo é
# arredondamento, não crédito sumido.
CREDIT_TOLERANCE_KWH = Decimal("0.01")
# Medição de energia do inversor não é de faturamento (±2–5%): só acusa
# envio impossível acima dessa folga.
INVERTER_TOLERANCE = Decimal("1.05")
# Queda da fração enviada à rede, em pontos percentuais abaixo da mediana dos
# ciclos anteriores, para virar suspeita. Larga de propósito: consumo diurno
# muda com a estação.
EXPORT_SHARE_DROP_PP = Decimal("20")
MIN_HISTORY_CYCLES = 3

VERDICT_OK = "OK"
VERDICT_SUSPECT = "SUSPECT"
VERDICT_LOSS = "LOSS"
VERDICT_IMPOSSIBLE = "IMPOSSIBLE"
VERDICT_UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True, slots=True)
class UtilityCheck:
    verdict: str
    # Créditos que não aparecem nem como abatimento nem como saldo (kWh).
    missing_credits_kwh: Decimal | None
    credits_available_kwh: Decimal | None
    credits_used_kwh: Decimal | None
    credit_balance_kwh: Decimal | None
    # Leitura do medidor (envio à rede) e saldo de partida usados na prova —
    # a tela cita estes números, nunca a injeção do snapshot.
    meter_export_kwh: Decimal | None
    previous_balance_kwh: Decimal | None
    # Fração da produção do inversor enviada à rede, segundo o medidor (%).
    export_share_percent: Decimal | None
    export_share_baseline_percent: Decimal | None
    reasons: tuple[str, ...]

    def as_payload(self) -> dict[str, object]:
        def text(value: Decimal | None) -> str | None:
            return None if value is None else str(value)

        return {
            "verdict": self.verdict,
            "missing_credits_kwh": text(self.missing_credits_kwh),
            "credits_available_kwh": text(self.credits_available_kwh),
            "credits_used_kwh": text(self.credits_used_kwh),
            "credit_balance_kwh": text(self.credit_balance_kwh),
            "meter_export_kwh": text(self.meter_export_kwh),
            "previous_balance_kwh": text(self.previous_balance_kwh),
            "export_share_percent": text(self.export_share_percent),
            "export_share_baseline_percent": text(self.export_share_baseline_percent),
            "reasons": list(self.reasons),
        }


def export_share(*, production_kwh: Decimal | None, bill: UtilityBill | None) -> Decimal | None:
    """Fração da produção enviada à rede, só com a leitura do medidor."""
    if production_kwh is None or production_kwh <= 0 or bill is None:
        return None
    if bill.generation_cycle_kwh is None:
        return None
    return (bill.generation_cycle_kwh / production_kwh * Decimal("100")).quantize(Decimal("0.1"))


def check_cycle(
    *,
    bill: UtilityBill | None,
    previous_bill: UtilityBill | None,
    production_kwh: Decimal | None,
    previous_export_shares: list[Decimal],
    production_estimated: bool = False,
    previous_bill_ambiguous: bool = False,
) -> UtilityCheck:
    """Confere um ciclo.

    ``production_estimated``: o total do inversor inclui dias estimados pelo
    sol ou o piso do medidor (ADR-082) — aí comparar inversor × medidor é
    circular, e os níveis 2 e 3 não rodam. ``previous_bill_ambiguous``: há
    mais de uma fatura confirmada, com saldos diferentes, no mês anterior
    (refaturamento) — o saldo de partida é incerto.
    """
    reasons: list[str] = []
    available = used = balance = missing = previous_balance = None
    unbalanced = False

    if bill is None:
        return UtilityCheck(
            VERDICT_UNVERIFIABLE, None, None, None, None, None, None, None, None, ("NO_BILL",)
        )

    # 1. Conservação dos créditos: injeção do medidor + saldo anterior =
    #    usado + saldo novo. Precisa da leitura do medidor e da fatura do mês
    #    anterior (o saldo de partida).
    if bill.generation_cycle_kwh is None:
        reasons.append("NO_METER_READING")
    elif previous_bill_ambiguous:
        reasons.append("AMBIGUOUS_PREVIOUS_BILL")
    elif previous_bill is None:
        reasons.append("NO_PREVIOUS_BILL")
    else:
        previous_balance = previous_bill.credit_balance_kwh
        available = bill.generation_cycle_kwh + previous_balance
        used = bill.compensated_kwh
        balance = bill.credit_balance_kwh
        gap = available - used - balance
        if gap > CREDIT_TOLERANCE_KWH:
            missing = gap
            reasons.append("CREDITS_MISSING")
        elif gap < -CREDIT_TOLERANCE_KWH:
            # Usou mais crédito do que havia: crédito recebido de outra UC,
            # fatura anterior errada ou compensação lida como consumo total.
            # A conta não fecha — não dá para afirmar nem prejuízo nem OK.
            unbalanced = True
            reasons.append("CREDITS_UNBALANCED")
        else:
            missing = Decimal("0")

    # 2. Envio impossível: o medidor não pode registrar mais saída do que o
    #    inversor produziu.
    if production_estimated:
        reasons.append("PRODUCTION_ESTIMATED")
    impossible = (
        not production_estimated
        and bill.generation_cycle_kwh is not None
        and production_kwh is not None
        and production_kwh > 0
        and bill.generation_cycle_kwh > production_kwh * INVERTER_TOLERANCE
    )
    if impossible:
        reasons.append("IMPOSSIBLE_EXPORT")
    elif production_kwh is None:
        reasons.append("NO_PRODUCTION")

    # 3. Fração enviada à rede muito abaixo do histórico.
    share = None if production_estimated else export_share(production_kwh=production_kwh, bill=bill)
    baseline = (
        Decimal(str(median(previous_export_shares))).quantize(Decimal("0.1"))
        if len(previous_export_shares) >= MIN_HISTORY_CYCLES
        else None
    )
    if share is not None and baseline is not None and share < baseline - EXPORT_SHARE_DROP_PP:
        reasons.append("EXPORT_SHARE_DROP")

    if missing is not None and missing > 0:
        verdict = VERDICT_LOSS
    elif impossible:
        verdict = VERDICT_IMPOSSIBLE
    elif "EXPORT_SHARE_DROP" in reasons:
        verdict = VERDICT_SUSPECT
    elif available is not None and not unbalanced:
        verdict = VERDICT_OK
    else:
        verdict = VERDICT_UNVERIFIABLE

    return UtilityCheck(
        verdict=verdict,
        missing_credits_kwh=None if missing is None else missing.quantize(Decimal("0.01")),
        credits_available_kwh=available,
        credits_used_kwh=used,
        credit_balance_kwh=balance,
        meter_export_kwh=bill.generation_cycle_kwh,
        previous_balance_kwh=previous_balance,
        export_share_percent=share,
        export_share_baseline_percent=baseline,
        reasons=tuple(reasons),
    )
