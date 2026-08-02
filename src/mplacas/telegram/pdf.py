from __future__ import annotations

import asyncio
import importlib
import logging
import math
import multiprocessing
import time
from io import BytesIO
from multiprocessing.connection import Connection
from typing import Any


logger = logging.getLogger(__name__)


class PdfTextExtractionError(ValueError):
    """Falha controlada ao extrair texto de uma fatura PDF."""


def extract_pdf_text(
    content: bytes,
    *,
    max_pages: int = 10,
    max_text_bytes: int = 250_000,
) -> str:
    """Extrai texto localmente, sem rede e sem persistir o arquivo bruto."""
    if not content.startswith(b"%PDF-"):
        raise PdfTextExtractionError("document is not a PDF")
    if max_pages <= 0:
        raise PdfTextExtractionError("invalid page limit")
    if max_text_bytes <= 0:
        raise PdfTextExtractionError("invalid text limit")

    try:
        # Importado somente dentro do caminho de parsing. No worker isolado isso
        # acontece depois da aplicação dos limites de recursos do processo.
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content), strict=True)
    except Exception as exc:  # pypdf normaliza vários erros de estrutura
        raise PdfTextExtractionError("PDF structure is invalid") from exc

    if reader.is_encrypted:
        raise PdfTextExtractionError("encrypted PDFs are not accepted")
    if not reader.pages or len(reader.pages) > max_pages:
        raise PdfTextExtractionError("PDF page count is not allowed")

    chunks: list[str] = []
    extracted_bytes = 0
    try:
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                normalized = text.strip()
                extracted_bytes += len(normalized.encode("utf-8"))
                if chunks:
                    extracted_bytes += 1
                if extracted_bytes > max_text_bytes:
                    raise PdfTextExtractionError("extracted text is too large")
                chunks.append(normalized)
    except PdfTextExtractionError:
        raise
    except Exception as exc:
        raise PdfTextExtractionError("PDF text extraction failed") from exc

    extracted = "\n".join(chunks).strip()
    if not extracted:
        raise PdfTextExtractionError("PDF has no extractable text")
    return extracted


def _apply_process_limits(*, cpu_seconds: int, memory_bytes: int) -> None:
    """Aplica limites fortes no Linux; o timeout do pai permanece multiplataforma."""
    try:
        resource: Any = importlib.import_module("resource")
    except ImportError:  # pragma: no cover - Windows local; produção roda em Linux
        return

    cpu_limit = max(1, math.ceil(cpu_seconds))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))


def _pdf_parser_worker(
    result_connection: Connection,
    content: bytes,
    max_pages: int,
    max_text_bytes: int,
    cpu_seconds: int,
    memory_bytes: int,
) -> None:
    """Entrada do processo descartável; nunca devolve bytes ou detalhes do documento em erro."""
    try:
        _apply_process_limits(cpu_seconds=cpu_seconds, memory_bytes=memory_bytes)
        extracted = extract_pdf_text(
            content,
            max_pages=max_pages,
            max_text_bytes=max_text_bytes,
        )
        result_connection.send(("ok", extracted))
    except BaseException as exc:
        # Apenas a classe cruza a fronteira. Mensagens de bibliotecas podem
        # conter fragmentos do PDF e não devem chegar a logs/respostas.
        result_connection.send(("error", type(exc).__name__))
    finally:
        result_connection.close()


def _stop_process(process: Any) -> None:
    if not process.is_alive():
        process.join(timeout=0.1)
        return
    process.terminate()
    process.join(timeout=0.5)
    if process.is_alive():
        process.kill()
        process.join(timeout=0.5)


async def extract_pdf_text_isolated(
    content: bytes,
    *,
    max_pages: int = 10,
    max_text_bytes: int = 250_000,
    timeout_seconds: float = 5.0,
    cpu_seconds: int = 3,
    memory_bytes: int = 268_435_456,
) -> str:
    """Extrai PDF não confiável fora do worker web, com cancelamento e timeout."""
    if timeout_seconds <= 0 or cpu_seconds <= 0 or memory_bytes <= 0:
        raise PdfTextExtractionError("invalid parser resource limit")
    if not content.startswith(b"%PDF-"):
        raise PdfTextExtractionError("document is not a PDF")

    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_pdf_parser_worker,
        args=(
            send_connection,
            content,
            max_pages,
            max_text_bytes,
            cpu_seconds,
            memory_bytes,
        ),
        name="mplacas-pdf-parser",
        daemon=True,
    )
    process.start()
    send_connection.close()
    deadline = time.monotonic() + timeout_seconds

    try:
        while True:
            if receive_connection.poll():
                try:
                    outcome, payload = receive_connection.recv()
                except EOFError as exc:
                    logger.warning(
                        "pdf_parser_process_closed_pipe",
                        extra={"worker_exit_code": process.exitcode},
                    )
                    raise PdfTextExtractionError("PDF parser process failed") from exc
                if outcome == "ok":
                    return str(payload)
                logger.warning(
                    "pdf_parser_rejected_document",
                    extra={"worker_error_type": str(payload)},
                )
                raise PdfTextExtractionError("PDF parser rejected document")
            if not process.is_alive():
                logger.warning(
                    "pdf_parser_process_failed",
                    extra={"worker_exit_code": process.exitcode},
                )
                raise PdfTextExtractionError("PDF parser process failed")
            if time.monotonic() >= deadline:
                logger.warning("pdf_parser_timeout", extra={"timeout_seconds": timeout_seconds})
                raise PdfTextExtractionError("PDF text extraction timed out")
            await asyncio.sleep(0.01)
    finally:
        receive_connection.close()
        await asyncio.to_thread(_stop_process, process)
