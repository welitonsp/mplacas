from __future__ import annotations

import uuid
from datetime import UTC, datetime

from mplacas.alerts.models import AlertCandidate, AlertSeverity
from mplacas.intelligence.anomaly_engine import AnomalyLevel
from mplacas.intelligence.anomaly_service import PersistedAnomalySummary

_LEVEL_TO_SEVERITY = {
    AnomalyLevel.NORMAL: AlertSeverity.INFO,
    AnomalyLevel.ATTENTION: AlertSeverity.WARNING,
    AnomalyLevel.ANOMALY: AlertSeverity.WARNING,
    AnomalyLevel.CRITICAL: AlertSeverity.CRITICAL,
}


def anomaly_summary_to_alerts(summary: PersistedAnomalySummary) -> tuple[AlertCandidate, ...]:
    """Project deterministic anomaly diagnostics into sanitized alert candidates."""
    alerts: list[AlertCandidate] = []
    for day in summary.daily:
        if day.assessment.level is AnomalyLevel.NORMAL:
            continue
        occurred_at = datetime.combine(day.observation_date, datetime.min.time(), tzinfo=UTC)
        for diagnostic in day.assessment.diagnostics:
            fingerprint = _fingerprint(summary.plant_id, day.observation_date.isoformat(), diagnostic.code)
            alerts.append(
                AlertCandidate(
                    fingerprint=fingerprint,
                    severity=_LEVEL_TO_SEVERITY[diagnostic.level],
                    title=f"Alerta energético — {diagnostic.level.value}",
                    message=diagnostic.message,
                    recommended_action=diagnostic.recommended_action,
                    occurred_at=occurred_at,
                )
            )
    return tuple(alerts)


def _fingerprint(plant_id: uuid.UUID, observation_date: str, code: str) -> str:
    value = f"{plant_id}:{observation_date}:{code}"
    if len(value) > 128:
        raise ValueError("generated alert fingerprint is too long")
    return value
