from __future__ import annotations

from dataclasses import dataclass

import httpx


class TelegramClientError(RuntimeError):
    """Falha controlada na comunicação com a API do Telegram."""


@dataclass(frozen=True, slots=True)
class DownloadedTelegramFile:
    content: bytes
    file_path: str


class TelegramClient:
    def __init__(self, *, bot_token: str, timeout_seconds: float = 20.0) -> None:
        if not bot_token:
            raise TelegramClientError("Telegram bot token is missing")
        self._timeout = timeout_seconds
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._file_base_url = f"https://api.telegram.org/file/bot{bot_token}"

    async def download_file(self, file_id: str, *, max_bytes: int) -> DownloadedTelegramFile:
        if not file_id or max_bytes <= 0:
            raise TelegramClientError("invalid Telegram file request")

        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
                metadata_response = await client.get(
                    f"{self._base_url}/getFile", params={"file_id": file_id}
                )
                if metadata_response.status_code != 200:
                    raise TelegramClientError("Telegram getFile failed")
                payload = metadata_response.json()
                if payload.get("ok") is not True:
                    raise TelegramClientError("Telegram rejected getFile")
                file_path = payload.get("result", {}).get("file_path")
                if not isinstance(file_path, str) or not file_path:
                    raise TelegramClientError("Telegram file path is missing")

                file_response = await client.get(f"{self._file_base_url}/{file_path}")
                if file_response.status_code != 200:
                    raise TelegramClientError("Telegram file download failed")
                content = file_response.content
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise TelegramClientError("Telegram file request failed") from exc

        if not content or len(content) > max_bytes:
            raise TelegramClientError("Telegram file size is not allowed")
        if not content.startswith(b"%PDF-"):
            raise TelegramClientError("Telegram document is not a valid PDF")
        return DownloadedTelegramFile(content=content, file_path=file_path)

    async def send_message(self, chat_id: int, text: str) -> None:
        if chat_id <= 0 or not text.strip():
            raise TelegramClientError("invalid Telegram message request")
        safe_text = text.strip()[:4_000]
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
                response = await client.post(
                    f"{self._base_url}/sendMessage",
                    json={"chat_id": chat_id, "text": safe_text},
                )
                if response.status_code != 200:
                    raise TelegramClientError("Telegram sendMessage failed")
                payload = response.json()
                if payload.get("ok") is not True:
                    raise TelegramClientError("Telegram rejected sendMessage")
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise TelegramClientError("Telegram message request failed") from exc
