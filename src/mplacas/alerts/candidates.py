from __future__ import annotations

from datetime import UTC, datetime

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


def executive_alert_candidate(
    dashboard: ExecutiveEnergyDashboard,
    *,
    occurred_at: datetime | None = None,
) -> AlertCandidate:
    cycle = dashboard.current_cycle
    action = dashboard.priority_actions[0] if dashboard.priority_actions else (
        "Manter o acompanhamento dos indicadores energéticos."
    )
    return AlertCandidate(
        fingerprint=(
            f"executive:{dashboard.plant_id}:{cycle.bill_id}:{dashboard.status.value}"
        ),
        severity=_executive_severity(dashboard.status),
        title="Diagnóstico executivo de energia",
        message=dashboard.headline,
        recommended_action=action,
        occurred_at=occurred_at or datetime.now(UTC),
    )


def anomaly_alert_candidate(
    summary: PersistedAnomalySummary,
    *,
    occurred_at: datetime | None = None,
) -> AlertCandidate:
    severity_order = {
        AnomalyLevel.NORMAL: 0,
        AnomalyLevel.ATTENTION: 1,
        AnomalyLevel.ANOMALY: 2,
        AnomalyLevel.CRITICAL: 3,
    }
    representative = max(
        summary.daily,
        key=lambda item: severity_order[item.assessment.level],
    )
    diagnostic = representative.assessment.diagnostics[0]
    message = diagnostic.message
    if summary.current_streak_days:
        message = f"{message} Sequência atual: {summary.current_streak_days} dia(s)."
    return AlertCandidate(
        fingerprint=(
            f"anomaly:{summary.plant_id}:{summary.end_date}:"
            f"{summary.worst_level.value}:{summary.current_streak_days}"
        ),
        severity=_anomaly_severity(summary.worst_level),
        title="Análise recente de produção solar",
        message=message,
        recommended_action=diagnostic.recommended_action,
        occurred_at=occurred_at or datetime.now(UTC),
    )


def build_alert_candidates(
    *,
    executive: ExecutiveEnergyDashboard | None,
    anomalies: PersistedAnomalySummary | None,
    occurred_at: datetime | None = None,
) -> tuple[AlertCandidate, ...]:
    candidates: list[AlertCandidate] = []
    if executive is not None:
        candidates.append(executive_alert_candidate(executive, occurred_at=occurred_at))
    if anomalies is not None:
        candidates.append(anomaly_alert_candidate(anomalies, occurred_at=occurred_at))
    return tuple(candidates)
