from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertDeliveryStatus(StrEnum):
    SKIPPED = "SKIPPED"
    SENT = "SENT"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class AlertCandidate:
    fingerprint: str
    severity: AlertSeverity
    title: str
    message: str
    recommended_action: str
    occurred_at: datetime

    def validate(self) -> None:
        values = (
            self.fingerprint,
            self.title,
            self.message,
            self.recommended_action,
        )
        if any(not value.strip() for value in values):
            raise ValueError("alert fields cannot be blank")
        if len(self.fingerprint) > 128:
            raise ValueError("alert fingerprint is too long")


@dataclass(frozen=True, slots=True)
class AlertDispatchResult:
    status: AlertDeliveryStatus
    fingerprint: str
    reason: str
