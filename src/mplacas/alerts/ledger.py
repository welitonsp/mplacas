from __future__ import annotations

from typing import Protocol


class AlertDeliveryLedger(Protocol):
    async def was_sent(self, fingerprint: str) -> bool:
        """Return whether a delivery was already confirmed for the fingerprint."""
        ...

    async def mark_sent(self, fingerprint: str) -> None:
        """Persist a confirmed delivery after the provider acknowledges it."""
        ...


class InMemoryAlertDeliveryLedger:
    """Small deterministic implementation for tests and single-process development."""

    def __init__(self) -> None:
        self._sent: set[str] = set()

    async def was_sent(self, fingerprint: str) -> bool:
        return fingerprint in self._sent

    async def mark_sent(self, fingerprint: str) -> None:
        if not fingerprint.strip():
            raise ValueError("fingerprint cannot be blank")
        self._sent.add(fingerprint)
