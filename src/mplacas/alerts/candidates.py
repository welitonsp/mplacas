from __future__ import annotations

from datetime import UTC, datetime, time

from mplacas.alerts.models import AlertCandidate, AlertSeverity
from mplacas.intelligence.anomaly_engine import AnomalyLevel
from mplacas.intelligence.anomaly_service import PersistedAnomalySummary
from mplacas.intelligence.executive_service import ExecutiveEnergyDashboard, ExecutiveStatus


def _executive_severity(status: ExecutiveStatus) -> AlertSeverity:
    return {
        ExecutiveStatus.HEALTHY: AlertSeverity.INFO,
        ExecutiveStatus.ATTENTION: AlertSeverity.WARNING,
        ExecutiveStatus.CRITICAL: AlertSeverity.CRITICAL,
    }[status]


def _anomaly_severity(level: AnomalyLevel) -> AlertSeverity:
    return {
        AnomalyLevel.NORMAL: AlertSeverity.INFO,
        AnomalyLevel.ATTENTION: AlertSeverity.WARNING,
        AnomalyLevel.ANOMALY: AlertSeverity.WARNING,
        AnomalyLevel.CRITICAL: AlertSeverity.CRITICAL,
    }[level]


def executive_alert_candidate(dashboard: ExecutiveEnergyDashboard) -> AlertCandidate:
    reference = dashboard.current_cycle.reference_month
    action = dashboard.priority_actions[0] if dashboard.priority_actions else (
        "Manter o acompanhamento dos indicadores energéticos."
    )
    return AlertCandidate(
        fingerprint=(
            f"executive:{dashboard.plant_id}:{reference}:{dashboard.status.value}"
        ),
        severity=_executive_severity(dashboard.status),
        title=f"Situação energética do ciclo {reference}",
        message=dashboard.headline,
        recommended_action=action,
        occurred_at=datetime.now(UTC),
    )


def anomaly_alert_candidate(summary: PersistedAnomalySummary) -> AlertCandidate:
    latest = summary.daily[-1]
    diagnostics = latest.assessment.diagnostics
    diagnostic = diagnostics[0] if diagnostics else None
    message = (
        diagnostic.message
        if diagnostic is not None
        else f"Nível consolidado de anomalia: {summary.worst_level.value}."
    )
    action = (
        diagnostic.recommended_action
        if diagnostic is not None
        else "Revisar os dados recentes e a disponibilidade operacional do sistema."
    )
    return AlertCandidate(
        fingerprint=(
            f"anomaly:{summary.plant_id}:{summary.end_date.isoformat()}:"
            f"{summary.worst_level.value}"
        ),
        severity=_anomaly_severity(summary.worst_level),
        title=f"Análise de produção solar — {summary.worst_level.value}",
        message=(
            f"{message} Sequência atual de dias anormais: "
            f"{summary.current_streak_days}."
        ),
        recommended_action=action,
        occurred_at=datetime.combine(summary.end_date, time.min, tzinfo=UTC),
    )
