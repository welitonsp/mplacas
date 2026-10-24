from datetime import date
from decimal import Decimal

from mplacas.billing.models import UtilityBill
from mplacas.reports.utility_check import (
    VERDICT_IMPOSSIBLE,
    VERDICT_LOSS,
    VERDICT_OK,
    VERDICT_SUSPECT,
    VERDICT_UNVERIFIABLE,
    check_cycle,
    export_share,
)


def _bill(
    *,
    generation: str | None = "238",
    compensated: str = "255.98",
    balance: str = "0",
    imported: str = "338",
    share: str | None = "100",
    expiring: str | None = "0",
) -> UtilityBill:
    return UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month="2026-10",
        cycle_start=date(2026, 9, 15),
        cycle_end=date(2026, 10, 15),
        billed_days=31,
        imported_kwh=Decimal(imported),
        injected_kwh=Decimal(compensated),
        compensated_kwh=Decimal(compensated),
        credit_balance_kwh=Decimal(balance),
        total_amount_brl=Decimal("171.32"),
        generation_cycle_kwh=None if generation is None else Decimal(generation),
        generation_share_percent=None if share is None else Decimal(share),
        credits_expiring_30d_kwh=None if expiring is None else Decimal(expiring),
    )


PREVIOUS = _bill(generation="235", compensated="221", balance="17.98", imported="221")


def test_real_october_bill_credits_are_conserved() -> None:
    # Fatura real out/26: 238 do medidor + 17,98 de saldo = 255,98 usados, saldo 0.
    check = check_cycle(
        bill=_bill(),
        previous_bill=PREVIOUS,
        production_kwh=Decimal("550"),
        previous_export_shares=[],
    )
    assert check.verdict == VERDICT_OK
    assert check.missing_credits_kwh == Decimal("0.00")
    assert check.credits_available_kwh == Decimal("255.98")
    assert check.export_share_percent == Decimal("43.3")


def test_minimum_billing_keeps_unused_credit_in_balance_not_lost() -> None:
    # out/24 real: 257 + 233 de saldo; usou 106 (mínimo de 30 kWh cobrado), saldo 384.
    previous = _bill(generation="352", compensated="119", balance="233", imported="149")
    bill = _bill(generation="257", compensated="106", balance="384", imported="136")
    check = check_cycle(
        bill=bill, previous_bill=previous, production_kwh=None, previous_export_shares=[]
    )
    assert check.verdict == VERDICT_OK


def test_credits_that_vanish_are_proven_loss() -> None:
    bill = _bill(compensated="240", balance="0")  # 255,98 disponíveis, 240 usados, saldo 0
    check = check_cycle(
        bill=bill, previous_bill=PREVIOUS, production_kwh=Decimal("550"), previous_export_shares=[]
    )
    assert check.verdict == VERDICT_LOSS
    assert check.missing_credits_kwh == Decimal("15.98")
    assert "CREDITS_MISSING" in check.reasons


def test_rounding_hundredth_is_not_loss() -> None:
    bill = _bill(compensated="255.97", balance="0")
    check = check_cycle(
        bill=bill, previous_bill=PREVIOUS, production_kwh=None, previous_export_shares=[]
    )
    assert check.verdict == VERDICT_OK


def test_meter_export_above_inverter_production_is_impossible() -> None:
    check = check_cycle(
        bill=_bill(),
        previous_bill=PREVIOUS,
        production_kwh=Decimal("200"),
        previous_export_shares=[],
    )
    assert check.verdict == VERDICT_IMPOSSIBLE


def test_export_within_inverter_tolerance_is_not_impossible() -> None:
    check = check_cycle(
        bill=_bill(),
        previous_bill=PREVIOUS,
        production_kwh=Decimal("230"),
        previous_export_shares=[],
    )
    assert check.verdict == VERDICT_OK  # 238 ≤ 230 × 1,05


def test_export_share_far_below_history_is_suspicion_not_proof() -> None:
    check = check_cycle(
        bill=_bill(generation="100", compensated="117.98"),
        previous_bill=PREVIOUS,
        production_kwh=Decimal("600"),
        previous_export_shares=[Decimal("45"), Decimal("42"), Decimal("48")],
    )
    assert check.verdict == VERDICT_SUSPECT
    assert check.export_share_baseline_percent == Decimal("45.0")


def test_share_drop_needs_three_previous_cycles() -> None:
    check = check_cycle(
        bill=_bill(generation="100", compensated="117.98"),
        previous_bill=PREVIOUS,
        production_kwh=Decimal("600"),
        previous_export_shares=[Decimal("45"), Decimal("42")],
    )
    assert check.verdict == VERDICT_OK
    assert check.export_share_baseline_percent is None


def test_without_meter_reading_or_previous_bill_is_unverifiable_never_ok() -> None:
    no_meter = check_cycle(
        bill=_bill(generation=None),
        previous_bill=PREVIOUS,
        production_kwh=None,
        previous_export_shares=[],
    )
    assert no_meter.verdict == VERDICT_UNVERIFIABLE
    assert "NO_METER_READING" in no_meter.reasons
    no_previous = check_cycle(
        bill=_bill(), previous_bill=None, production_kwh=None, previous_export_shares=[]
    )
    assert no_previous.verdict == VERDICT_UNVERIFIABLE
    assert "NO_PREVIOUS_BILL" in no_previous.reasons
    assert check_cycle(
        bill=None, previous_bill=None, production_kwh=None, previous_export_shares=[]
    ).verdict == (VERDICT_UNVERIFIABLE)


def test_export_share_needs_meter_and_positive_production() -> None:
    assert export_share(production_kwh=Decimal("0"), bill=_bill()) is None
    assert export_share(production_kwh=Decimal("500"), bill=_bill(generation=None)) is None
    assert export_share(production_kwh=Decimal("476"), bill=_bill()) == Decimal("50.0")


def test_more_credits_used_than_available_is_unbalanced_never_ok() -> None:
    # 100 disponíveis, 250 usados, saldo 0: a conta não fecha para nenhum lado.
    previous = _bill(generation="0", compensated="0", balance="0")
    bill = _bill(generation="100", compensated="250", balance="0")
    check = check_cycle(
        bill=bill, previous_bill=previous, production_kwh=None, previous_export_shares=[]
    )
    assert check.verdict == VERDICT_UNVERIFIABLE
    assert "CREDITS_UNBALANCED" in check.reasons
    assert check.missing_credits_kwh is None


def test_estimated_production_skips_impossible_and_share_checks() -> None:
    # Produção com dias estimados pelo sol pode ter sido elevada até o medidor
    # (ADR-082): comparar inversor × medidor seria circular.
    check = check_cycle(
        bill=_bill(),
        previous_bill=PREVIOUS,
        production_kwh=Decimal("200"),
        previous_export_shares=[Decimal("45"), Decimal("42"), Decimal("48")],
        production_estimated=True,
    )
    assert check.verdict == VERDICT_OK  # créditos fecham; nível 2 e 3 não rodam
    assert "PRODUCTION_ESTIMATED" in check.reasons
    assert check.export_share_percent is None


def test_ambiguous_previous_bill_is_unverifiable() -> None:
    check = check_cycle(
        bill=_bill(),
        previous_bill=PREVIOUS,
        production_kwh=None,
        previous_export_shares=[],
        previous_bill_ambiguous=True,
    )
    assert check.verdict == VERDICT_UNVERIFIABLE
    assert "AMBIGUOUS_PREVIOUS_BILL" in check.reasons


def test_proof_numbers_come_from_the_meter_and_previous_balance() -> None:
    check = check_cycle(
        bill=_bill(), previous_bill=PREVIOUS, production_kwh=None, previous_export_shares=[]
    )
    assert check.meter_export_kwh == Decimal("238")
    assert check.previous_balance_kwh == Decimal("17.98")


def test_loss_is_confirmed_only_with_full_generation_share() -> None:
    bill = _bill(compensated="240", balance="0", share="100")
    check = check_cycle(
        bill=bill, previous_bill=PREVIOUS, production_kwh=None, previous_export_shares=[]
    )
    assert check.verdict == VERDICT_LOSS
    assert check.loss_confirmed is True


def test_gap_without_confirmed_share_is_loss_not_confirmed() -> None:
    for share in (None, "0", "60"):
        bill = _bill(compensated="240", balance="0", share=share)
        check = check_cycle(
            bill=bill, previous_bill=PREVIOUS, production_kwh=None, previous_export_shares=[]
        )
        assert check.verdict == VERDICT_LOSS
        assert check.loss_confirmed is False
        assert "SHARE_NOT_CONFIRMED" in check.reasons


def test_gap_announced_as_expiring_is_expiry_not_loss() -> None:
    # Saldo grande, uso pequeno: avisou 30 a vencer, usou 10; sumiram 20.
    previous = _bill(generation="0", compensated="0", balance="500", imported="0", expiring="30")
    bill = _bill(generation="0", compensated="10", balance="470", imported="10")
    check = check_cycle(
        bill=bill, previous_bill=previous, production_kwh=None, previous_export_shares=[]
    )
    assert check.verdict == VERDICT_OK
    assert check.expired_credits_kwh == Decimal("20.00")
    assert "CREDITS_EXPIRED" in check.reasons
    assert check.loss_confirmed is False


def test_expiry_already_consumed_in_cycle_does_not_mask_loss() -> None:
    # Avisou 20 a vencer, mas o ciclo usou 240 de crédito: o bloco a vencer
    # foi consumido. Os 15,98 sumidos não podem virar "vencimento".
    previous = _bill(
        generation="235", compensated="221", balance="17.98", imported="221", expiring="20"
    )
    bill = _bill(compensated="240", balance="0")
    check = check_cycle(
        bill=bill, previous_bill=previous, production_kwh=None, previous_export_shares=[]
    )
    assert check.verdict == VERDICT_LOSS
    assert check.missing_credits_kwh == Decimal("15.98")
    assert check.expired_credits_kwh is None


def test_partial_expiry_leaves_remainder_as_missing() -> None:
    # Saldo grande, uso pequeno: 30 a vencer, usou 10 → no máximo 20 venceram.
    previous = _bill(generation="0", compensated="0", balance="500", imported="0", expiring="30")
    bill = _bill(generation="0", compensated="10", balance="465", imported="10")
    check = check_cycle(
        bill=bill, previous_bill=previous, production_kwh=None, previous_export_shares=[]
    )
    # gap = 500 − 10 − 465 = 25; até 20 venceram; 5 faltam.
    assert check.verdict == VERDICT_LOSS
    assert check.expired_credits_kwh == Decimal("20.00")
    assert check.missing_credits_kwh == Decimal("5.00")
    assert {"CREDITS_EXPIRED", "CREDITS_MISSING"} <= set(check.reasons)


def test_gap_larger_than_announced_expiry_is_still_loss() -> None:
    previous = _bill(
        generation="235", compensated="221", balance="17.98", imported="221", expiring="5"
    )
    bill = _bill(compensated="240", balance="0")
    check = check_cycle(
        bill=bill, previous_bill=previous, production_kwh=None, previous_export_shares=[]
    )
    assert check.verdict == VERDICT_LOSS


def test_credit_unit_value_is_full_tariff_plus_flag_minus_wire_b() -> None:
    from mplacas.reports.utility_check import credit_unit_value_brl

    from dataclasses import replace

    bill = replace(_bill(), wire_b_tariff_brl_kwh=Decimal("0.175126"))
    # out/26: 1,146180 cheia com impostos + 0,011721 bandeira − 0,175126 Fio B.
    assert credit_unit_value_brl(
        savings_tariff_brl_kwh=Decimal("1.146180"),
        flag_tariff_brl_kwh=Decimal("0.011721"),
        bill=bill,
    ) == Decimal("0.982775")
    # Sem Fio B lido ou sem tarifa: nenhum valor presumido.
    assert (
        credit_unit_value_brl(
            savings_tariff_brl_kwh=Decimal("1.146180"), flag_tariff_brl_kwh=None, bill=_bill()
        )
        is None
    )
    assert (
        credit_unit_value_brl(savings_tariff_brl_kwh=None, flag_tariff_brl_kwh=None, bill=bill)
        is None
    )


def test_missing_credits_value_uses_cycle_unit_value() -> None:
    from mplacas.reports.utility_check import missing_credits_value_brl

    check = check_cycle(
        bill=_bill(compensated="240", balance="0"),
        previous_bill=PREVIOUS,
        production_kwh=None,
        previous_export_shares=[],
    )
    assert missing_credits_value_brl(check, Decimal("0.982775")) == Decimal("15.70")
    assert missing_credits_value_brl(check, None) is None
    ok = check_cycle(
        bill=_bill(), previous_bill=PREVIOUS, production_kwh=None, previous_export_shares=[]
    )
    assert missing_credits_value_brl(ok, Decimal("0.982775")) is None
