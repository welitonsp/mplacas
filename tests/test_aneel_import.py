"""ADR-088: importação das tarifas homologadas da base aberta da ANEEL.

As linhas da Equatorial GO abaixo são as reais da base pública (sonda de
2026-10-24) e reproduzem as tarifas já conferidas nas faturas.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.tariffs.aneel_import import (
    AneelImportError,
    distributor_code,
    parse_rows,
    read_csv,
    upsert_periods,
)
from mplacas.tariffs.db_models import DistributorTariffRecord

HEADER = (
    "DatGeracaoConjuntoDados;DscREH;SigAgente;NumCNPJDistribuidora;DatInicioVigencia;"
    "DatFimVigencia;DscBaseTarifaria;DscSubGrupo;DscModalidadeTarifaria;DscClasse;"
    "DscSubClasse;DscDetalhe;NomPostoTarifario;DscUnidadeTerciaria;SigAgenteAcessante;"
    "VlrTUSD;VlrTE"
)
NA = "Não se aplica"


def _line(
    start: str,
    end: str,
    tusd: str,
    te: str,
    *,
    reh: str = "3.544",
    agent: str = "EQUATORIAL GO",
    base: str = "Tarifa de Aplicação",
    subgroup: str = "B1",
    modality: str = "Convencional",
    klass: str = "Residencial",
    subclass: str = "Residencial",
    detail: str = NA,
    post: str = NA,
) -> str:
    return ";".join(
        [
            "2026-10-24",
            f"RESOLUÇÃO HOMOLOGATÓRIA Nº {reh}, DE 1 DE OUTUBRO",
            agent,
            "01543032000104",
            start,
            end,
            base,
            subgroup,
            modality,
            klass,
            subclass,
            detail,
            post,
            "MWh",
            NA,
            tusd,
            te,
        ]
    )


REAL_EQUATORIAL = [
    _line("2023-10-22", "2024-10-21", "428,29", "282,34", reh="3.279"),
    _line("2023-10-22", "2024-10-21", "428,29", "43,34", reh="3.279", detail="SCEE"),
    _line("2024-10-22", "2025-10-21", "474,74", "271,19", reh="3.407"),
    _line("2024-10-22", "2025-10-21", "474,74", "23,38", reh="3.407", detail="SCEE"),
    _line("2025-10-22", "2025-12-31", "567,67", "324,14"),
    _line("2025-10-22", "2025-12-31", "567,67", "45,36", detail="SCEE"),
    _line("2026-01-01", "2026-10-21", "567,67", "324,14"),
    _line("2026-01-01", "2026-10-21", "567,67", "45,36", detail="SCEE"),
    # Ignoradas: base econômica, tarifa branca, baixa renda, pré-pagamento.
    _line("2025-10-22", "2026-10-21", "1,00", "1,00", base="Base Econômica"),
    _line("2025-10-22", "2026-10-21", "304,73", "269,63", modality="Branca", post="Fora ponta"),
    _line("2025-10-22", "2026-10-21", "336,26", "276,07", subclass="Baixa Renda"),
    _line("2025-10-22", "2026-10-21", "567,67", "324,14", modality="Convencional pré-pagamento"),
]


def _parse(lines: list[str]):
    return parse_rows(read_csv([HEADER, *lines]))


def test_real_equatorial_rows_reproduce_the_tariffs_checked_on_the_bills() -> None:
    periods = _parse(REAL_EQUATORIAL)
    got = {(p.valid_from, p.valid_to): (p.full_brl_kwh, p.scee_brl_kwh) for p in periods}
    assert got == {
        (date(2023, 10, 22), date(2024, 10, 21)): (Decimal("0.710630"), Decimal("0.471630")),
        (date(2024, 10, 22), date(2025, 10, 21)): (Decimal("0.745930"), Decimal("0.498120")),
        # Dois períodos iguais da ANEEL viram um só, como no cadastro.
        (date(2025, 10, 22), date(2026, 10, 21)): (Decimal("0.891810"), Decimal("0.613030")),
    }
    assert {p.distributor for p in periods} == {"EQUATORIAL_GO"}
    assert {p.tariff_class for p in periods} == {"B1_RESIDENCIAL_CONVENCIONAL"}
    assert periods[0].source == "ANEEL dados abertos, REH 3.279"


def test_b3_feeds_every_b3_class_and_rural_generic_only() -> None:
    periods = _parse(
        [
            _line(
                "2025-10-22", "2026-10-21", "500,00", "300,00", subgroup="B3", klass=NA, subclass=NA
            ),
            _line(
                "2025-10-22",
                "2026-10-21",
                "400,00",
                "300,00",
                subgroup="B2",
                klass="Rural",
                subclass=NA,
            ),
            _line(
                "2025-10-22",
                "2026-10-21",
                "100,00",
                "300,00",
                subgroup="B2",
                klass="Rural",
                subclass="Serviço público de irrigação rural",
            ),
        ]
    )
    classes = {p.tariff_class: p.full_brl_kwh for p in periods}
    assert classes == {
        "B3_COMERCIAL_CONVENCIONAL": Decimal("0.800000"),
        "B3_INDUSTRIAL_CONVENCIONAL": Decimal("0.800000"),
        "B3_PODER_PUBLICO_CONVENCIONAL": Decimal("0.800000"),
        "B3_SERVICO_PUBLICO_CONVENCIONAL": Decimal("0.800000"),
        "B2_RURAL_CONVENCIONAL": Decimal("0.700000"),
    }


def test_implausible_or_conflicting_values_fail_closed() -> None:
    with pytest.raises(AneelImportError):
        _parse([_line("2025-10-22", "2026-10-21", "5000,00", "3000,00")])
    with pytest.raises(AneelImportError):
        _parse(
            [
                _line("2025-10-22", "2026-10-21", "567,67", "324,14"),
                _line("2025-10-22", "2026-10-21", "500,00", "324,14"),
            ]
        )
    with pytest.raises(AneelImportError):
        _parse(
            [
                _line("2025-10-22", "2026-10-21", "567,67", "324,14"),
                _line("2026-01-01", "2026-12-31", "600,00", "324,14"),
            ]
        )


def test_distributor_code_matches_the_bill_reader_convention() -> None:
    assert distributor_code("EQUATORIAL GO") == "EQUATORIAL_GO"
    assert distributor_code("CPFL-PAULISTA") == "CPFL_PAULISTA"
    assert distributor_code("ENEL SP") == "ENEL_SP"
    assert distributor_code("CEMIG-D") == "CEMIG_D"


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        # Cadastro atual (migration 0045), como está em produção.
        for start, end, full, scee in (
            (date(2023, 10, 22), date(2024, 10, 21), "0.710630", None),
            (date(2024, 10, 22), date(2025, 10, 21), "0.745930", "0.498120"),
            (date(2025, 10, 22), date(2026, 10, 21), "0.891810", "0.613030"),
        ):
            db.add(
                DistributorTariffRecord(
                    id=uuid.uuid4(),
                    distributor="EQUATORIAL_GO",
                    tariff_class="B1_RESIDENCIAL_CONVENCIONAL",
                    valid_from=start,
                    valid_to=end,
                    full_brl_kwh=Decimal(full),
                    scee_brl_kwh=None if scee is None else Decimal(scee),
                    source="seed",
                )
            )
        await db.commit()
        yield db
    await engine.dispose()


async def test_import_over_current_registry_changes_nothing_and_adds_new_periods(
    session: AsyncSession,
) -> None:
    lines = [
        *REAL_EQUATORIAL,
        _line("2026-10-22", "2027-10-21", "610,00", "340,00", reh="3.613"),
    ]
    periods = _parse(lines)

    dry = await upsert_periods(session, periods, dry_run=True)
    assert (dry.inserted, dry.unchanged) == (1, 3)
    assert len((await session.scalars(select(DistributorTariffRecord))).all()) == 3

    report = await upsert_periods(session, periods, dry_run=False)
    await session.commit()
    assert (report.inserted, report.extended, report.unchanged) == (1, 0, 3)
    rows = (await session.scalars(select(DistributorTariffRecord))).all()
    assert len(rows) == 4
    new = next(r for r in rows if r.valid_from == date(2026, 10, 22))
    assert new.full_brl_kwh == Decimal("0.950000")
    assert new.source == "ANEEL dados abertos, REH 3.613"


async def test_registry_diverging_from_aneel_refuses_everything(session: AsyncSession) -> None:
    periods = _parse(
        [
            _line("2024-10-22", "2025-10-21", "474,74", "271,20", reh="3.407"),
            _line("2026-10-22", "2027-10-21", "610,00", "340,00", reh="3.613"),
        ]
    )
    with pytest.raises(AneelImportError):
        await upsert_periods(session, periods, dry_run=False)


async def test_period_overlapping_the_registry_is_refused(session: AsyncSession) -> None:
    periods = _parse([_line("2026-06-01", "2027-05-31", "610,00", "340,00")])
    with pytest.raises(AneelImportError):
        await upsert_periods(session, periods, dry_run=False)
