from __future__ import annotations

import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.parser import BillParseError, parse_equatorial_bill_text
from mplacas.billing.repository import UtilityBillRepository
from mplacas.core.config import get_settings
from mplacas.db.models import Plant
from mplacas.db.session import SessionFactory
from mplacas.telegram.client import TelegramClient, TelegramClientError
from mplacas.telegram.document_processing import (
    TelegramDocumentProcessingError,
    process_pdf_bill,
)
from mplacas.telegram.pdf import PdfTextExtractionError, extract_pdf_text
from mplacas.telegram.service import TelegramUpdateError, parse_authorized_update

router = APIRouter(prefix="/telegram", tags=["telegram"])


def _pending_message(reference_month: str) -> str:
    return (
        f"Fatura {reference_month} recebida e analisada. "
        "Ela ficou pendente de revisão humana antes da consolidação."
    )


async def _resolve_telegram_plant_scope(session: AsyncSession) -> uuid.UUID:
    plant_ids = list((await session.execute(select(Plant.id).limit(2))).scalars())
    if len(plant_ids) == 1:
        return plant_ids[0]
    raise HTTPException(
        status_code=409,
        detail="Telegram bill intake requires exactly one configured plant",
    )


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def telegram_webhook(
    payload: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    if not settings.telegram_configured or settings.telegram_webhook_secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram is not configured",
        )

    expected = settings.telegram_webhook_secret.get_secret_value()
    allowed_user_id = settings.telegram_allowed_user_id
    if allowed_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram is not configured",
        )
    if not x_telegram_bot_api_secret_token or not secrets.compare_digest(
        x_telegram_bot_api_secret_token, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )

    try:
        message = parse_authorized_update(
            payload,
            allowed_user_id=allowed_user_id,
            max_document_bytes=settings.telegram_document_max_bytes,
        )
    except TelegramUpdateError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    assert settings.telegram_bot_token is not None
    client = TelegramClient(
        bot_token=settings.telegram_bot_token.get_secret_value(),
        timeout_seconds=settings.request_timeout_seconds,
    )

    if message.kind == "command":
        return {
            "accepted": True,
            "kind": "command",
            "command": message.text,
        }

    if message.kind == "text":
        assert message.text is not None
        if len(message.text.encode("utf-8")) > settings.bill_text_max_bytes:
            raise HTTPException(
                status_code=413,
                detail="bill text exceeds configured size limit",
            )
        try:
            bill = parse_equatorial_bill_text(message.text)
            async with SessionFactory() as session:
                plant_id = await _resolve_telegram_plant_scope(session)
                record = await UtilityBillRepository(session).create_pending(
                    bill,
                    plant_id=plant_id,
                    source_text=message.text,
                )
                await session.commit()
                reference_month = record.reference_month
            await client.send_message(message.chat_id, _pending_message(reference_month))
        except BillParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except TelegramClientError as exc:
            raise HTTPException(status_code=502, detail="Telegram acknowledgement failed") from exc
        return {"accepted": True, "kind": "text", "status": "pending_review"}

    assert message.document is not None
    try:
        downloaded = await client.download_file(
            message.document.file_id,
            max_bytes=settings.telegram_document_max_bytes,
        )
        source_text = extract_pdf_text(downloaded.content)
        processed = process_pdf_bill(
            downloaded.content,
            extract_text=lambda _: source_text,
            max_text_bytes=settings.bill_text_max_bytes,
        )
        async with SessionFactory() as session:
            plant_id = await _resolve_telegram_plant_scope(session)
            record = await UtilityBillRepository(session).create_pending(
                processed.bill,
                plant_id=plant_id,
                source_text=source_text,
            )
            await session.commit()
            reference_month = record.reference_month
        await client.send_message(message.chat_id, _pending_message(reference_month))
    except (
        TelegramClientError,
        TelegramDocumentProcessingError,
        PdfTextExtractionError,
        BillParseError,
    ) as exc:
        raise HTTPException(status_code=422, detail="bill PDF could not be processed") from exc

    return {
        "accepted": True,
        "kind": "document",
        "status": "pending_review",
        "reference_month": reference_month,
    }
