from __future__ import annotations

from mplacas.explanations.models import DiagnosticEvidence, ExplanationRequest
from mplacas.intelligence.executive_service import ExecutiveEnergyDashboard


def executive_explanation_request(
    dashboard: ExecutiveEnergyDashboard,
) -> ExplanationRequest:
    evidence = tuple(
        DiagnosticEvidence(
            code=diagnostic.code,
            severity=diagnostic.severity.value,
            message=diagnostic.message,
            recommended_action=diagnostic.recommended_action,
        )
        for diagnostic in dashboard.current_cycle.intelligence.diagnostics
    )
    if not evidence:
        evidence = (
            DiagnosticEvidence(
                code="NO_ACTIVE_DIAGNOSTIC",
                severity="INFO",
                message="Nenhum diagnóstico de atenção ou criticidade foi registrado para o ciclo.",
                recommended_action="Manter o acompanhamento periódico dos indicadores energéticos.",
            ),
        )
    return ExplanationRequest(
        subject=f"Usina {dashboard.plant_id}",
        status=dashboard.status.value,
        headline=dashboard.headline,
        evidence=evidence,
    )
