"""Vale a pena ampliar a usina? — motor puro, serviço e rota (ADR-089)."""

from __future__ import annotations

import asyncio
import dataclasses
import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
import mplacas.intelligence.expansion_service as expansion_service
import mplacas.intelligence.router as intelligence_router
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import Device, Plant
from mplacas.intelligence.expansion import (
    INVERTER_CHECK_DATASHEET,
    INVERTER_MICRO,
    INVERTER_NEW_NEEDED,
    INVERTER_OK,
    INVERTER_UNKNOWN,
    STATUS_BALANCED,
    STATUS_EXPAND,
    STATUS_FIX_FIRST,
    STATUS_NOT_WORTH,
    STATUS_UNAVAILABLE,
    ExpansionCycle,
    MoneyInputs,
    assess_expansion,
    inverter_check,
    year_values,
)
from mplacas.intelligence.investor_metrics import add_months
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord

D = Decimal


def _cycle(
    month: str,
    *,
    imported: str | None = "260",
    export: str | None = "230",
    production: str | None = "400",
    estimated: bool = False,
    days: int | None = 30,
    verdict: str = "OK",
    well_below: bool = False,
    share: str | None = "100",
    balance: str | None = "0",
) -> ExpansionCycle:
    return ExpansionCycle(
        reference_month=month,
        imported_kwh=None if imported is None else D(imported),
        meter_export_kwh=None if export is None else D(export),
        production_kwh=None if production is None else D(production),
        production_estimated=estimated,
        cycle_days=days,
        utility_verdict=verdict,
        production_well_below_expected=well_below,
        generation_share_percent=None if share is None else D(share),
        credit_balance_kwh=None if balance is None else D(balance),
    )


def _year(start: str = "2025-11", **kwargs: object) -> list[ExpansionCycle]:
    return [_cycle(add_months(start, k), **kwargs) for k in range(12)]  # type: ignore[arg-type]


MONEY = MoneyInputs(
    reference_month="2026-10",
    full_tariff_brl_kwh=D("0.891810"),
    wire_b_tariff_brl_kwh=D("0.175126"),
    model_matches_bill=True,
    regime_confirmed=True,
)


def _assess(cycles, **overrides):  # type: ignore[no-untyped-def]
    params = dict(
        cycles=cycles,
        previous_balance_kwh=D("307"),
        installed_kwp=D("3.3"),
        device_count=1,
        inverter_ac_kw=D("3.0"),
        money_inputs=MONEY,
        request_year=2026,
    )
    params.update(overrides)
    return assess_expansion(**params)  # type: ignore[arg-type]


def test_structural_deficit_uses_grid_minus_meter_not_credits_used() -> None:
    # 12 × (260 − 230) = 360 kWh/ano faltando; saldo antigo acabou (307 → 0).
    result = _assess(_year())
    assert result.status == STATUS_EXPAND
    assert result.deficit_kwh_year == D("360")
    assert result.deficit_kwh_month == D("30.0")
    assert result.tolerance_kwh_year == D("156.0")  # 5% de 3120
    assert result.balance_before_kwh == D("307")
    assert result.balance_after_kwh == D("0")
    # Rendimento: 400 kWh/30 dias × 365 ÷ 3,3 kWp ≈ 1475 kWh/kWp/ano.
    assert result.yield_kwh_per_kwp_year == D("1475")
    # 360 ÷ 1474,7 = 0,244 → arredonda PARA CIMA: 0,3 kWp.
    assert result.extra_kwp == D("0.3")
    assert result.inverter_status == INVERTER_OK
    assert result.dc_ac_ratio_after == D("1.20")
    assert result.money is not None and result.money.unavailable_reason is None


def test_money_follows_art_27_wire_b_and_marks_2029_as_scenario() -> None:
    money = _assess(_year()).money
    assert money is not None
    years = {v.year: v for v in money.values_by_year}
    assert sorted(years) == [2026, 2027, 2028, 2029]
    # Fio B pleno = 0,175126 ÷ 0,60 = 0,291877.
    assert years[2026].value_brl_kwh == D("0.716684")  # 0,891810 − 0,175126
    assert years[2027].value_brl_kwh == D("0.672902")  # − 0,291877 × 0,75
    assert years[2028].value_brl_kwh == D("0.629121")
    assert years[2029].value_brl_kwh == D("0.599933")
    assert years[2029].scenario and not years[2028].scenario
    # 30 kWh/mês × valor do ano.
    assert money.monthly_saving_first_year_brl == D("21.50")
    assert money.monthly_saving_scenario_brl == D("18.00")


def test_share_below_100_is_unavailable_even_with_loss_verdict() -> None:
    # Com rateio < 100%, a conferência marca LOSS em todo ciclo (crédito foi
    # para outra UC): não é defeito, é dado insuficiente.
    cycles = [_cycle(c.reference_month, share="60", verdict="LOSS") for c in _year()]
    result = _assess(cycles)
    assert result.status == STATUS_UNAVAILABLE
    assert result.reasons == ("SHARE_NOT_CONFIRMED",)


def test_direction_labels_surplus_and_zero() -> None:
    assert _assess(_year(imported="255", export="260")).direction == "SOBRA"
    assert _assess(_year(imported="260", export="260")).direction == "ZERO"


def test_wire_b_from_a_2025_bill_uses_45_percent_share() -> None:
    money = _assess(
        _year(), money_inputs=dataclasses.replace(MONEY, reference_month="2025-12")
    ).money
    assert money is not None
    first = money.values_by_year[0]
    # Fio B pleno = 0,175126 ÷ 0,45 = 0,389169; 2026 paga 60%.
    assert first.year == 2026
    assert first.value_brl_kwh == D("0.658309")


def test_bill_after_transition_and_late_request_year() -> None:
    money = _assess(
        _year(), money_inputs=dataclasses.replace(MONEY, reference_month="2029-02")
    ).money
    assert money is not None and money.unavailable_reason == "TRANSITION_ENDED"
    late = _assess(_year(), request_year=2031).money
    assert late is not None and [v.year for v in late.values_by_year] == [2029]


def test_year_values_start_at_request_year() -> None:
    values = year_values(
        full_tariff_brl_kwh=D("1"),
        wire_b_tariff_brl_kwh=D("0.3"),
        bill_year=2026,
        request_year=2028,
    )
    assert [v.year for v in values] == [2028, 2029]


def test_surplus_says_not_worth_it() -> None:
    result = _assess(_year(imported="200", export="260", balance="900"))
    assert result.status == STATUS_NOT_WORTH
    assert result.deficit_kwh_year == D("-720")
    assert result.money is None and result.extra_kwp is None


def test_small_gap_is_balanced() -> None:
    # 12 × 5 = 60 kWh, abaixo de 5% de 3120 (156).
    assert _assess(_year(imported="260", export="255")).status == STATUS_BALANCED


def test_loss_or_impossible_export_blocks_and_suspect_only_warns() -> None:
    cycles = _year()
    cycles[4] = _cycle(cycles[4].reference_month, verdict="LOSS")
    blocked = _assess(cycles)
    assert blocked.status == STATUS_FIX_FIRST
    assert blocked.problem_months == (cycles[4].reference_month,)

    suspect = _year()
    suspect[4] = _cycle(suspect[4].reference_month, verdict="SUSPECT")
    result = _assess(suspect)
    assert result.status == STATUS_EXPAND
    assert "SUSPECT_CYCLES" in result.warnings


def test_production_well_below_expected_recently_blocks() -> None:
    cycles = _year()
    cycles[-1] = _cycle(cycles[-1].reference_month, well_below=True)
    assert _assess(cycles).status == STATUS_FIX_FIRST
    old = _year()
    old[0] = _cycle(old[0].reference_month, well_below=True)
    assert _assess(old).status == STATUS_EXPAND


def test_unavailable_reasons() -> None:
    assert _assess(_year()[:11]).reasons == ("NOT_ENOUGH_CYCLES",)
    gap = _year()[:11] + [_cycle("2027-01")]
    assert _assess(gap).reasons == ("CYCLES_NOT_CONTIGUOUS",)
    no_meter = _year()
    no_meter[3] = _cycle(no_meter[3].reference_month, export=None)
    assert _assess(no_meter).reasons == ("MISSING_METER_OR_CONSUMPTION",)
    shared = _year()
    shared[2] = _cycle(shared[2].reference_month, share="60")
    assert _assess(shared).reasons == ("SHARE_NOT_CONFIRMED",)
    latest_unknown = _year()
    latest_unknown[-1] = _cycle(latest_unknown[-1].reference_month, share=None)
    result = _assess(latest_unknown)
    assert result.status == STATUS_UNAVAILABLE
    assert result.reasons == ("SHARE_NOT_CONFIRMED",)


def test_expand_without_size_when_power_or_measurement_missing() -> None:
    no_kwp = _assess(_year(), installed_kwp=None)
    assert no_kwp.status == STATUS_EXPAND
    assert no_kwp.reasons == ("INSTALLED_POWER_UNKNOWN",)
    assert no_kwp.extra_kwp is None
    estimated = _year()
    for k in range(3):
        estimated[k] = _cycle(estimated[k].reference_month, estimated=True)
    result = _assess(estimated)
    assert result.reasons == ("NOT_ENOUGH_MEASURED_PRODUCTION",)
    assert result.measured_cycles == 9


def test_money_unavailable_reasons() -> None:
    def reason(**changes: object) -> str | None:
        inputs = dataclasses.replace(MONEY, **changes) if changes else None  # type: ignore[arg-type]
        money = _assess(_year(), money_inputs=inputs).money
        assert money is not None
        return money.unavailable_reason

    assert reason() == "FULL_TARIFF_MISSING"
    assert reason(full_tariff_brl_kwh=None) == "FULL_TARIFF_MISSING"
    assert reason(wire_b_tariff_brl_kwh=None) == "WIRE_B_MISSING"
    assert reason(regime_confirmed=False) == "REGIME_NOT_CONFIRMED"
    assert reason(model_matches_bill=False) == "BILL_MODEL_MISMATCH"
    assert reason(reference_month="2029-02") == "TRANSITION_ENDED"
    assert reason(reference_month="2022-06") == "REGIME_NOT_CONFIRMED"


def test_low_grid_consumption_warns_minimum_billing() -> None:
    cycles = _year(imported="90", export="40")
    result = _assess(cycles)
    assert "MINIMUM_BILLING_MAY_APPLY" in result.warnings


def test_inverter_check_ranges() -> None:
    def check(extra: str, count: int = 1, ac: str | None = "3.0"):  # type: ignore[no-untyped-def]
        return inverter_check(
            installed_kwp=D("3.3"),
            extra_kwp=D(extra),
            device_count=count,
            inverter_ac_kw=None if ac is None else D(ac),
        )

    assert check("0.6") == (INVERTER_OK, D("1.30"))
    assert check("1.2") == (INVERTER_CHECK_DATASHEET, D("1.50"))
    assert check("1.3")[0] == INVERTER_NEW_NEEDED
    assert check("1.0", count=8) == (INVERTER_MICRO, None)
    assert check("1.0", ac=None) == (INVERTER_UNKNOWN, None)
    assert check("1.0", count=0) == (INVERTER_UNKNOWN, None)


# ---------------------------------------------------------------- serviço/rota

PLANT = uuid.UUID("00000000-0000-0000-0000-0000000000e1")


async def _factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _seed(factory, devices: int = 1, **plant_fields):  # type: ignore[no-untyped-def]
    async with factory() as session:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        session.add_all(
            [
                OrganizationRecord(id=org_a, name="A", slug=f"a-{org_a.hex[:8]}", active=True),
                OrganizationRecord(id=org_b, name="B", slug=f"b-{org_b.hex[:8]}", active=True),
            ]
        )
        session.add(Plant(id=PLANT, organization_id=org_a, name="Casa", **plant_fields))
        for k in range(devices):
            session.add(Device(plant_id=PLANT, serial_number=f"SN{k}", ac_capacity_kw=D("3.0")))
        await session.commit()
        return org_a, org_b


def _history_cycle(month: str, bill_id: str, **overrides: object) -> dict[str, object]:
    cycle: dict[str, object] = {
        "reference_month": month,
        "bill_id": bill_id,
        "cycle_start": f"{month}-01",
        # Ciclo inclui os dois extremos: 1º ao último dia do mês.
        "cycle_end": (
            date.fromisoformat(f"{add_months(month, 1)}-01") - timedelta(days=1)
        ).isoformat(),
        "imported_kwh": "260",
        "production_kwh": "400",
        "quality": None,
        "utility_check": {
            "verdict": "OK",
            "meter_export_kwh": "230",
            "previous_balance_kwh": "307",
            "credit_unit_value_brl": "0.716684",
        },
    }
    cycle.update(overrides)
    return cycle


def _install_fakes(monkeypatch, months: list[str], *, version: str = "0.5.0") -> None:  # type: ignore[no-untyped-def]
    ids = {m: str(uuid.uuid4()) for m in months}
    cycles = [_history_cycle(m, ids[m]) for m in months]

    async def fake_history(session, *, plant_id, plant_scope, limit):  # type: ignore[no-untyped-def]
        return {"cycles": cycles}

    reports = [
        SimpleNamespace(
            report=SimpleNamespace(
                reference_month=m,
                bill_id=ids[m],
                calculation_version=version,
                diagnostics=(),
                metrics=(
                    SimpleNamespace(key="savings_tariff_brl_kwh", value="0.891810", nature="X"),
                    SimpleNamespace(
                        key="savings_tariff_source", value="DISTRIBUTOR_FULL_TARIFF", nature="X"
                    ),
                    SimpleNamespace(key="tariff_class", value="B1", nature="MEASURED"),
                ),
            )
        )
        for m in months
    ]

    class FakeSnapshots:
        def __init__(self, session, plant_scope=None) -> None:  # type: ignore[no-untyped-def]
            pass

        async def list_recent_for_plant(self, *, plant_id, limit):  # type: ignore[no-untyped-def]
            return tuple(reports)

    bill = SimpleNamespace(
        generation_share_percent=D("100"),
        credit_balance_kwh=D("0"),
        wire_b_tariff_brl_kwh=D("0.175126"),
    )

    class FakeBills:
        def __init__(self, session, plant_scope=None) -> None:  # type: ignore[no-untyped-def]
            pass

        async def list_for_plant(self, *, plant_id):  # type: ignore[no-untyped-def]
            return tuple(SimpleNamespace(id=ids[m], bill=bill) for m in months)

    monkeypatch.setattr(expansion_service, "load_monthly_production_history", fake_history)
    monkeypatch.setattr(expansion_service, "MonthlyReportSnapshotRepository", FakeSnapshots)
    monkeypatch.setattr(expansion_service, "ConfirmedBillReadRepository", FakeBills)


def _run_service(monkeypatch, months, *, devices=1, version="0.5.0", **plant):  # type: ignore[no-untyped-def]
    factory, engine = asyncio.run(_factory())
    asyncio.run(_seed(factory, devices=devices, **plant))
    _install_fakes(monkeypatch, months, version=version)

    async def run():  # type: ignore[no-untyped-def]
        async with factory() as session:
            return await expansion_service.get_expansion_assessment(
                session, plant_id=PLANT, today=date(2026, 10, 25)
            )

    result = asyncio.run(run())
    asyncio.run(engine.dispose())
    return result


MONTHS = [add_months("2025-11", k) for k in range(12)]


def test_service_assembles_cycles_and_money(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    assessment, context, _payback = _run_service(
        monkeypatch,
        ["2024-08", *MONTHS],  # mês da ligação fica de fora
        installed_power_kwp=D("3.3"),
        commissioned_on=date(2024, 8, 10),
    )
    assert context == ()
    assert assessment.status == STATUS_EXPAND
    assert assessment.first_month == "2025-11"
    assert assessment.deficit_kwh_year == D("360")
    assert assessment.direction == "FALTA"
    # 4800 kWh em 365 dias (inclusivos) ÷ 3,3 kWp = 1454,5 → 1455; contar
    # (fim − início) sem o +1 daria 353 dias e 1504 (ampliação subestimada).
    assert assessment.yield_kwh_per_kwp_year == D("1455")
    assert assessment.balance_before_kwh == D("307")
    assert assessment.inverter_status == INVERTER_OK
    assert assessment.money is not None
    assert assessment.money.unavailable_reason is None
    assert assessment.money.monthly_saving_first_year_brl == D("21.50")


def test_service_keeps_the_latest_rebilled_cycle_of_a_month(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # O histórico vem em ordem cronológica e, num refaturamento, o mais novo
    # por último: ele vence. Aqui o refaturado de out/26 zera o consumo extra.
    _install_fakes(monkeypatch, MONTHS)
    original = expansion_service.load_monthly_production_history

    async def with_rebill(session, *, plant_id, plant_scope, limit):  # type: ignore[no-untyped-def]
        payload = await original(session, plant_id=plant_id, plant_scope=plant_scope, limit=limit)
        cycles = list(payload["cycles"])
        rebill = dict(cycles[-1])
        rebill["imported_kwh"] = "230"
        return {"cycles": [*cycles, rebill]}

    monkeypatch.setattr(expansion_service, "load_monthly_production_history", with_rebill)
    factory, engine = asyncio.run(_factory())
    asyncio.run(_seed(factory, installed_power_kwp=D("3.3"), commissioned_on=date(2024, 8, 10)))

    async def run():  # type: ignore[no-untyped-def]
        async with factory() as session:
            return await expansion_service.get_expansion_assessment(
                session, plant_id=PLANT, today=date(2026, 10, 25)
            )

    assessment, _, _ = asyncio.run(run())
    asyncio.run(engine.dispose())
    assert assessment.cycles_used == 12
    assert assessment.deficit_kwh_year == D("330")


def test_service_refuses_money_for_2023_plants_and_old_versions(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    assessment, _, _ = _run_service(
        monkeypatch,
        MONTHS,
        installed_power_kwp=D("3.3"),
        commissioned_on=date(2023, 5, 2),
    )
    assert assessment.money is not None
    assert assessment.money.unavailable_reason == "REGIME_NOT_CONFIRMED"

    outdated, _, _ = _run_service(
        monkeypatch,
        MONTHS,
        version="0.4.0",
        installed_power_kwp=D("3.3"),
        commissioned_on=date(2024, 8, 10),
    )
    assert outdated.money is not None
    assert outdated.money.unavailable_reason == "FULL_TARIFF_MISSING"


def test_service_flags_missing_commissioning_and_microinverters(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    assessment, context, _payback = _run_service(
        monkeypatch, MONTHS, devices=8, installed_power_kwp=D("3.3")
    )
    assert context == ("COMMISSIONING_DATE_MISSING",)
    assert assessment.inverter_status == INVERTER_MICRO
    # Sem data de ligação, o regime não é confirmado: sem reais.
    assert assessment.money is not None
    assert assessment.money.unavailable_reason == "REGIME_NOT_CONFIRMED"


def test_route_is_tenant_scoped_and_serializes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()
    factory, engine = asyncio.run(_factory())
    org_a, org_b = asyncio.run(_seed(factory))
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(intelligence_router, "SessionFactory", factory)
    token_a = encode_access_token(uuid.uuid4(), org_a, OperationsRole.READ.value)
    token_b = encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)

    with TestClient(app) as client:
        own = client.get(
            f"/energy/expansion/latest?plant_id={PLANT}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        foreign = client.get(
            f"/energy/expansion/latest?plant_id={PLANT}",
            headers={"Authorization": f"Bearer {token_b}"},
        )

    asyncio.run(engine.dispose())
    get_settings.cache_clear()
    assert own.status_code == 200
    body = own.json()
    assert body["status"] == "INDISPONIVEL"
    assert body["reasons"] == ["NOT_ENOUGH_CYCLES"]
    assert body["warnings"] == ["COMMISSIONING_DATE_MISSING"]
    assert body["money"] is None
    assert foreign.status_code == 404


# ------------------------------------------------------- retorno (etapa 2)

from mplacas.intelligence.expansion import (  # noqa: E402
    PAYBACK_INVERTER_NOT_IN_PROPOSAL,
    PAYBACK_MARKET_DATA_UNAVAILABLE,
    PAYBACK_NOT_APPLICABLE,
    PAYBACK_PROPOSAL_MISSING,
    expansion_payback,
)
from mplacas.intelligence.investor_metrics import InvestorPremises  # noqa: E402

PREMISES = InvestorPremises(
    cdi_per_year=D("0.14"), ipca_per_year=D("0.045"), tariff_growth_per_year=D("0.045")
)


def _payback(assessment=None, **overrides):  # type: ignore[no-untyped-def]
    params = dict(
        assessment=assessment or _assess(_year()),
        money_inputs=MONEY,
        proposal_brl=D("1500"),
        includes_inverter=False,
        recorded_on=date(2026, 10, 28),
        premises=PREMISES,
        indices_as_of_month="2026-09",
        today=date(2026, 10, 28),
    )
    params.update(overrides)
    return expansion_payback(**params)  # type: ignore[arg-type]


def test_payback_uses_capped_saving_and_ipca_against_flat_tariff() -> None:
    result = _payback()
    assert result.unavailable_reason is None
    # 30 kWh/mês × (0,891810 − 0,175126) = R$ 21,50 no 1º ano.
    assert result.first_year_monthly_saving_brl == D("21.50")
    assert result.payback_months_with_ipca is not None
    assert result.payback_months_no_growth is not None
    # Sem reajuste é a contraprova conservadora: nunca mais curto. O Fio B da
    # parte nova subindo e o O&M deixam o prazo acima de 1500 ÷ 21,50 ≈ 70.
    assert result.payback_months_with_ipca <= result.payback_months_no_growth
    assert result.payback_months_no_growth > 70
    assert 60 < result.payback_months_with_ipca < 120


def test_bigger_proposal_takes_longer() -> None:
    cheap = _payback(proposal_brl=D("1500")).payback_months_with_ipca
    pricey = _payback(proposal_brl=D("3000")).payback_months_with_ipca
    assert cheap is not None and pricey is not None and pricey > cheap


def test_payback_unavailable_reasons() -> None:
    assert _payback(proposal_brl=None).unavailable_reason == PAYBACK_PROPOSAL_MISSING
    assert _payback(premises=None).unavailable_reason == PAYBACK_MARKET_DATA_UNAVAILABLE
    surplus = _assess(_year(imported="200", export="260"))
    assert _payback(surplus).unavailable_reason == PAYBACK_NOT_APPLICABLE
    no_money = _assess(_year(), money_inputs=None)
    assert _payback(no_money).unavailable_reason == PAYBACK_NOT_APPLICABLE
    # Inversor novo necessário e a proposta não o inclui: não calcula.
    needs_inverter = _assess(_year(imported="460", export="230"), inverter_ac_kw=D("2.5"))
    assert needs_inverter.inverter_status == INVERTER_NEW_NEEDED
    assert (
        _payback(needs_inverter, includes_inverter=False).unavailable_reason
        == PAYBACK_INVERTER_NOT_IN_PROPOSAL
    )
    assert _payback(needs_inverter, includes_inverter=True).unavailable_reason is None


def test_proposal_endpoint_is_admin_scoped_audited_and_feeds_the_card(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    # BCB fora da allowlist: a rota não sai para a rede.
    monkeypatch.setenv("MPLACAS_EXTERNAL_HTTP_ALLOWED_HOSTS", "api.nepviewer.net")
    get_settings.cache_clear()
    import mplacas.plants.router as plants_router

    factory, engine = asyncio.run(_factory())
    org_a, org_b = asyncio.run(_seed(factory))
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(intelligence_router, "SessionFactory", factory)
    monkeypatch.setattr(plants_router, "SessionFactory", factory)
    admin = encode_access_token(uuid.uuid4(), org_a, OperationsRole.ADMIN.value)
    reader = encode_access_token(uuid.uuid4(), org_a, OperationsRole.READ.value)
    foreign = encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)
    url = f"/plants/{PLANT}/expansion-proposal"
    body = {"amount_brl": "1500.00", "includes_inverter": False}

    with TestClient(app) as client:
        saved = client.patch(url, json=body, headers={"Authorization": f"Bearer {admin}"})
        denied = client.patch(url, json=body, headers={"Authorization": f"Bearer {reader}"})
        other = client.patch(url, json=body, headers={"Authorization": f"Bearer {foreign}"})
        bad = client.patch(
            url, json={"amount_brl": "-1"}, headers={"Authorization": f"Bearer {admin}"}
        )
        card = client.get(
            f"/energy/expansion/latest?plant_id={PLANT}",
            headers={"Authorization": f"Bearer {reader}"},
        )
        cleared = client.patch(
            url, json={"amount_brl": None}, headers={"Authorization": f"Bearer {admin}"}
        )

    async def stored():  # type: ignore[no-untyped-def]
        from sqlalchemy import select

        from mplacas.audit.db_models import AuditEventRecord

        async with factory() as session:
            plant = await session.get(Plant, PLANT)
            events = (
                await session.scalars(
                    select(AuditEventRecord).where(
                        AuditEventRecord.action == "plant.expansion_proposal_updated"
                    )
                )
            ).all()
            return plant, events

    plant, events = asyncio.run(stored())
    asyncio.run(engine.dispose())
    get_settings.cache_clear()
    assert saved.status_code == 200
    assert saved.json()["amount_brl"] == "1500.00"
    assert saved.json()["recorded_on"] is not None
    assert denied.status_code == 403
    assert other.status_code == 404
    assert bad.status_code == 422
    # Sem 12 faturas, o card fica indisponível e o retorno "não se aplica",
    # mas a proposta salva aparece.
    payback = card.json()["payback"]
    assert payback["unavailable_reason"] == "NOT_APPLICABLE"
    assert payback["proposal_brl"] == "1500.00"
    assert cleared.status_code == 200 and cleared.json()["amount_brl"] is None
    assert plant.expansion_proposal_brl is None
    assert plant.expansion_proposal_recorded_on is None
    assert len(events) == 2
