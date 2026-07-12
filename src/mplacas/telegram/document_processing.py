from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mplacas.billing.models import UtilityBill
from mplacas.billing.parser import parse_equatorial_bill_text


class TelegramDocumentProcessingError(ValueError):
    """Falha segura no processamento de uma fatura recebida."""


@dataclass(frozen=True, slots=True)
class ProcessedBillDocument:
    bill: UtilityBill
    extracted_text_bytes: int


def process_pdf_bill(
    content: bytes,
    *,
    extract_text: Callable[[bytes], str],
    max_text_bytes: int,
) -> ProcessedBillDocument:
    """Valida, extrai e interpreta uma fatura sem persistir o PDF bruto."""
    if not content.startswith(b"%PDF-"):
        raise TelegramDocumentProcessingError("document is not a PDF")
    if max_text_bytes <= 0:
        raise TelegramDocumentProcessingError("invalid text limit")

    text = extract_text(content)
    if not isinstance(text, str) or not text.strip():
        raise TelegramDocumentProcessingError("PDF has no extractable text")
    text_size = len(text.encode("utf-8"))
    if text_size > max_text_bytes:
        raise TelegramDocumentProcessingError("extracted text is too large")

    bill = parse_equatorial_bill_text(text)
    return ProcessedBillDocument(bill=bill, extracted_text_bytes=text_size)
