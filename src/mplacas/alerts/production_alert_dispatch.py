"""Delivery boundary for production alerts.

Decision and rendering code deliberately have no provider or ledger side
effects. This module owns the at-most-once delivery sequence so it can evolve
independently from the solar-domain rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from mplacas.alerts.ledger import AlertDeliveryLedger


class ProductionAlertMessage(Protocol):
    @property
    def text(self) -> str: ...

    @property
    def reply_markup(self) -> Mapping[str, Any]: ...

    @property
    def fingerprint(self) -> str: ...


class ProductionAlertProvider(Protocol):
    async def send_message(
        self,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: Mapping[str, Any] | None = None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ProductionAlertDispatchResult:
    sent: bool
    reason: str


async def dispatch_production_alert(
    content: ProductionAlertMessage,
    *,
    provider: ProductionAlertProvider,
    ledger: AlertDeliveryLedger,
) -> ProductionAlertDispatchResult:
    """Deliver once and persist confirmation only after provider success."""
    if await ledger.was_sent(content.fingerprint):
        return ProductionAlertDispatchResult(sent=False, reason="duplicate alert")

    await provider.send_message(
        content.text,
        parse_mode="HTML",
        reply_markup=content.reply_markup,
    )
    await ledger.mark_sent(content.fingerprint)
    return ProductionAlertDispatchResult(sent=True, reason="alert delivered")
