from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.alerts.db_models import AlertDeliveryRecord
from mplacas.alerts.job import run_alert_dispatch_job
from mplacas.alerts.models import AlertCandidate, AlertDeliveryStatus, AlertSeverity
from mplacas.alerts.sql_ledger import SqlAlertDeliveryLedger
from mplacas.db.base import Base


class RecordingProvider:
    def __init__(self) -> None:
        self.fingerprints: list[str] = []

    async def send(self, alert: AlertCandidate) -> None:
        self.fingerprints.append(alert.fingerprint)


def _alert(fingerprint: str, severity: AlertSeverity) -> AlertCandidate:
    return AlertCandidate(
        fingerprint=fingerprint,
        severity=severity,
        title="Alerta energético",
        message="Produção abaixo do esperado.",
        recommended_action="Verificar o sistema fotovoltaico.",
        occurred_at=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_sql_ledger_persists_confirmed_delivery_and_deduplicates() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    provider = RecordingProvider()

    async with session_factory() as session:
        ledger = SqlAlertDeliveryLedger(
            session,
            provider="TELEGRAM",
            destination_ref="test-destination",
        )
        first = await run_alert_dispatch_job(
            [_alert("alert-1", AlertSeverity.WARNING)],
            provider=provider,
            ledger=ledger,
        )
        second = await run_alert_dispatch_job(
            [_alert("alert-1", AlertSeverity.WARNING)],
            provider=provider,
            ledger=ledger,
        )

    assert first.sent == 1
    assert second.skipped == 1
    assert second.results[0].status is AlertDeliveryStatus.SKIPPED
    assert provider.fingerprints == ["alert-1"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_job_reports_sent_skipped_and_failed_counts() -> None:
    class SelectiveProvider:
        async def send(self, alert: AlertCandidate) -> None:
            if alert.fingerprint == "fail":
                raise RuntimeError("delivery error")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        ledger = SqlAlertDeliveryLedger(session, provider="TELEGRAM", destination_ref="test")
        summary = await run_alert_dispatch_job(
            [
                _alert("info", AlertSeverity.INFO),
                _alert("sent", AlertSeverity.WARNING),
                _alert("fail", AlertSeverity.CRITICAL),
            ],
            provider=SelectiveProvider(),
            ledger=ledger,
        )

    assert summary.evaluated == 3
    assert summary.sent == 1
    assert summary.skipped == 1
    assert summary.failed == 1
    await engine.dispose()
