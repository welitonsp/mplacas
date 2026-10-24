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
    assert _extract_tariff_class(_text("B B1 RESIDENCIAL - BAIXA RENDA CONVENCIONAL")) == (
        "B1_RESIDENCIAL_BAIXA_RENDA"
    )
    assert _extract_tariff_class(_text("B B3 COMERCIAL - COMERCIAL CONVENCIONAL")) == (
        "B3_COMERCIAL_CONVENCIONAL"
    )
    assert _extract_tariff_class(_text("B B2 RURAL - RURAL AGROPECUARIA CONVENCIONAL")) == (
        "B2_RURAL_CONVENCIONAL"
    )


def test_unrecognized_or_missing_classification_is_unidentified() -> None:
    assert _extract_tariff_class(_text("B B1 RESIDENCIAL - RESIDENCIAL NORMAL")) == (
        UNIDENTIFIED_TARIFF_CLASS
    )
    assert _extract_tariff_class("fatura sem a linha de classe") == UNIDENTIFIED_TARIFF_CLASS


def test_legacy_bill_keeps_b1_but_marked_presumed_new_unidentified_gets_none() -> None:
    assert resolve_tariff_class(None) == ("B1_RESIDENCIAL_CONVENCIONAL", True)
    assert resolve_tariff_class(UNIDENTIFIED_TARIFF_CLASS) == (None, False)
    assert resolve_tariff_class("B3_COMERCIAL_CONVENCIONAL") == ("B3_COMERCIAL_CONVENCIONAL", False)
