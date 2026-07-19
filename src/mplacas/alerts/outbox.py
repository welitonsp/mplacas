from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.alerts.job import AlertJobSummary
from mplacas.alerts.models import (
    AlertCandidate,
    AlertDeliveryStatus,
    AlertDispatchResult,
    AlertSeverity,
)
from mplacas.alerts.provider import AlertProvider
from mplacas.alerts.sql_ledger import SqlAlertDeliveryLedger
from mplacas.events.db_models import OutboxEventStatus
from mplacas.events.outbox import OutboxEvent, OutboxEventIntegrityError, OutboxRepository

ALERT_DELIVERY_EVENT = "alert.delivery.requested"

_SEVERITY_ORDER = {
    AlertSeverity.INFO: 0,
    AlertSeverity.WARNING: 1,
    AlertSeverity.CRITICAL: 2,
}


@dataclass(frozen=True, slots=True)
class AlertOutboxItem:
    fingerprint: str
    event_id: uuid.UUID | None
    immediate_result: AlertDispatchResult | None


@dataclass(frozen=True, slots=True)
class AlertOutboxBatch:
    items: tuple[AlertOutboxItem, ...]


async def enqueue_alert_candidates(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    alerts: tuple[AlertCandidate, ...],
    provider: str,
    destination_ref: str,
    minimum_severity: AlertSeverity = AlertSeverity.WARNING,
) -> AlertOutboxBatch:
    provider_name = provider.strip().lower()
    if provider_name != "telegram":
        raise ValueError("unsupported alert outbox provider")
    repository = OutboxRepository(session)
    items: list[AlertOutboxItem] = []
    for alert in alerts:
        alert.validate()
        if _SEVERITY_ORDER[alert.severity] < _SEVERITY_ORDER[minimum_severity]:
            items.append(
                AlertOutboxItem(
                    fingerprint=alert.fingerprint,
                    event_id=None,
                    immediate_result=_result(
                        alert.fingerprint,
                        AlertDeliveryStatus.SKIPPED,
                        "below minimum severity",
                    ),
                )
            )
            continue
        enqueued = await repository.enqueue(
            plant_id=plant_id,
            event_type=ALERT_DELIVERY_EVENT,
            aggregate_type="alert",
            aggregate_id=alert.fingerprint,
            destination_ref=destination_ref,
            deduplication_key=(
                f"alert:{provider_name}:{destination_ref.strip()}:{alert.fingerprint}"
            ),
            payload={
                "plant_id": str(plant_id),
                "fingerprint": alert.fingerprint,
                "severity": alert.severity.value,
                "title": alert.title,
                "message": alert.message,
                "recommended_action": alert.recommended_action,
                "occurred_at": alert.occurred_at.isoformat(),
                "provider": provider_name,
                "destination_ref": destination_ref.strip(),
            },
        )
        event = enqueued.event
        immediate: AlertDispatchResult | None = None
        event_id: uuid.UUID | None = event.id
        if event.status is OutboxEventStatus.DELIVERED:
            event_id = None
            immediate = _result(
                alert.fingerprint,
                AlertDeliveryStatus.SKIPPED,
                "duplicate alert",
            )
        elif event.status is OutboxEventStatus.FAILED:
            event_id = None
            immediate = _result(
                alert.fingerprint,
                AlertDeliveryStatus.FAILED,
                "outbox retry exhausted",
            )
        items.append(
            AlertOutboxItem(
                fingerprint=alert.fingerprint,
                event_id=event_id,
                immediate_result=immediate,
            )
        )
    return AlertOutboxBatch(items=tuple(items))


async def dispatch_alert_outbox_batch(
    session: AsyncSession,
    *,
    batch: AlertOutboxBatch,
    provider: AlertProvider,
    destination_ref: str,
    max_attempts: int = 10,
) -> AlertJobSummary:
    results: list[AlertDispatchResult] = []
    for item in batch.items:
        if item.immediate_result is not None:
            results.append(item.immediate_result)
        elif item.event_id is not None:
            results.append(
                await _dispatch_event(
                    session,
                    event_id=item.event_id,
                    provider=provider,
                    destination_ref=destination_ref,
                    max_attempts=max_attempts,
                )
            )
    return _summary(results)


async def dispatch_due_alert_outbox(
    session: AsyncSession,
    *,
    provider: AlertProvider,
    destination_ref: str,
    limit: int = 100,
    max_attempts: int = 10,
    stale_after: timedelta = timedelta(minutes=15),
) -> AlertJobSummary:
    repository = OutboxRepository(session)
    event_ids = await repository.due_ids(
        event_type=ALERT_DELIVERY_EVENT,
        destination_ref=destination_ref,
        stale_after=stale_after,
        limit=limit,
    )
    results = [
        await _dispatch_event(
            session,
            event_id=event_id,
            provider=provider,
            destination_ref=destination_ref,
            max_attempts=max_attempts,
            stale_after=stale_after,
        )
        for event_id in event_ids
    ]
    return _summary(results)


async def _dispatch_event(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    provider: AlertProvider,
    destination_ref: str,
    max_attempts: int,
    stale_after: timedelta = timedelta(minutes=15),
) -> AlertDispatchResult:
    repository = OutboxRepository(session)
    try:
        event = await repository.claim(event_id, stale_after=stale_after)
    except OutboxEventIntegrityError:
        await repository.mark_failed(event_id, error_code="PAYLOAD_INTEGRITY_ERROR")
        await session.commit()
        return _result(str(event_id), AlertDeliveryStatus.FAILED, "invalid outbox payload")
    if event is None:
        current = await repository.by_id(event_id)
        if current is None:
            return _result(str(event_id), AlertDeliveryStatus.FAILED, "outbox event not found")
        if current.status is OutboxEventStatus.DELIVERED:
            return _result(current.aggregate_id, AlertDeliveryStatus.SKIPPED, "duplicate alert")
        if current.status is OutboxEventStatus.FAILED:
            return _result(
                current.aggregate_id,
                AlertDeliveryStatus.FAILED,
                "outbox retry exhausted",
            )
        return _result(current.aggregate_id, AlertDeliveryStatus.SKIPPED, "alert already queued")

    await session.commit()
    try:
        alert = _deserialize_alert(event, destination_ref=destination_ref)
    except (TypeError, ValueError):
        await repository.mark_failed(event.id, error_code="INVALID_ALERT_PAYLOAD")
        await session.commit()
        return _result(event.aggregate_id, AlertDeliveryStatus.FAILED, "invalid outbox payload")

    ledger = SqlAlertDeliveryLedger(
        session,
        provider="telegram",
        destination_ref=destination_ref,
    )
    if await ledger.was_sent(alert.fingerprint):
        await repository.mark_delivered(event.id)
        await session.commit()
        return _result(alert.fingerprint, AlertDeliveryStatus.SKIPPED, "duplicate alert")

    try:
        await provider.send(alert)
    except Exception as exc:
        error_code = type(exc).__name__.upper()[:80] or "PROVIDER_ERROR"
        await repository.reschedule(
            event.id,
            error_code=error_code,
            max_attempts=max_attempts,
        )
        await session.commit()
        return _result(
            alert.fingerprint,
            AlertDeliveryStatus.FAILED,
            "provider delivery failed",
        )

    await ledger.mark_sent(alert.fingerprint)
    await repository.mark_delivered(event.id)
    await session.commit()
    return _result(alert.fingerprint, AlertDeliveryStatus.SENT, "alert delivered")


def _deserialize_alert(event: OutboxEvent, *, destination_ref: str) -> AlertCandidate:
    payload = event.payload
    if event.event_type != ALERT_DELIVERY_EVENT or event.aggregate_type != "alert":
        raise ValueError("unsupported outbox event type")
    if (
        event.destination_ref != destination_ref
        or _text(payload, "destination_ref") != destination_ref
    ):
        raise ValueError("outbox destination mismatch")
    if _text(payload, "provider") != "telegram":
        raise ValueError("outbox provider mismatch")
    if uuid.UUID(_text(payload, "plant_id")) != event.plant_id:
        raise ValueError("outbox plant mismatch")
    fingerprint = _text(payload, "fingerprint")
    if fingerprint != event.aggregate_id:
        raise ValueError("outbox aggregate mismatch")
    alert = AlertCandidate(
        fingerprint=fingerprint,
        severity=AlertSeverity(_text(payload, "severity")),
        title=_text(payload, "title"),
        message=_text(payload, "message"),
        recommended_action=_text(payload, "recommended_action"),
        occurred_at=datetime.fromisoformat(_text(payload, "occurred_at")),
    )
    alert.validate()
    return alert


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"outbox field {key} must be a non-empty string")
    return value


def _result(
    fingerprint: str,
    status: AlertDeliveryStatus,
    reason: str,
) -> AlertDispatchResult:
    return AlertDispatchResult(status=status, fingerprint=fingerprint, reason=reason)


def _summary(results: list[AlertDispatchResult]) -> AlertJobSummary:
    return AlertJobSummary(
        evaluated=len(results),
        sent=sum(item.status is AlertDeliveryStatus.SENT for item in results),
        skipped=sum(item.status is AlertDeliveryStatus.SKIPPED for item in results),
        failed=sum(item.status is AlertDeliveryStatus.FAILED for item in results),
        results=tuple(results),
    )
