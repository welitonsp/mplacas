from __future__ import annotations

from collections.abc import Iterable

from mplacas.explanations.models import (
    DiagnosticEvidence,
    ExplanationRequest,
    ExplanationSource,
    GroundedExplanation,
)
from mplacas.explanations.provider import ExplanationProvider

_DISCLAIMER = (
    "Explicação informativa baseada apenas nos diagnósticos calculados pelo Mplacas; "
    "não confirma causa técnica nem substitui inspeção profissional."
)


def _unique_actions(evidence: Iterable[DiagnosticEvidence], limit: int = 5) -> tuple[str, ...]:
    actions: list[str] = []
    for item in evidence:
        action = item.recommended_action.strip()
        if action and action not in actions:
            actions.append(action)
        if len(actions) == limit:
            break
    return tuple(actions)


def build_deterministic_explanation(request: ExplanationRequest) -> GroundedExplanation:
    request.validate()
    codes = ", ".join(item.code for item in request.evidence)
    explanation = GroundedExplanation(
        source=ExplanationSource.DETERMINISTIC,
        summary=request.headline.strip(),
        what_it_means=(
            f"O estado consolidado é {request.status}. A explicação está limitada às "
            f"evidências registradas: {codes}."
        ),
        next_steps=_unique_actions(request.evidence),
        disclaimer=_DISCLAIMER,
    )
    explanation.validate()
    return explanation


async def explain_with_fallback(
    request: ExplanationRequest,
    *,
    provider: ExplanationProvider | None,
) -> GroundedExplanation:
    """Use AI only as an optional wording layer and always preserve a safe fallback."""
    fallback = build_deterministic_explanation(request)
    if provider is None:
        return fallback

    try:
        result = await provider.explain(request)
        result.validate()
    except Exception:
        return fallback

    return GroundedExplanation(
        source=ExplanationSource.AI_ASSISTED,
        summary=result.summary.strip(),
        what_it_means=result.what_it_means.strip(),
        next_steps=result.next_steps[:5],
        disclaimer=_DISCLAIMER,
    )
