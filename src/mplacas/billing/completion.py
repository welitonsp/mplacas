"""Completar campos vazios de uma fatura já confirmada a partir do PDF.

Faturas que entraram antes de o leitor saber ler a tarifa (por exemplo, pelo
texto do Telegram) ficaram gravadas sem tarifa, Fio B ou registro de geração,
e por isso sem economia calculada. Reimportar o PDF do mesmo mês não pode
criar outra fatura (duplicaria o mês nas somas) nem reescrever o que já foi
conferido pelo cliente.

Regra: o PDF só completa campos que estão VAZIOS na fatura confirmada, e só
se tudo o que já existe bater exatamente (datas e dias do ciclo, consumo,
injeção, compensação, crédito e valor total). Qualquer divergência recusa a operação.
"""

from __future__ import annotations

from decimal import Decimal

from mplacas.billing.db_models import UtilityBillRecord
from mplacas.billing.models import UtilityBill
from mplacas.billing.parser import UNIDENTIFIED_TARIFF_CLASS

# Campos que precisam ser idênticos para ser a MESMA fatura.
_IDENTITY_FIELDS = (
    "cycle_start",
    "cycle_end",
    "billed_days",
    "imported_kwh",
    "injected_kwh",
    "compensated_kwh",
    "credit_balance_kwh",
    "total_amount_brl",
)
# Únicos campos que o PDF pode preencher, e só quando estão vazios.
COMPLETABLE_FIELDS = (
    "tariff_with_taxes_brl_kwh",
    "tariff_without_taxes_brl_kwh",
    "wire_b_tariff_brl_kwh",
    "generation_cycle_kwh",
    "generation_share_percent",
    "credits_expiring_30d_kwh",
    "flag_tariff_brl_kwh",
    "non_energy_credits_brl",
    "tariff_class",
)


class BillCompletionConflict(ValueError):
    """O PDF não é a mesma fatura que está confirmada para o mês."""


def _same(left: object, right: object) -> bool:
    if isinstance(left, Decimal) and isinstance(right, Decimal):
        return left == right  # 221 == 221.00
    return left == right


def complete_missing_fields(record: UtilityBillRecord, bill: UtilityBill) -> tuple[str, ...]:
    """Preenche os campos vazios de ``record`` com os de ``bill``.

    Devolve os nomes dos campos preenchidos (vazio se nada faltava). Levanta
    :class:`BillCompletionConflict` sem tocar em nada se algum campo de
    identidade divergir, ou se um campo já preenchido divergir do PDF.
    """
    for name in _IDENTITY_FIELDS:
        if not _same(getattr(record, name), getattr(bill, name)):
            raise BillCompletionConflict(name)
    filled: list[str] = []
    for name in COMPLETABLE_FIELDS:
        current = getattr(record, name)
        incoming = getattr(bill, name)
        if incoming is None:
            continue
        # Classe não reconhecida numa leitura anterior conta como vazia: o PDF
        # pode trazê-la (ADR-087). O contrário — PDF sem classe — não apaga.
        if name == "tariff_class" and current == UNIDENTIFIED_TARIFF_CLASS:
            current = None
        # PDF sem classe reconhecida nunca apaga uma classe lida; mas troca o
        # NULL antigo (que presumiria B1) por NAO_IDENTIFICADA — nunca presumir
        # quando o PDF já disse que não dá para saber.
        if (
            name == "tariff_class"
            and incoming == UNIDENTIFIED_TARIFF_CLASS
            and current is not None
        ):
            continue
        if current is None:
            filled.append(name)
        elif not _same(current, incoming):
            raise BillCompletionConflict(name)
    for name in filled:
        setattr(record, name, getattr(bill, name))
    return tuple(filled)
