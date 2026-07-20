from __future__ import annotations

from mplacas.alerts.ledger import AlertDeliveryLedger
from mplacas.alerts.models import (
    SEVERITY_ORDER as _SEVERITY_ORDER,
    AlertCandidate,
    AlertDeliveryStatus,
    AlertDispatchResult,
    AlertSeverity,
)
from mplacas.alerts.provider import AlertProvider


async def dispatch_alert_with_ledger(
    alert: AlertCandidate,
    *,
    provider: AlertProvider,
    ledger: AlertDeliveryLedger,
    minimum_severity: AlertSeverity = AlertSeverity.WARNING,
) -> AlertDispatchResult:
    """Deliver once and persist deduplication only after provider acknowledgement."""
    alert.validate()

    if _SEVERITY_ORDER[alert.severity] < _SEVERITY_ORDER[minimum_severity]:
        return AlertDispatchResult(
            status=AlertDeliveryStatus.SKIPPED,
            fingerprint=alert.fingerprint,
            reason="below minimum severity",
        )

    if await ledger.was_sent(alert.fingerprint):
        return AlertDispatchResult(
            status=AlertDeliveryStatus.SKIPPED,
            fingerprint=alert.fingerprint,
            reason="duplicate alert",
        )

    try:
        await provider.send(alert)
    except Exception:
        return AlertDispatchResult(
            status=AlertDeliveryStatus.FAILED,
            fingerprint=alert.fingerprint,
            reason="provider delivery failed",
        )

    await ledger.mark_sent(alert.fingerprint)
    return AlertDispatchResult(
        status=AlertDeliveryStatus.SENT,
        fingerprint=alert.fingerprint,
        reason="alert delivered",
    )
