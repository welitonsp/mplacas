from __future__ import annotations

import pytest

from mplacas.explanations.models import (
    DiagnosticEvidence,
    ExplanationRequest,
    ExplanationSource,
    GroundedExplanation,
)
from mplacas.explanations.service import build_deterministic_explanation, explain_with_fallback


def _request() -> ExplanationRequest:
    return ExplanationRequest(
        subject="Usina residencial",
        status="ATTENTION",
        headline="Produção abaixo do esperado no período analisado.",
        evidence=(
            DiagnosticEvidence(
                code="LOW_PRODUCTION_NOT_EXPLAINED_BY_LOW_IRRADIATION",
                severity="WARNING",
                message="A produção ficou abaixo do esperado sem baixa irradiação suficiente.",
                recommended_action="Verificar inversor, comunicação e disponibilidade operacional.",
            ),
        ),
    )


def test_build_deterministic_explanation_uses_only_supplied_evidence() -> None:
    result = build_deterministic_explanation(_request())

    assert result.source is ExplanationSource.DETERMINISTIC
    assert "LOW_PRODUCTION_NOT_EXPLAINED_BY_LOW_IRRADIATION" in result.what_it_means
    assert result.next_steps == (
        "Verificar inversor, comunicação e disponibilidade operacional.",
    )
    assert "não confirma causa técnica" in result.disclaimer


class FailingProvider:
    async def explain(self, request: ExplanationRequest) -> GroundedExplanation:
        raise TimeoutError("provider unavailable")


@pytest.mark.asyncio
async def test_provider_failure_returns_deterministic_fallback() -> None:
    result = await explain_with_fallback(_request(), provider=FailingProvider())

    assert result.source is ExplanationSource.DETERMINISTIC
    assert result.summary == _request().headline


class ValidProvider:
    async def explain(self, request: ExplanationRequest) -> GroundedExplanation:
        return GroundedExplanation(
            source=ExplanationSource.AI_ASSISTED,
            summary="O sistema identificou uma queda relevante de produção.",
            what_it_means="Os dados justificam uma verificação, mas não comprovam a causa.",
            next_steps=("Verificar o inversor.",),
            disclaimer="texto que deve ser substituído pelo serviço",
        )


@pytest.mark.asyncio
async def test_valid_provider_output_keeps_fixed_disclaimer() -> None:
    result = await explain_with_fallback(_request(), provider=ValidProvider())

    assert result.source is ExplanationSource.AI_ASSISTED
    assert result.next_steps == ("Verificar o inversor.",)
    assert "não confirma causa técnica" in result.disclaimer


def test_request_rejects_missing_evidence() -> None:
    request = ExplanationRequest(
        subject="Usina",
        status="NORMAL",
        headline="Sem alterações.",
        evidence=(),
    )

    with pytest.raises(ValueError, match="at least one"):
        build_deterministic_explanation(request)
