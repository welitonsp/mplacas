from __future__ import annotations

from decimal import Decimal

import pytest

from mplacas.telegram.document_processing import (
    TelegramDocumentProcessingError,
    process_pdf_bill,
)


BILL_TEXT = """
Equatorial Energia
Referência: 06/2026
Leitura anterior: 18/05/2026
Leitura atual: 16/06/2026
Dias faturados: 30
Energia ativa consumida: 278 kWh
Energia injetada: 182 kWh
Energia compensada: 278 kWh
Saldo de créditos: 63,98 kWh
Total a pagar: R$ 80,21
Contribuição de iluminação pública: R$ 30,21
"""


def test_processes_valid_pdf_text_without_storing_binary() -> None:
    result = process_pdf_bill(
        b"%PDF-1.7 synthetic",
        extract_text=lambda _: BILL_TEXT,
        max_text_bytes=10_000,
    )
    assert result.bill.reference_month == "2026-06"
    assert result.bill.total_amount_brl == Decimal("80.21")
    assert result.extracted_text_bytes > 0


def test_rejects_non_pdf_signature() -> None:
    with pytest.raises(TelegramDocumentProcessingError, match="not a PDF"):
        process_pdf_bill(b"not-pdf", extract_text=lambda _: BILL_TEXT, max_text_bytes=10_000)


def test_rejects_empty_extraction() -> None:
    with pytest.raises(TelegramDocumentProcessingError, match="no extractable text"):
        process_pdf_bill(b"%PDF-1.7", extract_text=lambda _: "", max_text_bytes=10_000)


def test_rejects_extracted_text_over_limit() -> None:
    with pytest.raises(TelegramDocumentProcessingError, match="too large"):
        process_pdf_bill(b"%PDF-1.7", extract_text=lambda _: BILL_TEXT, max_text_bytes=10)
