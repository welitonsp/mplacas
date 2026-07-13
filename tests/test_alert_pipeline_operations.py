from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from mplacas.alerts.candidates import anomaly_alert_candidate, executive_alert_candidate
from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.router import _destination_ref
from mplacas.intelligence.anomaly_engine import (
    AnomalyDiagnostic,
    AnomalyLevel,
    DailyAnomalyAssessment,
)
from mplacas.intelligence.executive_service import ExecutiveStatus


def test_executive_candidate_has_stable_fingerprint_and_action() -> None:
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000021")
    bill_id = uuid.UUID("00000000-0000-0000-0000-000000000120")
    dashboard = SimpleNamespace(
        plant_id=plant_id,
        status=ExecutiveStatus.ATTENTION,
        current_cycle=SimpleNamespace(bill_id=bill_id),
        priority_actions=("Verificar o desempenho do ciclo.",),
        headline="O ciclo requer acompanhamento.",
    )
    occurred_at = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)

    candidate = executive_alert_candidate(dashboard, occurred_at=occurred_at)

    assert candidate.severity is AlertSeverity.WARNING
    assert candidate.fingerprint == f"executive:{plant_id}:{bill_id}:ATTENTION"
    assert candidate.recommended_action == "Verificar o desempenho do ciclo."
    assert candidate.occurred_at == occurred_at


def test_anomaly_candidate_uses_worst_diagnostic_and_streak() -> None:
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000021")
    diagnostic = AnomalyDiagnostic(
        code="LOW_PRODUCTION_NOT_EXPLAINED_BY_LOW_IRRADIATION",
        level=AnomalyLevel.CRITICAL,
        message="A produção ficou abaixo do esperado.",
        recommended_action="Verificar o sistema fotovoltaico.",
    )
    assessment = DailyAnomalyAssessment(
        level=AnomalyLevel.CRITICAL,
        deviation_kwh=Decimal("-8.000"),
        deviation_percent=Decimal("-60.0"),
        climate_context_available=True,
        diagnostics=(diagnostic,),
    )
    summary = SimpleNamespace(
        plant_id=plant_id,
        end_date=date(2026, 7, 13),
        worst_level=AnomalyLevel.CRITICAL,
        current_streak_days=3,
        daily=(SimpleNamespace(assessment=assessment),),
    )

    candidate = anomaly_alert_candidate(summary)

    assert candidate.severity is AlertSeverity.CRITICAL
    assert candidate.fingerprint == f"anomaly:{plant_id}:2026-07-13:CRITICAL:3"
    assert "Sequência atual: 3 dia(s)." in candidate.message
    assert candidate.recommended_action == "Verificar o sistema fotovoltaico."


def test_destination_reference_is_deterministic_and_does_not_expose_chat_id() -> None:
    chat_id = "synthetic-chat-123"

    first = _destination_ref(chat_id)
    second = _destination_ref(chat_id)

    assert first == second
    assert first.startswith("telegram:")
    assert chat_id not in first
