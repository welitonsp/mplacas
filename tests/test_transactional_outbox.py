from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.alerts.db_models import AlertDeliveryRecord
from mplacas.alerts.models import AlertCandidate, AlertSeverity
from mplacas.alerts.outbox import (
    dispatch_alert_outbox_batch,
    dispatch_due_alert_outbox,
    enqueue_alert_candidates,
)
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.events.db_models import OutboxEventRecord, OutboxEventStatus
from mplacas.events.outbox import OutboxRepository


class RecordingProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.fingerprints: list[str] = []

    async def send(self, alert: AlertCandidate) -> None:
        self.fingerprints.append(alert.fingerprint)
        if self.fail:
            raise RuntimeError("synthetic provider failure")


class CommitObservingProvider(RecordingProvider):
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        event_id: uuid.UUID,
    ) -> None:
        super().__init__()
        self._factory = factory
        self._event_id = event_id

    async def send(self, alert: AlertCandidate) -> None:
        async with self._factory() as observer:
            record = await observer.get(OutboxEventRecord, self._event_id)
            assert record is not None
            assert record.status is OutboxEventStatus.PROCESSING
        await super().send(alert)


def _alert(fingerprint: str = "outbox-alert-1") -> AlertCandidate:
    return AlertCandidate(
        fingerprint=fingerprint,
        severity=AlertSeverity.WARNING,
        title="Alerta energético",
        message="Produção abaixo do esperado.",
        recommended_action="Verificar o sistema fotovoltaico.",
        occurred_at=datetime(2026, 7, 19, 12, 0, tzinfo=UTC),
    )


async def _database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        plant = Plant(name="Outbox plant")
        session.add(plant)
        await session.commit()
    return engine, factory, plant.id


@pytest.mark.asyncio
async def test_outbox_enqueue_is_atomic_idempotent_and_committed_before_delivery() -> None:
    engine, factory, plant_id = await _database()
    destination_ref = "telegram:synthetic"

    async with factory() as session:
        rolled_back = await enqueue_alert_candidates(
            session,
            plant_id=plant_id,
            alerts=(_alert(),),
            provider="telegram",
            destination_ref=destination_ref,
        )
        assert rolled_back.items[0].event_id is not None
        await session.rollback()

    async with factory() as session:
        count = await session.scalar(select(func.count(OutboxEventRecord.id)))
        assert count == 0
        batch = await enqueue_alert_candidates(
            session,
            plant_id=plant_id,
            alerts=(_alert(),),
            provider="telegram",
            destination_ref=destination_ref,
        )
        await session.commit()
        event_id = batch.items[0].event_id
        assert event_id is not None
        provider = CommitObservingProvider(factory, event_id=event_id)
        summary = await dispatch_alert_outbox_batch(
            session,
            batch=batch,
            provider=provider,
            destination_ref=destination_ref,
        )

        assert summary.sent == 1
        assert provider.fingerprints == ["outbox-alert-1"]
        record = await session.get(OutboxEventRecord, event_id)
        assert record is not None
        assert record.status is OutboxEventStatus.DELIVERED
        ledger_count = await session.scalar(select(func.count(AlertDeliveryRecord.id)))
        assert ledger_count == 1

        duplicate = await enqueue_alert_candidates(
            session,
            plant_id=plant_id,
            alerts=(_alert(),),
            provider="telegram",
            destination_ref=destination_ref,
        )
        await session.commit()
        duplicate_summary = await dispatch_alert_outbox_batch(
            session,
            batch=duplicate,
            provider=provider,
            destination_ref=destination_ref,
        )
        assert duplicate_summary.skipped == 1
        assert duplicate_summary.results[0].reason == "duplicate alert"
        assert provider.fingerprints == ["outbox-alert-1"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_outbox_failure_uses_backoff_and_can_be_retried() -> None:
    engine, factory, plant_id = await _database()
    destination_ref = "telegram:synthetic"

    async with factory() as session:
        batch = await enqueue_alert_candidates(
            session,
            plant_id=plant_id,
            alerts=(_alert("retry-alert"),),
            provider="telegram",
            destination_ref=destination_ref,
        )
        await session.commit()
        event_id = batch.items[0].event_id
        assert event_id is not None

        failed = await dispatch_alert_outbox_batch(
            session,
            batch=batch,
            provider=RecordingProvider(fail=True),
            destination_ref=destination_ref,
        )
        assert failed.failed == 1
        record = await session.get(OutboxEventRecord, event_id)
        assert record is not None
        assert record.status is OutboxEventStatus.PENDING
        assert record.attempt_count == 1
        assert record.last_error_code == "RUNTIMEERROR"

        not_due = await dispatch_due_alert_outbox(
            session,
            provider=RecordingProvider(),
            destination_ref=destination_ref,
        )
        assert not_due.evaluated == 0

        record.available_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        recovered_provider = RecordingProvider()
        recovered = await dispatch_due_alert_outbox(
            session,
            provider=recovered_provider,
            destination_ref=destination_ref,
        )
        assert recovered.sent == 1
        assert recovered_provider.fingerprints == ["retry-alert"]
        assert record.status is OutboxEventStatus.DELIVERED

        terminal_batch = await enqueue_alert_candidates(
            session,
            plant_id=plant_id,
            alerts=(_alert("terminal-alert"),),
            provider="telegram",
            destination_ref=destination_ref,
        )
        await session.commit()
        terminal = await dispatch_alert_outbox_batch(
            session,
            batch=terminal_batch,
            provider=RecordingProvider(fail=True),
            destination_ref=destination_ref,
            max_attempts=1,
        )
        terminal_id = terminal_batch.items[0].event_id
        assert terminal.failed == 1 and terminal_id is not None
        terminal_record = await session.get(OutboxEventRecord, terminal_id)
        assert terminal_record is not None
        assert terminal_record.status is OutboxEventStatus.FAILED

    await engine.dispose()


@pytest.mark.asyncio
async def test_outbox_recovers_stale_claim_and_rejects_tampered_payload() -> None:
    engine, factory, plant_id = await _database()
    destination_ref = "telegram:synthetic"

    async with factory() as session:
        stale_batch = await enqueue_alert_candidates(
            session,
            plant_id=plant_id,
            alerts=(_alert("stale-alert"),),
            provider="telegram",
            destination_ref=destination_ref,
        )
        tampered_batch = await enqueue_alert_candidates(
            session,
            plant_id=plant_id,
            alerts=(_alert("tampered-alert"),),
            provider="telegram",
            destination_ref=destination_ref,
        )
        await session.commit()
        stale_id = stale_batch.items[0].event_id
        tampered_id = tampered_batch.items[0].event_id
        assert stale_id is not None and tampered_id is not None

        claimed = await OutboxRepository(session).claim(stale_id)
        assert claimed is not None
        await session.commit()
        stale_record = await session.get(OutboxEventRecord, stale_id)
        tampered_record = await session.get(OutboxEventRecord, tampered_id)
        assert stale_record is not None and tampered_record is not None
        stale_record.locked_at = datetime.now(UTC) - timedelta(minutes=20)
        tampered_record.payload_json = tampered_record.payload_json.replace(
            "tampered-alert",
            "changed-alert",
        )
        await session.commit()

        provider = RecordingProvider()
        recovered = await dispatch_due_alert_outbox(
            session,
            provider=provider,
            destination_ref=destination_ref,
            stale_after=timedelta(minutes=15),
        )
        assert recovered.sent == 1
        assert recovered.failed == 1
        assert provider.fingerprints == ["stale-alert"]
        assert stale_record.status is OutboxEventStatus.DELIVERED
        assert tampered_record.status is OutboxEventStatus.FAILED
        assert tampered_record.last_error_code == "PAYLOAD_INTEGRITY_ERROR"

    await engine.dispose()
