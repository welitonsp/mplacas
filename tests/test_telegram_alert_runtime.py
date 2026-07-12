from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mplacas.alerts.ledger import InMemoryAlertDeliveryLedger
from mplacas.alerts.models import AlertCandidate, AlertDeliveryStatus, AlertSeverity
from mplacas.alerts.runtime import dispatch_alert_with_ledger
from mplacas.alerts.telegram import TelegramAlertProvider, format_telegram_alert


def _alert(severity: AlertSeverity = AlertSeverity.WARNING) -> AlertCandidate:
    return AlertCandidate(
        fingerprint="plant-1:LOW_PRODUCTION:2026-07-12",
        severity=severity,
        title="Produção abaixo do esperado",
        message="A geração ficou abaixo da linha de base do período.",
        recommended_action="Verificar disponibilidade e comunicação do inversor.",
        occurred_at=datetime(2026, 7, 12, 12, 30, tzinfo=UTC),
    )


def test_format_telegram_alert_is_plain_and_actionable() -> None:
    text = format_telegram_alert(_alert())

    assert "MPLACAS — WARNING" in text
    assert "Produção abaixo do esperado" in text
    assert "Ação recomendada:" in text
    assert "2026-07-12T12:30+00:00" in text


def test_telegram_provider_rejects_blank_credentials() -> None:
    with pytest.raises(ValueError, match="bot token"):
        TelegramAlertProvider(bot_token=" ", chat_id="123")

    with pytest.raises(ValueError, match="chat id"):
        TelegramAlertProvider(bot_token="token", chat_id=" ")


class SuccessfulProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def send(self, alert: AlertCandidate) -> None:
        self.calls += 1


class FailingProvider:
    async def send(self, alert: AlertCandidate) -> None:
        raise TimeoutError("telegram unavailable")


@pytest.mark.asyncio
async def test_runtime_marks_only_confirmed_delivery_and_skips_duplicate() -> None:
    ledger = InMemoryAlertDeliveryLedger()
    provider = SuccessfulProvider()

    first = await dispatch_alert_with_ledger(_alert(), provider=provider, ledger=ledger)
    second = await dispatch_alert_with_ledger(_alert(), provider=provider, ledger=ledger)

    assert first.status is AlertDeliveryStatus.SENT
    assert second.status is AlertDeliveryStatus.SKIPPED
    assert second.reason == "duplicate alert"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_runtime_allows_retry_after_provider_failure() -> None:
    ledger = InMemoryAlertDeliveryLedger()

    failed = await dispatch_alert_with_ledger(_alert(), provider=FailingProvider(), ledger=ledger)
    recovered_provider = SuccessfulProvider()
    recovered = await dispatch_alert_with_ledger(
        _alert(), provider=recovered_provider, ledger=ledger
    )

    assert failed.status is AlertDeliveryStatus.FAILED
    assert recovered.status is AlertDeliveryStatus.SENT
    assert recovered_provider.calls == 1


@pytest.mark.asyncio
async def test_runtime_respects_minimum_severity_without_calling_provider() -> None:
    ledger = InMemoryAlertDeliveryLedger()
    provider = SuccessfulProvider()

    result = await dispatch_alert_with_ledger(
        _alert(AlertSeverity.INFO),
        provider=provider,
        ledger=ledger,
        minimum_severity=AlertSeverity.WARNING,
    )

    assert result.status is AlertDeliveryStatus.SKIPPED
    assert result.reason == "below minimum severity"
    assert provider.calls == 0
