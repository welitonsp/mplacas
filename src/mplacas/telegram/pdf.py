from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader


class PdfTextExtractionError(ValueError):
    """Falha controlada ao extrair texto de uma fatura PDF."""


def extract_pdf_text(content: bytes, *, max_pages: int = 10) -> str:
    """Extrai texto localmente, sem rede e sem persistir o arquivo bruto."""
    if not content.startswith(b"%PDF-"):
        raise PdfTextExtractionError("document is not a PDF")
    if max_pages <= 0:
        raise PdfTextExtractionError("invalid page limit")

    try:
        reader = PdfReader(BytesIO(content), strict=True)
    except Exception as exc:  # pypdf normaliza vários erros de estrutura
        raise PdfTextExtractionError("PDF structure is invalid") from exc

    if reader.is_encrypted:
        raise PdfTextExtractionError("encrypted PDFs are not accepted")
    if not reader.pages or len(reader.pages) > max_pages:
        raise PdfTextExtractionError("PDF page count is not allowed")

    chunks: list[str] = []
    try:
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(text.strip())
    except Exception as exc:
        raise PdfTextExtractionError("PDF text extraction failed") from exc

    extracted = "\n".join(chunks).strip()
    if not extracted:
        raise PdfTextExtractionError("PDF has no extractable text")
    return extracted
