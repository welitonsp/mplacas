"""HTTP layer for the Telegram webhook.

Owns the webhook secret check, settings, session/tenant context, the Telegram
client, PDF extraction and status codes. Database work (organization and user
resolution, plant commands, pending-bill registration) lives in
``telegram.bot_service``; payload validation in ``telegram.service``.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status

from mplacas.billing.parser import BillParseError, parse_equatorial_bill_text
from mplacas.core.config import get_settings
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_platform_context, set_tenant_context
from mplacas.telegram.bot_service import (
    TelegramBotService,
    UnlinkedTelegramChatError,
    pending_bill_message,
)
from mplacas.telegram.client import TelegramClient, TelegramClientError
from mplacas.telegram.document_processing import (
    TelegramDocumentProcessingError,
    process_pdf_bill,
)
from mplacas.telegram.pdf import PdfTextExtractionError, extract_pdf_text_isolated
from mplacas.telegram.service import (
    TelegramUpdateError,
    extract_chat_id,
    parse_authorized_update,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def telegram_webhook(
    payload: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    if settings.telegram_bot_token is None or settings.telegram_webhook_secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram is not configured",
        )

    expected = settings.telegram_webhook_secret.get_secret_value()
    if not x_telegram_bot_api_secret_token or not secrets.compare_digest(
        x_telegram_bot_api_secret_token, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )

    # Authorization is organization-scoped since the telegram_allowed_user_id
    # column was added: which user is allowed to talk to this bot depends on
    # which organization the incoming chat belongs to (resolved from
    # `telegram_chat_id`), not on a single process-wide setting. So we must
    # resolve the organization *before* validating the sender.
    try:
        chat_id = extract_chat_id(payload)
    except TelegramUpdateError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    async with SessionFactory() as session:
        await set_platform_context(session)
        bot = TelegramBotService(session)
        try:
            organization_id = await bot.resolve_organization(chat_id)
        except UnlinkedTelegramChatError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Telegram chat is not linked to any organization",
            ) from None
        await set_tenant_context(session, organization_id)
        allowed_user_id = await bot.allowed_user_id(organization_id)

    if allowed_user_id is None:
        # Fail closed: an organization without its own configured
        # telegram_allowed_user_id is rejected outright. We deliberately do
        # NOT fall back to the process-wide MPLACAS_TELEGRAM_ALLOWED_USER_ID
        # setting here — doing so would silently re-authorize that single
        # global user for every organization missing its own value, which is
        # exactly the cross-tenant bypass this column exists to close. The
        # global setting is only ever used as a one-time deploy-time backfill
        # (see migration 20260731_0027), never as a runtime fallback.
        if settings.telegram_allowed_user_id is not None:
            logger.warning(
                "telegram_organization_missing_allowed_user_id",
                extra={
                    "organization_id": str(organization_id),
                    "hint": (
                        "MPLACAS_TELEGRAM_ALLOWED_USER_ID is set but is not "
                        "used as a fallback for this organization; configure "
                        "telegram_allowed_user_id directly on the "
                        "organization row"
                    ),
                },
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Telegram is not configured for this organization",
        )

    try:
        message = parse_authorized_update(
            payload,
            allowed_user_id=allowed_user_id,
            max_document_bytes=settings.telegram_document_max_bytes,
        )
    except TelegramUpdateError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    client = TelegramClient(
        bot_token=settings.telegram_bot_token.get_secret_value(),
        timeout_seconds=settings.request_timeout_seconds,
    )

    if message.kind == "command":
        async with SessionFactory() as session:
            await set_tenant_context(session, organization_id)
            reply_text = await TelegramBotService(session).handle_command(
                organization_id, message.text or ""
            )
            await session.commit()
        try:
            await client.send_message(message.chat_id, reply_text)
        except TelegramClientError as exc:
            raise HTTPException(
                status_code=502, detail="Telegram acknowledgement failed"
            ) from exc
        return {
            "accepted": True,
            "kind": "command",
            "command": message.text,
        }

    if message.kind == "text":
        if message.text is None:
            raise HTTPException(status_code=422, detail="text message has no content")
        if len(message.text.encode("utf-8")) > settings.bill_text_max_bytes:
            raise HTTPException(
                status_code=413,
                detail="bill text exceeds configured size limit",
            )
        try:
            bill = parse_equatorial_bill_text(message.text)
            async with SessionFactory() as session:
                await set_tenant_context(session, organization_id)
                receipt = await TelegramBotService(session).register_pending_bill(
                    organization_id, bill, source_text=message.text
                )
                await session.commit()
            await client.send_message(
                message.chat_id,
                pending_bill_message(receipt.reference_month, receipt.plant_name),
            )
        except BillParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except TelegramClientError as exc:
            raise HTTPException(status_code=502, detail="Telegram acknowledgement failed") from exc
        return {"accepted": True, "kind": "text", "status": "pending_review"}

    if message.document is None:
        raise HTTPException(status_code=422, detail="document message has no file attached")
    try:
        downloaded = await client.download_file(
            message.document.file_id,
            max_bytes=settings.telegram_document_max_bytes,
        )
        source_text = await extract_pdf_text_isolated(
            downloaded.content,
            max_pages=settings.telegram_pdf_max_pages,
            max_text_bytes=settings.bill_text_max_bytes,
            timeout_seconds=settings.telegram_pdf_parse_timeout_seconds,
            cpu_seconds=settings.telegram_pdf_parse_cpu_seconds,
            memory_bytes=settings.telegram_pdf_parse_memory_bytes,
        )
        processed = process_pdf_bill(
            downloaded.content,
            extract_text=lambda _: source_text,
            max_text_bytes=settings.bill_text_max_bytes,
        )
        async with SessionFactory() as session:
            await set_tenant_context(session, organization_id)
            receipt = await TelegramBotService(session).register_pending_bill(
                organization_id, processed.bill, source_text=source_text
            )
            await session.commit()
        reference_month = receipt.reference_month
        await client.send_message(
            message.chat_id,
            pending_bill_message(reference_month, receipt.plant_name),
        )
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
