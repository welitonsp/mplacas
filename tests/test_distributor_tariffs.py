"""Tarifa cheia do ciclo e conta "sem a usina" (ADR-080).

Valores conferidos nas faturas reais da Equatorial GO e na REH 3.544/2025.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.billing.models import UtilityBill
from mplacas.db.base import Base
from mplacas.intelligence.energy_engine import (
    SAVINGS_TARIFF_BILL,
    SAVINGS_TARIFF_DISTRIBUTOR_FULL,
    analyze_energy_cycle,
)
from mplacas.tariffs.db_models import DistributorTariffRecord
from mplacas.tariffs.service import RESIDENTIAL_B1_CONVENTIONAL, full_tariff_without_taxes

ROOT = Path(__file__).resolve().parents[1]


def _seed_rows() -> list[DistributorTariffRecord]:
    """As mesmas linhas que a migration 0045 grava."""
    spec = importlib.util.spec_from_file_location(
        "seed_0045",
        ROOT / "migrations" / "versions" / "20261022_0045_add_distributor_tariffs.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [
        DistributorTariffRecord(
            distributor="EQUATORIAL_GO",
            tariff_class=RESIDENTIAL_B1_CONVENTIONAL,
            valid_from=start,
            valid_to=end,
            full_brl_kwh=full,
            scee_brl_kwh=scee,
            source=source,
        )
        for start, end, full, scee, source in module._SEED
    ]


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add_all(_seed_rows())
        await db.commit()
        yield db
    await engine.dispose()


async def _full(session: AsyncSession, start: date, end: date) -> Decimal | None:
    return await full_tariff_without_taxes(
        session, distributor="EQUATORIAL_GO", cycle_start=start, cycle_end=end
    )


async def test_cycle_inside_one_period_uses_its_tariff(session: AsyncSession) -> None:
    # Ciclo set/2026 (17/08–14/09/2026): REH 3.544/2025.
    assert await _full(session, date(2026, 8, 17), date(2026, 9, 14)) == Decimal("0.891810")


async def test_cycle_across_readjustment_reproduces_the_printed_price(
    session: AsyncSession,
) -> None:
    # Fatura nov/2024 (ciclo 16/10–15/11/2024): a "ENERGIA ATIVA FORNECIDA"
    # saiu a 0,740236 sem tributos = 5 dias a 0,710630 + 26 dias a 0,745930.
    assert await _full(session, date(2024, 10, 16), date(2024, 11, 15)) == Decimal("0.740236")


async def test_cycle_without_registered_period_returns_none(session: AsyncSession) -> None:
    # Reajuste de 22/10/2026 ainda não cadastrado: nenhum palpite.
    assert await _full(session, date(2026, 10, 15), date(2026, 11, 16)) is None
    assert (
        await full_tariff_without_taxes(
            session, distributor="OUTRA", cycle_start=date(2026, 8, 17), cycle_end=date(2026, 9, 14)
        )
        is None
    )


def _september_2026(**overrides: object) -> UtilityBill:
    values: dict[str, object] = {
        "distributor": "EQUATORIAL_GO",
        "reference_month": "2026-09",
        "cycle_start": date(2026, 8, 17),
        "cycle_end": date(2026, 9, 14),
        "billed_days": 29,
        "imported_kwh": Decimal("221.00"),
        "injected_kwh": Decimal("221.00"),
        "compensated_kwh": Decimal("221.00"),
        "credit_balance_kwh": Decimal("17.98"),
        "total_amount_brl": Decimal("70.22"),
        "public_lighting_brl": Decimal("30.21"),
        "generation_cycle_kwh": Decimal("235.00"),
        "tariff_with_taxes_brl_kwh": Decimal("0.787589"),
        "tariff_without_taxes_brl_kwh": Decimal("0.613030"),
        "wire_b_tariff_brl_kwh": Decimal("0.175126"),
    }
    values.update(overrides)
    return UtilityBill(**values)  # type: ignore[arg-type]


def test_savings_use_full_tariff_with_the_bills_own_taxes() -> None:
    # Set/2026 real: 583,21 kWh produzidos, 235 injetados → 348,21 do telhado
    # + 221 da rede = 569,21 kWh. Tarifa cheia 0,891810 × (0,787589/0,613030).
    result = analyze_energy_cycle(
        bill=_september_2026(),
        cycle_production_kwh=Decimal("583.21"),
        full_tariff_without_taxes=Decimal("0.891810"),
    )

    assert result.savings_tariff_source == SAVINGS_TARIFF_DISTRIBUTOR_FULL
    assert result.savings_tariff_brl_kwh == Decimal("1.145751")
    assert result.bill_without_solar_brl == Decimal("682.38")
    assert result.estimated_savings_brl == Decimal("612.16")


def test_without_full_tariff_falls_back_to_bill_price_and_says_so() -> None:
    result = analyze_energy_cycle(bill=_september_2026(), cycle_production_kwh=Decimal("583.21"))

    assert result.savings_tariff_source == SAVINGS_TARIFF_BILL
    assert result.savings_tariff_brl_kwh == Decimal("0.787589")
    assert result.estimated_savings_brl == Decimal("408.29")  # o número antigo, subestimado


def test_full_tariff_reproduces_uncompensated_price_printed_on_the_bill() -> None:
    # Set/2025: "CONSUMO NÃO COMPENSADO" a 0,964151 c/ tributos; tarifa cheia
    # 0,745930 × fator da linha SCEE (0,643844 / 0,498120).
    bill = _september_2026(
        reference_month="2025-09",
        cycle_start=date(2025, 8, 15),
        cycle_end=date(2025, 9, 14),
        billed_days=31,
        tariff_with_taxes_brl_kwh=Decimal("0.643844"),
        tariff_without_taxes_brl_kwh=Decimal("0.498120"),
    )
    result = analyze_energy_cycle(
        bill=bill,
        cycle_production_kwh=Decimal("500"),
        full_tariff_without_taxes=Decimal("0.745930"),
    )

    assert result.savings_tariff_brl_kwh is not None
    assert abs(result.savings_tariff_brl_kwh - Decimal("0.964151")) < Decimal("0.00002")


def test_full_tariff_never_goes_below_the_bills_own_price() -> None:
    # Fatura pré-transição: o preço da linha já é a tarifa cheia.
    result = analyze_energy_cycle(
        bill=_september_2026(),
        cycle_production_kwh=Decimal("583.21"),
        full_tariff_without_taxes=Decimal("0.500000"),
    )

    assert result.savings_tariff_brl_kwh == Decimal("0.787589")
