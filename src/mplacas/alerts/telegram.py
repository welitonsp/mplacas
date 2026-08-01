from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from mplacas.alerts.models import AlertCandidate


@dataclass(frozen=True, slots=True)
class TelegramAlertProvider:
    """Deliver sanitized alerts through the Telegram Bot API."""

    bot_token: str
    chat_id: str
    timeout_seconds: float = 10.0
    api_base_url: str = "https://api.telegram.org"

    def __post_init__(self) -> None:
        if not self.bot_token.strip():
            raise ValueError("bot token cannot be blank")
        if not self.chat_id.strip():
            raise ValueError("chat id cannot be blank")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout must be positive")

    async def send(self, alert: AlertCandidate) -> None:
        alert.validate()
        text = format_telegram_alert(alert)
        await self.send_message(text)

    async def send_message(
        self,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: Mapping[str, Any] | None = None,
    ) -> None:
        """Deliver an arbitrary message, optionally rich (HTML + inline keyboard).

        ``send`` remains the entry point for the existing operational-alert
        path (plain text, no formatting). This method is the lower-level
        primitive shared by alerts and any other message type — e.g. the
        daily digest — that needs ``parse_mode``/``reply_markup`` support.
        """
        url = f"{self.api_base_url.rstrip('/')}/bot{self.bot_token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        timeout = httpx.Timeout(self.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            body = response.json()
        if body.get("ok") is not True:
            raise RuntimeError("telegram delivery was not acknowledged")


def format_telegram_alert(alert: AlertCandidate) -> str:
    """Render a concise plain-text message without exposing secrets or raw payloads."""
    alert.validate()
    severity_icon = {
        "INFO": "ℹ️",
        "WARNING": "⚠️",
        "CRITICAL": "🚨",
    }[alert.severity.value]
    occurred_at = alert.occurred_at.isoformat(timespec="minutes")
    return "\n".join(
        (
            f"{severity_icon} MPLACAS — {alert.severity.value}",
            alert.title.strip(),
            "",
            alert.message.strip(),
            "",
            f"Ação recomendada: {alert.recommended_action.strip()}",
            f"Ocorrência: {occurred_at}",
        )
    )
