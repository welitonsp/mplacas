"""ADR-087: classe tarifária lida da fatura, nunca presumida em fatura nova."""

from mplacas.billing.parser import UNIDENTIFIED_TARIFF_CLASS, _extract_tariff_class
from mplacas.intelligence.cycle_service import resolve_tariff_class


def _text(classification: str) -> str:
    return " ".join(f"classificação: {classification} fulano de tal rua x".casefold().split())


def test_reads_real_equatorial_classification_without_the_holder_name() -> None:
    value = _extract_tariff_class(_text("B B1 RESIDENCIAL - RESIDENCIAL NORMAL CONVENCIONAL"))
    assert value == "B1_RESIDENCIAL_CONVENCIONAL"
    assert "FULANO" not in value


def test_reads_white_tariff_social_tariff_and_other_classes() -> None:
    assert _extract_tariff_class(_text("B B1 RESIDENCIAL - RESIDENCIAL NORMAL BRANCA")) == (
        "B1_RESIDENCIAL_BRANCA"
    )
    assert _extract_tariff_class(
        _text("B B1 RESIDENCIAL - RESIDENCIAL BAIXA RENDA CONVENCIONAL")
    ) == ("B1_RESIDENCIAL_BAIXA_RENDA")
    assert _extract_tariff_class(_text("B B3 COMERCIAL - COMERCIAL CONVENCIONAL")) == (
        "B3_COMERCIAL_CONVENCIONAL"
    )
    assert _extract_tariff_class(_text("B B2 RURAL - RURAL AGROPECUARIA CONVENCIONAL")) == (
        "B2_RURAL_CONVENCIONAL"
    )


def test_holder_name_never_decides_the_modality() -> None:
    # O nome vem logo depois da modalidade: "Branca", "Social" ou
    # "Convencional" no nome não mudam nada.
    for name in ("maria branca silva", "joao social", "ana baixa renda", "convencional"):
        text = " ".join(
            f"classificação: b b1 residencial - residencial normal convencional {name}".split()
        )
        assert _extract_tariff_class(text) == "B1_RESIDENCIAL_CONVENCIONAL"
    branca = " ".join("classificação: b b1 residencial - residencial normal branca joao".split())
    assert _extract_tariff_class(branca) == "B1_RESIDENCIAL_BRANCA"
    # Fatura sem modalidade e titular "Branca": nunca vira tarifa branca.
    no_modality = " ".join(
        "classificação: b b1 residencial - residencial maria branca silva".split()
    )
    assert _extract_tariff_class(no_modality) == UNIDENTIFIED_TARIFF_CLASS


def test_discounted_subclasses_and_too_long_phrases_fail_closed() -> None:
    for classification in (
        "B B2 RURAL - RURAL IRRIGANTE CONVENCIONAL",
        "B B2 RURAL - COOPERATIVA DE ELETRIFICACAO RURAL CONVENCIONAL",
        "B B1 RESIDENCIAL - UMA DUAS TRES QUATRO CINCO SEIS CONVENCIONAL",
        "A A4 INDUSTRIAL - HORARIA AZUL",
    ):
        assert _extract_tariff_class(_text(classification)) == UNIDENTIFIED_TARIFF_CLASS
    assert _extract_tariff_class(
        _text("B B4A ILUMINAÇÃO PÚBLICA - ILUMINACAO PUBLICA CONVENCIONAL")
    ) == ("B4A_ILUMINACAO_PUBLICA_CONVENCIONAL")


def test_unrecognized_or_missing_classification_is_unidentified() -> None:
    assert _extract_tariff_class(_text("B B1 RESIDENCIAL - RESIDENCIAL NORMAL")) == (
        UNIDENTIFIED_TARIFF_CLASS
    )
    assert _extract_tariff_class("fatura sem a linha de classe") == UNIDENTIFIED_TARIFF_CLASS


def test_legacy_bill_keeps_b1_but_marked_presumed_new_unidentified_gets_none() -> None:
    assert resolve_tariff_class(None) == ("B1_RESIDENCIAL_CONVENCIONAL", True)
    assert resolve_tariff_class(UNIDENTIFIED_TARIFF_CLASS) == (None, False)
    assert resolve_tariff_class("B3_COMERCIAL_CONVENCIONAL") == ("B3_COMERCIAL_CONVENCIONAL", False)


def test_pdf_completion_replaces_unidentified_class_but_never_erases_it() -> None:
    from dataclasses import replace
    from datetime import date
    from decimal import Decimal
    from types import SimpleNamespace

    from mplacas.billing.completion import complete_missing_fields
    from mplacas.billing.models import UtilityBill

    bill = UtilityBill(
        distributor="EQUATORIAL_GO",
        reference_month="2026-10",
        cycle_start=date(2026, 9, 15),
        cycle_end=date(2026, 10, 15),
        billed_days=31,
        imported_kwh=Decimal("338"),
        injected_kwh=Decimal("255.98"),
        compensated_kwh=Decimal("255.98"),
        credit_balance_kwh=Decimal("0"),
        total_amount_brl=Decimal("171.32"),
        tariff_class="B1_RESIDENCIAL_CONVENCIONAL",
    )
    identity = {
        name: getattr(bill, name)
        for name in (
            "cycle_start",
            "cycle_end",
            "billed_days",
            "imported_kwh",
            "injected_kwh",
            "compensated_kwh",
            "credit_balance_kwh",
            "total_amount_brl",
        )
    }
    empty = dict.fromkeys(
        (
            "tariff_with_taxes_brl_kwh",
            "tariff_without_taxes_brl_kwh",
            "wire_b_tariff_brl_kwh",
            "generation_cycle_kwh",
            "generation_share_percent",
            "credits_expiring_30d_kwh",
            "flag_tariff_brl_kwh",
            "non_energy_credits_brl",
        )
    )
    for stored in (None, UNIDENTIFIED_TARIFF_CLASS):
        record = SimpleNamespace(**identity, **empty, tariff_class=stored)
        assert "tariff_class" in complete_missing_fields(record, bill)  # type: ignore[arg-type]
        assert record.tariff_class == "B1_RESIDENCIAL_CONVENCIONAL"
    record = SimpleNamespace(**identity, **empty, tariff_class="B1_RESIDENCIAL_CONVENCIONAL")
    unidentified_pdf = replace(bill, tariff_class=UNIDENTIFIED_TARIFF_CLASS)
    assert complete_missing_fields(record, unidentified_pdf) == ()  # type: ignore[arg-type]
    assert record.tariff_class == "B1_RESIDENCIAL_CONVENCIONAL"
    # Fatura antiga (NULL, presumiria B1) + PDF sem classe: vira não identificada.
    legacy = SimpleNamespace(**identity, **empty, tariff_class=None)
    assert complete_missing_fields(legacy, unidentified_pdf) == ("tariff_class",)  # type: ignore[arg-type]
    assert legacy.tariff_class == UNIDENTIFIED_TARIFF_CLASS
