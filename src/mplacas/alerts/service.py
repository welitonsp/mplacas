from __future__ import annotations

from collections.abc import MutableSet

from mplacas.alerts.models import (
    AlertCandidate,
    AlertDeliveryStatus,
    AlertDispatchResult,
    AlertSeverity,
)
from mplacas.alerts.provider import AlertProvider

_SEVERITY_ORDER = {
    AlertSeverity.INFO: 0,
    AlertSeverity.WARNING: 1,
    AlertSeverity.CRITICAL: 2,
}


async def dispatch_alert(
    alert: AlertCandidate,
    *,
    provider: AlertProvider,
    sent_fingerprints: MutableSet[str],
    minimum_severity: AlertSeverity = AlertSeverity.WARNING,
) -> AlertDispatchResult:
    """Dispatch one alert once, respecting a deterministic minimum severity policy."""
    alert.validate()

    if _SEVERITY_ORDER[alert.severity] < _SEVERITY_ORDER[minimum_severity]:
        return AlertDispatchResult(
            status=AlertDeliveryStatus.SKIPPED,
            fingerprint=alert.fingerprint,
            reason="below minimum severity",
        )

    if alert.fingerprint in sent_fingerprints:
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

    sent_fingerprints.add(alert.fingerprint)
    return AlertDispatchResult(
        status=AlertDeliveryStatus.SENT,
        fingerprint=alert.fingerprint,
        reason="alert delivered",
    )
