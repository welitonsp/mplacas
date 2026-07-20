from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.events.db_models import OutboxEventRecord, OutboxEventStatus


class OutboxEventIntegrityError(ValueError):
    """The persisted event payload does not match its integrity metadata."""


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    id: uuid.UUID
    plant_id: uuid.UUID
    event_type: str
    aggregate_type: str
    aggregate_id: str
    destination_ref: str
    deduplication_key: str
    payload: dict[str, object]
    status: OutboxEventStatus
    attempt_count: int
    available_at: datetime


@dataclass(frozen=True, slots=True)
class EnqueuedOutboxEvent:
    event: OutboxEvent
    created: bool


def _canonical_payload(payload: Mapping[str, object]) -> str:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _payload_sha256(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _to_event(record: OutboxEventRecord) -> OutboxEvent:
    checksum = _payload_sha256(record.payload_json)
    if not hmac.compare_digest(checksum, record.payload_sha256):
        raise OutboxEventIntegrityError("outbox event payload checksum mismatch")
    try:
        payload = json.loads(record.payload_json)
    except json.JSONDecodeError as exc:
        raise OutboxEventIntegrityError("outbox event payload is invalid") from exc
    if not isinstance(payload, dict):
        raise OutboxEventIntegrityError("outbox event payload must be an object")
    return OutboxEvent(
        id=record.id,
        plant_id=record.plant_id,
        event_type=record.event_type,
        aggregate_type=record.aggregate_type,
        aggregate_id=record.aggregate_id,
        destination_ref=record.destination_ref,
        deduplication_key=record.deduplication_key,
        payload=payload,
        status=record.status,
        attempt_count=record.attempt_count,
        available_at=record.available_at,
    )


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        *,
        plant_id: uuid.UUID,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        destination_ref: str,
        deduplication_key: str,
        payload: Mapping[str, object],
    ) -> EnqueuedOutboxEvent:
        event_type = _required(event_type, "event type", 80)
        aggregate_type = _required(aggregate_type, "aggregate type", 80)
        aggregate_id = _required(aggregate_id, "aggregate id", 128)
        destination_ref = _required(destination_ref, "destination reference", 128)
        deduplication_key = _required(deduplication_key, "deduplication key", 255)
        existing = await self.by_deduplication_key(deduplication_key)
        if existing is not None:
            return EnqueuedOutboxEvent(event=existing, created=False)

        payload_json = _canonical_payload(payload)
        record_id = uuid.uuid4()
        values = {
            "id": record_id,
            "plant_id": plant_id,
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "destination_ref": destination_ref,
            "deduplication_key": deduplication_key,
            "payload_json": payload_json,
            "payload_sha256": _payload_sha256(payload_json),
            "status": OutboxEventStatus.PENDING,
            "attempt_count": 0,
        }
        dialect = self._session.sync_session.get_bind().dialect.name
        if dialect == "postgresql":
            statement = (
                postgresql_insert(OutboxEventRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["deduplication_key"])
                .returning(OutboxEventRecord.id)
            )
        elif dialect == "sqlite":
            statement = (
                sqlite_insert(OutboxEventRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["deduplication_key"])
                .returning(OutboxEventRecord.id)
            )
        else:
            raise RuntimeError("transactional outbox requires PostgreSQL or SQLite")
        inserted_id = await self._session.scalar(statement)
        if inserted_id is None:
            concurrent = await self.by_deduplication_key(deduplication_key)
            if concurrent is None:
                raise RuntimeError("outbox conflict did not resolve to an existing event")
            return EnqueuedOutboxEvent(event=concurrent, created=False)
        record = await self._session.get(OutboxEventRecord, inserted_id)
        if record is None:
            raise RuntimeError("inserted outbox event could not be loaded")
        return EnqueuedOutboxEvent(event=_to_event(record), created=True)

    async def by_deduplication_key(self, key: str) -> OutboxEvent | None:
        record = await self._session.scalar(
            select(OutboxEventRecord).where(OutboxEventRecord.deduplication_key == key)
        )
        return _to_event(record) if record is not None else None

    async def by_id(self, event_id: uuid.UUID) -> OutboxEvent | None:
        record = await self._session.get(OutboxEventRecord, event_id)
        return _to_event(record) if record is not None else None

    async def due_ids(
        self,
        *,
        event_type: str,
        destination_ref: str,
        now: datetime | None = None,
        stale_after: timedelta = timedelta(minutes=15),
        limit: int = 100,
    ) -> tuple[uuid.UUID, ...]:
        if limit < 1 or limit > 1000:
            raise ValueError("outbox batch limit must be between 1 and 1000")
        current_time = now or datetime.now(UTC)
        stale_before = current_time - stale_after
        rows = await self._session.scalars(
            select(OutboxEventRecord.id)
            .where(
                OutboxEventRecord.event_type == event_type,
                OutboxEventRecord.destination_ref == destination_ref,
                _claimable(current_time=current_time, stale_before=stale_before),
            )
            .order_by(OutboxEventRecord.created_at, OutboxEventRecord.id)
            .limit(limit)
        )
        return tuple(rows)

    async def claim(
        self,
        event_id: uuid.UUID,
        *,
        now: datetime | None = None,
        stale_after: timedelta = timedelta(minutes=15),
    ) -> OutboxEvent | None:
        current_time = now or datetime.now(UTC)
        record = await self._session.scalar(
            select(OutboxEventRecord)
            .where(
                OutboxEventRecord.id == event_id,
                _claimable(
                    current_time=current_time,
                    stale_before=current_time - stale_after,
                ),
            )
            .with_for_update(skip_locked=True)
        )
        if record is None:
            return None
        record.status = OutboxEventStatus.PROCESSING
        record.locked_at = current_time
        record.last_error_code = None
        await self._session.flush()
        return _to_event(record)

    async def mark_delivered(
        self,
        event_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> None:
        record = await self._required_record(event_id)
        record.status = OutboxEventStatus.DELIVERED
        record.processed_at = now or datetime.now(UTC)
        record.locked_at = None
        record.last_error_code = None
        await self._session.flush()

    async def reschedule(
        self,
        event_id: uuid.UUID,
        *,
        error_code: str,
        now: datetime | None = None,
        max_attempts: int = 10,
    ) -> OutboxEventStatus:
        if max_attempts < 1:
            raise ValueError("outbox max attempts must be positive")
        current_time = now or datetime.now(UTC)
        record = await self._required_record(event_id)
        record.attempt_count += 1
        record.locked_at = None
        record.last_error_code = _required(error_code.upper(), "error code", 80)
        if record.attempt_count >= max_attempts:
            record.status = OutboxEventStatus.FAILED
            record.processed_at = current_time
        else:
            delay_seconds = min(3600, 60 * (2 ** (record.attempt_count - 1)))
            record.status = OutboxEventStatus.PENDING
            record.available_at = current_time + timedelta(seconds=delay_seconds)
        await self._session.flush()
        return record.status

    async def mark_failed(
        self,
        event_id: uuid.UUID,
        *,
        error_code: str,
        now: datetime | None = None,
    ) -> None:
        record = await self._required_record(event_id)
        record.status = OutboxEventStatus.FAILED
        record.processed_at = now or datetime.now(UTC)
        record.locked_at = None
        record.last_error_code = _required(error_code.upper(), "error code", 80)
        await self._session.flush()

    async def _required_record(self, event_id: uuid.UUID) -> OutboxEventRecord:
        record = await self._session.get(OutboxEventRecord, event_id)
        if record is None:
            raise LookupError("outbox event not found")
        return record


def _claimable(*, current_time: datetime, stale_before: datetime):
    return or_(
        and_(
            OutboxEventRecord.status == OutboxEventStatus.PENDING,
            OutboxEventRecord.available_at <= current_time,
        ),
        and_(
            OutboxEventRecord.status == OutboxEventStatus.PROCESSING,
            OutboxEventRecord.locked_at <= stale_before,
        ),
    )


def _required(value: str, label: str, maximum_length: int) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > maximum_length:
        raise ValueError(f"invalid outbox {label}")
    return cleaned
