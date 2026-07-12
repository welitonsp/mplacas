from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from mplacas.alerts.ledger import AlertDeliveryLedger
from mplacas.alerts.models import AlertCandidate, AlertDeliveryStatus, AlertDispatchResult, AlertSeverity
from mplacas.alerts.provider import AlertProvider
from mplacas.alerts.runtime import dispatch_alert_with_ledger


@dataclass(frozen=True, slots=True)
class AlertJobSummary:
    evaluated: int
    sent: int
    skipped: int
    failed: int
    results: tuple[AlertDispatchResult, ...]


async def run_alert_dispatch_job(
    alerts: Iterable[AlertCandidate],
    *,
    provider: AlertProvider,
    ledger: AlertDeliveryLedger,
    minimum_severity: AlertSeverity = AlertSeverity.WARNING,
) -> AlertJobSummary:
    results: list[AlertDispatchResult] = []
    for alert in alerts:
        result = await dispatch_alert_with_ledger(
            alert,
            provider=provider,
            ledger=ledger,
            minimum_severity=minimum_severity,
        )
        results.append(result)

    return AlertJobSummary(
        evaluated=len(results),
        sent=sum(item.status is AlertDeliveryStatus.SENT for item in results),
        skipped=sum(item.status is AlertDeliveryStatus.SKIPPED for item in results),
        failed=sum(item.status is AlertDeliveryStatus.FAILED for item in results),
        results=tuple(results),
    )
