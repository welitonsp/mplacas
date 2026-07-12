from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExplanationSource(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    AI_ASSISTED = "AI_ASSISTED"


@dataclass(frozen=True, slots=True)
class DiagnosticEvidence:
    code: str
    severity: str
    message: str
    recommended_action: str

    def validate(self) -> None:
        values = (self.code, self.severity, self.message, self.recommended_action)
        if any(not value.strip() for value in values):
            raise ValueError("diagnostic evidence fields cannot be blank")


@dataclass(frozen=True, slots=True)
class ExplanationRequest:
    subject: str
    status: str
    headline: str
    evidence: tuple[DiagnosticEvidence, ...]

    def validate(self) -> None:
        if not self.subject.strip():
            raise ValueError("subject cannot be blank")
        if not self.status.strip():
            raise ValueError("status cannot be blank")
        if not self.headline.strip():
            raise ValueError("headline cannot be blank")
        if not self.evidence:
            raise ValueError("at least one diagnostic evidence item is required")
        for item in self.evidence:
            item.validate()


@dataclass(frozen=True, slots=True)
class GroundedExplanation:
    source: ExplanationSource
    summary: str
    what_it_means: str
    next_steps: tuple[str, ...]
    disclaimer: str

    def validate(self) -> None:
        if not self.summary.strip():
            raise ValueError("summary cannot be blank")
        if not self.what_it_means.strip():
            raise ValueError("what_it_means cannot be blank")
        if not self.next_steps or any(not item.strip() for item in self.next_steps):
            raise ValueError("next_steps cannot be empty or blank")
        if not self.disclaimer.strip():
            raise ValueError("disclaimer cannot be blank")
