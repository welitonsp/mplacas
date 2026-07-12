from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status

from mplacas.core.config import get_settings
from mplacas.telegram.service import TelegramUpdateError, parse_authorized_update

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def telegram_webhook(
    payload: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    if not settings.telegram_configured or settings.telegram_webhook_secret is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram is not configured")

    expected = settings.telegram_webhook_secret.get_secret_value()
    if not x_telegram_bot_api_secret_token or not secrets.compare_digest(
        x_telegram_bot_api_secret_token, expected
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")

    try:
        message = parse_authorized_update(
            payload,
            allowed_user_id=settings.telegram_allowed_user_id,
            max_document_bytes=settings.telegram_document_max_bytes,
        )
    except TelegramUpdateError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    if message.kind == "command":
        return {
            "accepted": True,
            "kind": "command",
            "command": message.text,
        }
    if message.kind == "text":
        return {
            "accepted": True,
            "kind": "text",
            "next_action": "submit_bill_text_for_review",
        }

    assert message.document is not None
    return {
        "accepted": True,
        "kind": "document",
        "file_id": message.document.file_id,
        "file_name": message.document.file_name,
        "file_size": message.document.file_size,
        "next_action": "download_extract_and_submit_for_review",
    }
