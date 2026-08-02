from __future__ import annotations

import asyncio
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from mplacas.telegram.pdf import (
    PdfTextExtractionError,
    extract_pdf_text,
    extract_pdf_text_isolated,
)


def _text_pdf(text: str) -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output)
    document.drawString(72, 720, text)
    document.save()
    return output.getvalue()


def _encrypted_pdf() -> bytes:
    source = PdfReader(BytesIO(_text_pdf("sensitive bill")))
    writer = PdfWriter()
    writer.append_pages_from_reader(source)
    writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_extracts_text_with_current_pypdf_contract() -> None:
    assert "Equatorial Energia" in extract_pdf_text(_text_pdf("Equatorial Energia"))


def test_rejects_encrypted_pdf() -> None:
    with pytest.raises(PdfTextExtractionError, match="encrypted"):
        extract_pdf_text(_encrypted_pdf())


def test_rejects_compressed_text_expansion_over_limit() -> None:
    compressed_pdf = _text_pdf("A" * 2_000)

    with pytest.raises(PdfTextExtractionError, match="too large"):
        extract_pdf_text(compressed_pdf, max_text_bytes=100)


@pytest.mark.asyncio
async def test_isolated_parser_returns_text_from_disposable_process() -> None:
    extracted = await extract_pdf_text_isolated(
        _text_pdf("Fatura isolada"),
        timeout_seconds=10,
    )

    assert "Fatura isolada" in extracted


@pytest.mark.asyncio
async def test_isolated_parser_enforces_wall_clock_timeout() -> None:
    with pytest.raises(PdfTextExtractionError, match="timed out"):
        await extract_pdf_text_isolated(
            _text_pdf("Fatura com timeout"),
            timeout_seconds=0.000_001,
        )


@pytest.mark.asyncio
async def test_isolated_parser_does_not_block_event_loop() -> None:
    parser_task = asyncio.create_task(
        extract_pdf_text_isolated(_text_pdf("Fatura concorrente"), timeout_seconds=10)
    )
    await asyncio.sleep(0)

    assert not parser_task.done()
    assert "Fatura concorrente" in await parser_task
