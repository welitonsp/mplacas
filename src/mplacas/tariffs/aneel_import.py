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
  industrial e poder público). Serviço público, subclasses com desconto
  próprio (irrigação, cooperativa) e tarifa branca ficam de fora — sem chave
  exata, o motor usa o preço da fatura (ADR-087);
- vigências seguidas com os mesmos valores são unidas (a ANEEL às vezes parte
  o ano em dois períodos iguais);
- inconsistência DENTRO da base (valores diferentes na mesma vigência,
  vigências sobrepostas, valor implausível) tira só aquela distribuidora e
  classe, com aviso — a base real tem casos assim (ex.: CEA, 2021);
- cadastro existente com valor diferente da ANEEL interrompe tudo sem gravar
  nada; coluna ausente ou base vazia também.
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
    # B3 "demais classes": uma tarifa só para comercial, industrial e poder
    # público. Serviço público (água, esgoto, saneamento) fica de fora: pode
    # ter desconto próprio, e sem chave exata o motor usa o preço da fatura.
    ("B3", _NOT_APPLICABLE, _NOT_APPLICABLE): (
        "B3_COMERCIAL_CONVENCIONAL",
        "B3_INDUSTRIAL_CONVENCIONAL",
        "B3_PODER_PUBLICO_CONVENCIONAL",
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
    skipped: tuple[str, ...] = ()


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


REQUIRED_COLUMNS = frozenset(
    {
        "DscREH",
        "SigAgente",
        "DatInicioVigencia",
        "DatFimVigencia",
        "DscBaseTarifaria",
        "DscSubGrupo",
        "DscModalidadeTarifaria",
        "DscClasse",
        "DscSubClasse",
        "DscDetalhe",
        "NomPostoTarifario",
        "DscUnidadeTerciaria",
        "SigAgenteAcessante",
        "VlrTUSD",
        "VlrTE",
    }
)


@dataclass(frozen=True, slots=True)
class ParseResult:
    periods: list[TariffPeriod]
    # Distribuidora/classe deixadas de fora por inconsistência DENTRO da base
    # da ANEEL (valores diferentes na mesma vigência, vigências sobrepostas,
    # valor implausível). Isoladas para não travar as demais distribuidoras.
    skipped: list[str]


def parse_aneel(rows: Iterable[dict[str, str]], *, since: date = DEFAULT_SINCE) -> ParseResult:
    """Linhas do CSV → períodos de tarifa por distribuidora e classe.

    Inconsistência numa distribuidora/classe tira só aquela chave (com
    aviso); formato inesperado da base (coluna ausente) recusa tudo.
    """
    # (distribuidora, classe, início, fim) → [tarifa cheia, tarifa SCEE, REH]
    found: dict[tuple[str, str, date, date], list[object]] = {}
    bad: dict[tuple[str, str], str] = {}
    checked_header = False
    for row in rows:
        if not checked_header:
            missing = REQUIRED_COLUMNS - set(row)
            if missing:
                raise AneelImportError(f"base da ANEEL sem as colunas: {sorted(missing)}")
            checked_header = True
        if row["DscBaseTarifaria"] != "Tarifa de Aplicação":
            continue
        if row["DscModalidadeTarifaria"] != "Convencional":
            continue
        if row["NomPostoTarifario"] != _NOT_APPLICABLE:
            continue
        if row["SigAgenteAcessante"] != _NOT_APPLICABLE:
            continue
        if row["DscUnidadeTerciaria"] != "MWh":
            continue
        detail = row["DscDetalhe"]
        if detail not in (_NOT_APPLICABLE, "SCEE"):
            continue
        classes = _CLASS_MAP.get((row["DscSubGrupo"], row["DscClasse"], row["DscSubClasse"]))
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
        if not code or len(code) > 40:
            continue
        for tariff_class in classes:
            slot = found.setdefault(
                (code, tariff_class, start, end), [None, None, _reh(row["DscREH"])]
            )
            index = 0 if detail == _NOT_APPLICABLE else 1
            if slot[index] is not None and slot[index] != value:
                bad.setdefault(
                    (code, tariff_class),
                    f"{code} {tariff_class}: valores diferentes na vigência {start} "
                    f"({slot[index]} e {value})",
                )
            slot[index] = value
    if not checked_header:
        raise AneelImportError("base da ANEEL vazia")

    periods = []
    for (code, tariff_class, start, end), (full, scee, reh) in found.items():
        if (code, tariff_class) in bad or not isinstance(full, Decimal):
            continue  # só a linha SCEE: sem tarifa cheia não há o que usar
        if not (_MIN_FULL <= full <= _MAX_FULL):
            bad.setdefault((code, tariff_class), f"{code} {tariff_class}: tarifa {full} em {start}")
            continue
        # SCEE plausível: positiva e não maior que a cheia; senão, sem SCEE.
        scee_value = scee if isinstance(scee, Decimal) and Decimal("0") < scee <= full else None
        periods.append(
            TariffPeriod(
                distributor=code,
                tariff_class=tariff_class,
                valid_from=start,
                valid_to=end,
                full_brl_kwh=full,
                scee_brl_kwh=scee_value,
                source=f"ANEEL dados abertos, REH {reh}",
            )
        )
    merged, overlapping = _coalesce(
        [p for p in periods if (p.distributor, p.tariff_class) not in bad]
    )
    for key, reason in overlapping.items():
        bad.setdefault(key, reason)
    final = [p for p in merged if (p.distributor, p.tariff_class) not in bad]
    return ParseResult(periods=final, skipped=sorted(bad.values()))


def parse_rows(
    rows: Iterable[dict[str, str]], *, since: date = DEFAULT_SINCE
) -> list[TariffPeriod]:
    return parse_aneel(rows, since=since).periods


def _coalesce(
    periods: list[TariffPeriod],
) -> tuple[list[TariffPeriod], dict[tuple[str, str], str]]:
    """Une vigências seguidas e iguais; aponta chaves com vigências sobrepostas."""
    periods = sorted(periods, key=lambda p: (p.distributor, p.tariff_class, p.valid_from))
    merged: list[TariffPeriod] = []
    overlapping: dict[tuple[str, str], str] = {}
    for period in periods:
        key = (period.distributor, period.tariff_class)
        last = merged[-1] if merged else None
        if last and (last.distributor, last.tariff_class) == key:
            if period.valid_from <= last.valid_to:
                overlapping.setdefault(
                    key,
                    f"{key[0]} {key[1]}: vigências sobrepostas {last.valid_from}..{last.valid_to} "
                    f"e {period.valid_from}",
                )
                continue
            if (
                period.valid_from == last.valid_to + timedelta(days=1)
                and period.full_brl_kwh == last.full_brl_kwh
                and period.scee_brl_kwh == last.scee_brl_kwh
            ):
                merged[-1] = replace(last, valid_to=period.valid_to)
                continue
        merged.append(period)
    return merged, overlapping


def read_csv(lines: Iterable[str]) -> Iterator[dict[str, str]]:
    yield from csv.DictReader(lines, delimiter=";")


def _overlaps(
    rows: list[DistributorTariffRecord], start: date, end: date, *, ignore: object = None
) -> DistributorTariffRecord | None:
    return next(
        (r for r in rows if r is not ignore and r.valid_from <= end and start <= r.valid_to),
        None,
    )


async def upsert_periods(
    session: AsyncSession, periods: list[TariffPeriod], *, dry_run: bool
) -> ImportReport:
    """Grava os períodos novos, sem nunca reescrever tarifa em silêncio.

    - Período já cadastrado com valor DIFERENTE: recusa tudo (precisa de
      revisão humana).
    - Mesmo valor: a vigência só pode ser ESTENDIDA (a ANEEL fecha a data
      quando sai o reajuste), e só se não encostar em outra vigência.
      Encurtar, ou estender por cima de outra linha, deixa aquela chave como
      está, com aviso.
    - Período novo que sobrepõe o cadastro: chave fica como está, com aviso —
      nunca dois valores no mesmo dia (service.py não escolheria).
    """
    by_key: dict[tuple[str, str], list[DistributorTariffRecord]] = {}
    for stored in (await session.scalars(select(DistributorTariffRecord))).all():
        by_key.setdefault((stored.distributor, stored.tariff_class), []).append(stored)
    inserted = extended = unchanged = 0
    skipped: list[str] = []
    to_add: list[DistributorTariffRecord] = []
    for period in periods:
        key = (period.distributor, period.tariff_class)
        rows = by_key.setdefault(key, [])
        row = next((r for r in rows if r.valid_from == period.valid_from), None)
        if row is None:
            clash = _overlaps(rows, period.valid_from, period.valid_to)
            if clash is not None:
                skipped.append(
                    f"{key[0]} {key[1]}: vigência {period.valid_from}..{period.valid_to} sobrepõe "
                    f"o cadastro {clash.valid_from}..{clash.valid_to}"
                )
                continue
            record = DistributorTariffRecord(
                distributor=period.distributor,
                tariff_class=period.tariff_class,
                valid_from=period.valid_from,
                valid_to=period.valid_to,
                full_brl_kwh=period.full_brl_kwh,
                scee_brl_kwh=period.scee_brl_kwh,
                source=period.source[:200],
            )
            rows.append(record)
            to_add.append(record)
            inserted += 1
            continue
        # SCEE só diverge quando os dois lados a têm: a ANEEL pode publicar a
        # cheia antes da SCEE (ou a SCEE pode ter sido descartada por
        # implausível) — isso não é motivo para travar todas as distribuidoras.
        if row.full_brl_kwh != period.full_brl_kwh or (
            row.scee_brl_kwh is not None
            and period.scee_brl_kwh is not None
            and row.scee_brl_kwh != period.scee_brl_kwh
        ):
            raise AneelImportError(
                f"cadastro diverge da ANEEL em {key[0]} {key[1]} {period.valid_from}: "
                f"cheia {row.full_brl_kwh} × {period.full_brl_kwh}, "
                f"SCEE {row.scee_brl_kwh} × {period.scee_brl_kwh}"
            )
        if period.valid_to == row.valid_to:
            unchanged += 1
        elif period.valid_to < row.valid_to:
            skipped.append(
                f"{key[0]} {key[1]}: ANEEL encurta a vigência {row.valid_from}..{row.valid_to} "
                f"para {period.valid_to}; cadastro mantido"
            )
        else:
            clash = _overlaps(rows, row.valid_to + timedelta(days=1), period.valid_to, ignore=row)
            if clash is not None:
                skipped.append(
                    f"{key[0]} {key[1]}: estender {row.valid_from}..{row.valid_to} até "
                    f"{period.valid_to} encostaria em {clash.valid_from}..{clash.valid_to}"
                )
                continue
            extended += 1
            if not dry_run:
                row.valid_to = period.valid_to
    if not dry_run:
        session.add_all(to_add)
        await session.flush()
    return ImportReport(
        periods=len(periods),
        inserted=inserted,
        extended=extended,
        unchanged=unchanged,
        skipped=tuple(skipped),
    )
