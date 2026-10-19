from __future__ import annotations

from datetime import date
from decimal import Decimal

from mplacas.intelligence.investor_metrics import (
    InvestorPremises,
    add_months,
    annualize,
    income_tax_rate,
    months_between,
    project,
    realized_comparison,
    wire_b_share,
)

PREMISES = InvestorPremises(
    cdi_per_year=Decimal("0.1365"),
    ipca_per_year=Decimal("0.0458"),
    tariff_growth_per_year=Decimal("0.06"),
)


def _flat_cdi(start: str, months: int, rate: str = "1") -> dict[str, Decimal]:
    return {add_months(start, k): Decimal(rate) for k in range(1, months + 1)}


def test_month_helpers() -> None:
    assert add_months("2025-09", 4) == "2026-01"
    assert add_months("2026-01", -1) == "2025-12"
    assert months_between("2025-09", "2026-09") == 12


def test_income_tax_regressive_table() -> None:
    assert income_tax_rate(Decimal("180")) == Decimal("0.225")
    assert income_tax_rate(Decimal("181")) == Decimal("0.20")
    assert income_tax_rate(Decimal("720")) == Decimal("0.175")
    assert income_tax_rate(Decimal("721")) == Decimal("0.15")


def test_wire_b_schedule_follows_law_14300_and_assumes_full_from_2029() -> None:
    assert wire_b_share(2022) == Decimal("0")
    assert wire_b_share(2026) == Decimal("0.60")
    assert wire_b_share(2028) == Decimal("0.90")
    assert wire_b_share(2031) == Decimal("1.00")


def test_annualize_chains_monthly_rates_instead_of_summing() -> None:
    # 12 × 1% = 12% somando; encadeando = 12,68%.
    assert annualize([Decimal("1")] * 12).quantize(Decimal("0.0001")) == Decimal("0.1268")


def test_realized_cdi_path_is_net_of_regressive_income_tax() -> None:
    result = realized_comparison(
        investment_brl=Decimal("10000"),
        start_month="2025-09",
        savings_by_month={},
        cdi_by_month=_flat_cdi("2025-09", 12),
        as_of_month="2026-09",
    )
    assert result is not None
    # Bruto: 10.000 × 1,01^12 = 11.268,25; ganho 1.268,25; 12 meses ≈ 365 dias → 17,5%.
    assert result.cdi_path_net_brl == Decimal("11046.31")
    assert result.cdi_accumulated_percent == Decimal("12.68")


def test_realized_solar_path_grows_each_saving_from_its_own_month() -> None:
    result = realized_comparison(
        investment_brl=Decimal("10000"),
        start_month="2025-09",
        savings_by_month={"2026-08": Decimal("300"), "2026-09": Decimal("300")},
        cdi_by_month=_flat_cdi("2025-09", 12),
        as_of_month="2026-09",
    )
    assert result is not None
    # Agosto rende 1 mês (300 × 1,01 = 303; IR 22,5% sobre 3 → 302,33);
    # setembro entra no fim do mês, sem render: 300.
    assert result.solar_path_net_brl == Decimal("602.33")
    assert result.accumulated_savings_brl == Decimal("600.00")
    assert result.cycles_counted == 2


def test_realized_is_unavailable_when_a_cdi_month_is_missing() -> None:
    cdi = _flat_cdi("2025-09", 12)
    del cdi["2026-03"]
    assert (
        realized_comparison(
            investment_brl=Decimal("10000"),
            start_month="2025-09",
            savings_by_month={"2026-09": Decimal("300")},
            cdi_by_month=cdi,
            as_of_month="2026-09",
        )
        is None
    )


def test_projection_reproduces_the_documented_example() -> None:
    # Exemplo do documento de diagnóstico: R$ 20 mil, R$ 400/mês, tarifa +6%,
    # degradação 0,5%, O&M 0,5%, inversor no ano 12, sem Fio B (GD I).
    result = project(
        investment_brl=Decimal("20000"),
        start_month="2025-09",
        commissioned_on=date(2022, 6, 1),
        savings_by_month={"2025-10": Decimal("400")},
        compensated_kwh_per_month=Decimal("221"),
        wire_b_tariff_brl_kwh=Decimal("0.175126"),
        wire_b_reference_year=2026,
        premises=PREMISES,
    )
    assert result is not None
    assert result.wire_b_applied is False  # GD I: fora da transição do Fio B
    assert result.irr_per_year is not None
    assert Decimal("0.31") < result.irr_per_year < Decimal("0.34")
    assert result.payback_simple_months == 47
    assert result.payback_discounted_months is not None
    assert result.payback_discounted_months > result.payback_simple_months
    ten_years = next(p for p in result.patrimony if p.year == 10)
    # CDB comprado na ligação e resgatado em 10 anos: IR de 15% só sobre o
    # ganho, no resgate (não um desconto de 15% na taxa a cada ano).
    gross = Decimal("20000") * Decimal("1.1365") ** 10
    expected = gross - (gross - Decimal("20000")) * Decimal("0.15")
    assert abs(ten_years.cdi_path_brl - expected) < Decimal("0.05")
    assert ten_years.solar_path_brl > ten_years.cdi_path_brl


def test_wire_b_transition_lowers_the_return_for_gd_ii() -> None:
    common = dict(
        investment_brl=Decimal("11200"),
        start_month="2025-09",
        savings_by_month={"2026-09": Decimal("264")},
        compensated_kwh_per_month=Decimal("221"),
        wire_b_tariff_brl_kwh=Decimal("0.175126"),
        wire_b_reference_year=2026,
        premises=PREMISES,
    )
    gd_ii = project(commissioned_on=date(2025, 9, 1), **common)  # type: ignore[arg-type]
    gd_i = project(commissioned_on=date(2022, 9, 1), **common)  # type: ignore[arg-type]
    assert gd_ii is not None and gd_i is not None
    assert gd_ii.wire_b_applied is True
    assert gd_ii.irr_per_year is not None and gd_i.irr_per_year is not None
    assert gd_ii.irr_per_year < gd_i.irr_per_year
    assert gd_ii.lifetime_savings_brl < gd_i.lifetime_savings_brl


def test_projection_needs_at_least_one_real_saving() -> None:
    assert (
        project(
            investment_brl=Decimal("11200"),
            start_month="2025-09",
            commissioned_on=date(2025, 9, 1),
            savings_by_month={},
            compensated_kwh_per_month=None,
            wire_b_tariff_brl_kwh=None,
            wire_b_reference_year=None,
            premises=PREMISES,
        )
        is None
    )


def test_irr_is_none_when_the_plant_never_pays_back() -> None:
    result = project(
        investment_brl=Decimal("100000"),
        start_month="2025-09",
        commissioned_on=date(2025, 9, 1),
        savings_by_month={"2026-09": Decimal("5")},
        compensated_kwh_per_month=None,
        wire_b_tariff_brl_kwh=None,
        wire_b_reference_year=None,
        premises=PREMISES,
    )
    assert result is not None
    assert result.irr_per_year is None
    assert result.payback_simple_months is None
    assert result.npv_at_cdi_net_brl < 0


def test_long_horizon_cdi_benchmark_taxes_the_gain_at_redemption() -> None:
    # Regressão do achado P1 do reviewer: com CDI de 14% a.a. por 25 anos o CDB
    # rende 1 + 0,85 × (1,14^25 − 1) ≈ 22,7×, não 1,119^25 ≈ 16,6×.
    premises = InvestorPremises(
        cdi_per_year=Decimal("0.14"),
        ipca_per_year=Decimal("0.045"),
        tariff_growth_per_year=Decimal("0.045"),
    )
    result = project(
        investment_brl=Decimal("10000"),
        start_month="2025-09",
        commissioned_on=date(2025, 9, 1),
        savings_by_month={"2025-10": Decimal("200")},
        compensated_kwh_per_month=None,
        wire_b_tariff_brl_kwh=None,
        wire_b_reference_year=None,
        premises=premises,
    )
    assert result is not None
    final = result.patrimony[-1]
    expected_factor = 1 + Decimal("0.85") * (Decimal("1.14") ** 25 - 1)
    assert abs(final.cdi_path_brl / Decimal("10000") - expected_factor) < Decimal("0.01")
    # A taxa líquida efetiva é a que reproduz esse resgate em 25 anos.
    assert abs((1 + result.cdi_net_per_year) ** 25 - expected_factor) < Decimal("0.05")


def test_discounted_payback_is_where_the_patrimony_lines_cross() -> None:
    result = project(
        investment_brl=Decimal("11200"),
        start_month="2025-09",
        commissioned_on=date(2022, 9, 1),
        savings_by_month={"2026-09": Decimal("264")},
        compensated_kwh_per_month=None,
        wire_b_tariff_brl_kwh=None,
        wire_b_reference_year=None,
        premises=PREMISES,
    )
    assert result is not None and result.payback_discounted_months is not None
    year = result.payback_discounted_months / 12
    before = next(p for p in result.patrimony if p.year == int(year))
    after = next(p for p in result.patrimony if p.year == int(year) + 1)
    assert before.solar_path_brl < before.cdi_path_brl
    assert after.solar_path_brl >= after.cdi_path_brl


def test_realized_ignores_the_commissioning_month_bill() -> None:
    result = realized_comparison(
        investment_brl=Decimal("10000"),
        start_month="2025-09",
        savings_by_month={"2025-09": Decimal("100"), "2025-10": Decimal("300")},
        cdi_by_month=_flat_cdi("2025-09", 12),
        as_of_month="2026-09",
    )
    assert result is not None
    assert result.cycles_counted == 1
    assert result.accumulated_savings_brl == Decimal("300.00")
