from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mplacas.alerts.models import AlertCandidate, AlertDeliveryStatus, AlertSeverity
from mplacas.alerts.service import dispatch_alert


class RecordingProvider:
    def __init__(self) -> None:
        self.sent: list[AlertCandidate] = []

    async def send(self, alert: AlertCandidate) -> None:
        self.sent.append(alert)


class FailingProvider:
    async def send(self, alert: AlertCandidate) -> None:
        raise TimeoutError("provider unavailable")


def _alert(*, severity: AlertSeverity = AlertSeverity.WARNING) -> AlertCandidate:
    return AlertCandidate(
        fingerprint="plant-1:LOW_PRODUCTION:2026-07-12",
        severity=severity,
        title="Atenção na geração solar",
        message="A produção ficou abaixo da faixa esperada.",
        recommended_action="Verificar disponibilidade e comunicação do inversor.",
        occurred_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_dispatches_eligible_alert_once() -> None:
    provider = RecordingProvider()
    ledger: set[str] = set()

    first = await dispatch_alert(_alert(), provider=provider, sent_fingerprints=ledger)
    second = await dispatch_alert(_alert(), provider=provider, sent_fingerprints=ledger)

    assert first.status is AlertDeliveryStatus.SENT
    assert second.status is AlertDeliveryStatus.SKIPPED
    assert second.reason == "duplicate alert"
    assert len(provider.sent) == 1


@pytest.mark.asyncio
async def test_skips_alert_below_minimum_severity() -> None:
    provider = RecordingProvider()

    result = await dispatch_alert(
        _alert(severity=AlertSeverity.INFO),
        provider=provider,
        sent_fingerprints=set(),
        minimum_severity=AlertSeverity.WARNING,
    )

    assert result.status is AlertDeliveryStatus.SKIPPED
    assert provider.sent == []


@pytest.mark.asyncio
async def test_provider_failure_does_not_mark_alert_as_sent() -> None:
    ledger: set[str] = set()

    result = await dispatch_alert(_alert(), provider=FailingProvider(), sent_fingerprints=ledger)

    assert result.status is AlertDeliveryStatus.FAILED
    assert ledger == set()
