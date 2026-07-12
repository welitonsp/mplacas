import pytest

from mplacas.telegram.service import TelegramUpdateError, parse_authorized_update


def make_payload(*, user_id: int = 123, chat_type: str = "private") -> dict[str, object]:
    return {
        "update_id": 10,
        "message": {
            "from": {"id": user_id},
            "chat": {"id": user_id, "type": chat_type},
            "document": {
                "file_id": "file-1",
                "file_name": "fatura.pdf",
                "mime_type": "application/pdf",
                "file_size": 1024,
            },
        },
    }


def test_accepts_authorized_private_pdf() -> None:
    message = parse_authorized_update(
        make_payload(), allowed_user_id=123, max_document_bytes=2_000
    )
    assert message.kind == "document"
    assert message.document is not None
    assert message.document.file_name == "fatura.pdf"


def test_rejects_unauthorized_user() -> None:
    with pytest.raises(TelegramUpdateError, match="not authorized"):
        parse_authorized_update(
            make_payload(user_id=999), allowed_user_id=123, max_document_bytes=2_000
        )


def test_rejects_group_chat() -> None:
    with pytest.raises(TelegramUpdateError, match="private chats"):
        parse_authorized_update(
            make_payload(chat_type="group"), allowed_user_id=123, max_document_bytes=2_000
        )


def test_rejects_oversized_document() -> None:
    payload = make_payload()
    payload["message"]["document"]["file_size"] = 3_000  # type: ignore[index]
    with pytest.raises(TelegramUpdateError, match="size"):
        parse_authorized_update(payload, allowed_user_id=123, max_document_bytes=2_000)


def test_accepts_text_command() -> None:
    payload = {
        "update_id": 11,
        "message": {
            "from": {"id": 123},
            "chat": {"id": 123, "type": "private"},
            "text": "/status",
        },
    }
    message = parse_authorized_update(payload, allowed_user_id=123, max_document_bytes=2_000)
    assert message.kind == "command"
    assert message.text == "/status"
