from __future__ import annotations

from typing import Protocol

from mplacas.alerts.models import AlertCandidate


class AlertProvider(Protocol):
    async def send(self, alert: AlertCandidate) -> None:
        """Deliver a sanitized alert without changing its severity or evidence."""
        ...
