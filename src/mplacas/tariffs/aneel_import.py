"""Importação das tarifas homologadas da base aberta da ANEEL (ADR-088).

Fonte: "Tarifas de aplicação das distribuidoras de energia elétrica"
(dadosabertos.aneel.gov.br), CSV com ";" e vírgula decimal, valores em R$/MWh.
Conferido contra as faturas reais da Equatorial Goiás: B1 residencial
convencional 2024/25 = 474,74 + 271,19 = R$ 0,745930/kWh, igual ao cadastro.

Regras:
- só "Tarifa de Aplicação" (a "Base Econômica" não é faturada);
- grupo B convencional, sem posto tarifário e sem usuário específico;
- linha comum ("Não se aplica") → tarifa cheia; linha "SCEE" → tarifa da
  energia compensada;
- classes: B1 residencial (não a baixa renda/tarifa social, que tem faixas de
  desconto por consumo), B2 rural genérica e B3 (uma tarifa só para comercial,
  industrial, poder público e serviço público). Subclasses com desconto
  próprio (irrigação, cooperativa) e tarifa branca ficam de fora — sem chave
  exata, o motor usa o preço da fatura (ADR-087);
- vigências seguidas com os mesmos valores são unidas (a ANEEL às vezes parte
  o ano em dois períodos iguais);
- falha fechada: valor fora do plausível, ou cadastro existente com valor
  diferente, interrompe a importação sem gravar nada.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.tariffs.db_models import DistributorTariffRecord

ANEEL_TARIFFS_CSV_URL = (
    "https://dadosabertos.aneel.gov.br/dataset/5a583f3e-1646-4f67-bf0f-69db4203e89e/"
    "resource/fcf2906c-7c32-4b9b-a637-054e7a5234f4/download/"
    "tarifas-homologadas-distribuidoras-energia-eletrica.csv"
)

_NOT_APPLICABLE = "Não se aplica"
_SIX_PLACES = Decimal("0.000001")
# Tarifa cheia plausível em R$/kWh sem tributos (hoje ~R$ 0,60–1,10).
_MIN_FULL = Decimal("0.2")
_MAX_FULL = Decimal("2.5")
# Vigências anteriores não servem a nenhuma fatura que o sistema leia.
DEFAULT_SINCE = date(2019, 1, 1)

# (subgrupo, classe ANEEL, subclasse ANEEL) → classes do sistema (ADR-087).
_CLASS_MAP: dict[tuple[str, str, str], tuple[str, ...]] = {
    ("B1", "Residencial", "Residencial"): ("B1_RESIDENCIAL_CONVENCIONAL",),
    ("B2", "Rural", _NOT_APPLICABLE): ("B2_RURAL_CONVENCIONAL",),
    ("B3", _NOT_APPLICABLE, _NOT_APPLICABLE): (
        "B3_COMERCIAL_CONVENCIONAL",
        "B3_INDUSTRIAL_CONVENCIONAL",
        "B3_PODER_PUBLICO_CONVENCIONAL",
        "B3_SERVICO_PUBLICO_CONVENCIONAL",
    ),
}


class AneelImportError(ValueError):
    """A importação foi recusada; nada foi gravado."""


@dataclass(frozen=True, slots=True)
class TariffPeriod:
    distributor: str
    tariff_class: str
    valid_from: date
    valid_to: date
    full_brl_kwh: Decimal
    scee_brl_kwh: Decimal | None
    source: str


@dataclass(frozen=True, slots=True)
class ImportReport:
    periods: int
    inserted: int
    extended: int
    unchanged: int


def distributor_code(sig_agente: str) -> str:
    """Código do sistema a partir da sigla da ANEEL: "EQUATORIAL GO" →
    "EQUATORIAL_GO". O leitor de fatura de cada distribuidora usa a mesma
    regra, para a fatura achar a tarifa."""
    ascii_only = unicodedata.normalize("NFKD", sig_agente).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "_", ascii_only.upper()).strip("_")


def _mwh_to_kwh(value: str) -> Decimal:
    text = value.strip().replace(".", "").replace(",", ".")
    if text.startswith("."):
        text = "0" + text
    try:
        return Decimal(text) / Decimal("1000")
    except InvalidOperation as exc:
        raise AneelImportError(f"valor ilegível na base da ANEEL: {value!r}") from exc


def _reh(text: str) -> str:
    match = re.search(r"N[ºo°]\s*([\d.]+)", text)
    return match.group(1) if match else text[:60]


def parse_rows(
    rows: Iterable[dict[str, str]], *, since: date = DEFAULT_SINCE
) -> list[TariffPeriod]:
    """Linhas do CSV → períodos de tarifa por distribuidora e classe."""
    # (distribuidora, classe, início, fim) → [tarifa cheia, tarifa SCEE, REH]
    found: dict[tuple[str, str, date, date], list[object]] = {}
    for row in rows:
        if row.get("DscBaseTarifaria") != "Tarifa de Aplicação":
            continue
        if row.get("DscModalidadeTarifaria") != "Convencional":
            continue
        if row.get("NomPostoTarifario") != _NOT_APPLICABLE:
            continue
        if row.get("SigAgenteAcessante") != _NOT_APPLICABLE:
            continue
        if row.get("DscUnidadeTerciaria") != "MWh":
            continue
        detail = row.get("DscDetalhe")
        if detail not in (_NOT_APPLICABLE, "SCEE"):
            continue
        classes = _CLASS_MAP.get(
            (row.get("DscSubGrupo", ""), row.get("DscClasse", ""), row.get("DscSubClasse", ""))
        )
        if classes is None:
            continue
        start = date.fromisoformat(row["DatInicioVigencia"])
        end = date.fromisoformat(row["DatFimVigencia"])
        if end < since:
            continue
        value = (_mwh_to_kwh(row["VlrTUSD"]) + _mwh_to_kwh(row["VlrTE"])).quantize(
            _SIX_PLACES, rounding=ROUND_HALF_UP
        )
        code = distributor_code(row["SigAgente"])
        for tariff_class in classes:
            slot = found.setdefault(
                (code, tariff_class, start, end), [None, None, _reh(row["DscREH"])]
            )
            index = 0 if detail == _NOT_APPLICABLE else 1
            if slot[index] is not None and slot[index] != value:
                raise AneelImportError(
                    f"valores diferentes para {code} {tariff_class} {start}: "
                    f"{slot[index]} e {value}"
                )
            slot[index] = value

    periods = []
    for (code, tariff_class, start, end), (full, scee, reh) in found.items():
        if full is None:
            continue  # só a linha SCEE: sem tarifa cheia não há o que usar
        assert isinstance(full, Decimal)
        if not (_MIN_FULL <= full <= _MAX_FULL):
            raise AneelImportError(f"tarifa implausível para {code} {tariff_class} {start}: {full}")
        periods.append(
            TariffPeriod(
                distributor=code,
                tariff_class=tariff_class,
                valid_from=start,
                valid_to=end,
                full_brl_kwh=full,
                scee_brl_kwh=scee if isinstance(scee, Decimal) else None,
                source=f"ANEEL dados abertos, REH {reh}",
            )
        )
    return _coalesce(periods)


def _coalesce(periods: list[TariffPeriod]) -> list[TariffPeriod]:
    """Une vigências seguidas e iguais; recusa vigências sobrepostas."""
    periods = sorted(periods, key=lambda p: (p.distributor, p.tariff_class, p.valid_from))
    merged: list[TariffPeriod] = []
    for period in periods:
        last = merged[-1] if merged else None
        if last and (last.distributor, last.tariff_class) == (
            period.distributor,
            period.tariff_class,
        ):
            if period.valid_from <= last.valid_to:
                raise AneelImportError(
                    f"vigências sobrepostas na ANEEL: {period.distributor} {period.tariff_class} "
                    f"{last.valid_from}..{last.valid_to} e {period.valid_from}"
                )
            if (
                period.valid_from == last.valid_to + timedelta(days=1)
                and period.full_brl_kwh == last.full_brl_kwh
                and period.scee_brl_kwh == last.scee_brl_kwh
            ):
                merged[-1] = replace(last, valid_to=period.valid_to)
                continue
        merged.append(period)
    return merged


def read_csv(lines: Iterable[str]) -> Iterator[dict[str, str]]:
    yield from csv.DictReader(lines, delimiter=";")


async def upsert_periods(
    session: AsyncSession, periods: list[TariffPeriod], *, dry_run: bool
) -> ImportReport:
    """Grava os períodos novos. Período já cadastrado com o MESMO valor pode
    ter a vigência ajustada (a ANEEL fecha a data quando sai o reajuste);
    com valor diferente, recusa tudo — nunca reescreve tarifa em silêncio."""
    existing = {
        (row.distributor, row.tariff_class, row.valid_from): row
        for row in (await session.scalars(select(DistributorTariffRecord))).all()
    }
    inserted = extended = unchanged = 0
    to_add: list[DistributorTariffRecord] = []
    for period in periods:
        row = existing.get((period.distributor, period.tariff_class, period.valid_from))
        if row is None:
            clash = next(
                (
                    other
                    for other in existing.values()
                    if (other.distributor, other.tariff_class)
                    == (period.distributor, period.tariff_class)
                    and other.valid_from <= period.valid_to
                    and period.valid_from <= other.valid_to
                ),
                None,
            )
            if clash is not None:
                # Vigência sobreposta deixaria dias com duas tarifas — o motor
                # não escolhe (service.py devolve None). Recusa tudo.
                raise AneelImportError(
                    f"vigência da ANEEL {period.valid_from}..{period.valid_to} sobrepõe o "
                    f"cadastro {clash.valid_from}..{clash.valid_to} em "
                    f"{period.distributor} {period.tariff_class}"
                )
            inserted += 1
            to_add.append(
                DistributorTariffRecord(
                    distributor=period.distributor,
                    tariff_class=period.tariff_class,
                    valid_from=period.valid_from,
                    valid_to=period.valid_to,
                    full_brl_kwh=period.full_brl_kwh,
                    scee_brl_kwh=period.scee_brl_kwh,
                    source=period.source[:200],
                )
            )
            continue
        if row.full_brl_kwh != period.full_brl_kwh or (
            row.scee_brl_kwh is not None
            and period.scee_brl_kwh is not None
            and row.scee_brl_kwh != period.scee_brl_kwh
        ):
            raise AneelImportError(
                f"cadastro diverge da ANEEL em {period.distributor} {period.tariff_class} "
                f"{period.valid_from}: {row.full_brl_kwh} × {period.full_brl_kwh}"
            )
        if row.valid_to != period.valid_to:
            extended += 1
            if not dry_run:
                row.valid_to = period.valid_to
        else:
            unchanged += 1
    if not dry_run:
        session.add_all(to_add)
        await session.flush()
    return ImportReport(
        periods=len(periods), inserted=inserted, extended=extended, unchanged=unchanged
    )
