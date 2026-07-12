from __future__ import annotations

from typing import Protocol

from mplacas.explanations.models import ExplanationRequest, GroundedExplanation


class ExplanationProvider(Protocol):
    async def explain(self, request: ExplanationRequest) -> GroundedExplanation:
        """Explain only the supplied evidence without recalculating or inventing facts."""
        ...
