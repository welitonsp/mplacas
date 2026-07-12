from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


class TelegramUpdateError(ValueError):
    """Falha segura ao validar uma atualização recebida do Telegram."""


@dataclass(frozen=True, slots=True)
class TelegramDocument:
    file_id: str
    file_name: str
    mime_type: str
    file_size: int


@dataclass(frozen=True, slots=True)
class TelegramMessage:
    update_id: int
    user_id: int
    chat_id: int
    chat_type: str
    kind: Literal["command", "text", "document"]
    text: str | None = None
    document: TelegramDocument | None = None


def parse_authorized_update(
    payload: dict[str, Any],
    *,
    allowed_user_id: int,
    max_document_bytes: int,
) -> TelegramMessage:
    """Valida remetente, conversa privada e conteúdo sem confiar no payload externo."""
    try:
        update_id = int(payload["update_id"])
        message = payload["message"]
        user_id = int(message["from"]["id"])
        chat_id = int(message["chat"]["id"])
        chat_type = str(message["chat"]["type"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TelegramUpdateError("invalid Telegram update structure") from exc

    if user_id != allowed_user_id:
        raise TelegramUpdateError("Telegram user is not authorized")
    if chat_type != "private" or chat_id != user_id:
        raise TelegramUpdateError("only private chats are accepted")

    text = message.get("text")
    if isinstance(text, str) and text.strip():
        clean_text = text.strip()
        kind: Literal["command", "text"] = "command" if clean_text.startswith("/") else "text"
        return TelegramMessage(
            update_id=update_id,
            user_id=user_id,
            chat_id=chat_id,
            chat_type=chat_type,
            kind=kind,
            text=clean_text,
        )

    raw_document = message.get("document")
    if not isinstance(raw_document, dict):
        raise TelegramUpdateError("unsupported Telegram message type")

    try:
        file_id = str(raw_document["file_id"])
        file_name = str(raw_document["file_name"])
        mime_type = str(raw_document["mime_type"])
        file_size = int(raw_document["file_size"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TelegramUpdateError("invalid Telegram document metadata") from exc

    if mime_type != "application/pdf" or not file_name.casefold().endswith(".pdf"):
        raise TelegramUpdateError("only PDF bills are accepted")
    if file_size <= 0 or file_size > max_document_bytes:
        raise TelegramUpdateError("Telegram document size is not allowed")

    return TelegramMessage(
        update_id=update_id,
        user_id=user_id,
        chat_id=chat_id,
        chat_type=chat_type,
        kind="document",
        document=TelegramDocument(
            file_id=file_id,
            file_name=file_name,
            mime_type=mime_type,
            file_size=file_size,
        ),
    )
