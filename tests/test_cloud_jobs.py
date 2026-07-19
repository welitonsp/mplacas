from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from mplacas.cloud_jobs import CommandResult, main, run_migrations
from mplacas.core.config import get_settings
import mplacas.cloud_jobs as cloud_jobs


class FakeSession:
    committed = False
    rolled_back = False

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def test_migrate_job_returns_zero(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_DATABASE_URL", "sqlite+aiosqlite:///./synthetic.db")
    get_settings.cache_clear()
    calls: list[list[str]] = []

    def runner(args, env):
        calls.append(args)
        return CommandResult(returncode=0, stdout="", stderr="")

    assert run_migrations(runner=runner) == 0
    assert calls[0][-2:] == ["upgrade", "head"]
    get_settings.cache_clear()


def test_migrate_cli_returns_nonzero_on_failure(monkeypatch, capsys) -> None:
    monkeypatch.setenv("MPLACAS_DATABASE_URL", "postgresql://user:secret@db/mplacas")
    get_settings.cache_clear()

    def failing_runner(args, env):
        return CommandResult(
            returncode=1,
            stdout="",
            stderr="failed postgresql://user:secret@db/mplacas",
        )

    monkeypatch.setattr(cloud_jobs, "_run_command", failing_runner)

    assert main(["migrate"]) == 1
    captured = capsys.readouterr()
    assert "secret" not in captured.err
    assert "postgresql://" not in captured.err
    get_settings.cache_clear()


def test_daily_pipeline_uses_yesterday_in_configured_timezone(monkeypatch) -> None:
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000031")
    monkeypatch.setenv("MPLACAS_CLOUD_JOB_PLANT_ID", str(plant_id))
    monkeypatch.setenv("MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH", "12.5")
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALERT_CHAT_ID", "synthetic-chat")
    get_settings.cache_clear()
    session = FakeSession()
    captured: dict[str, object] = {}

    async def fake_runtime(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: session)
    monkeypatch.setattr(cloud_jobs, "run_ledger_backed_daily_pipeline", fake_runtime)

    now = datetime.fromisoformat("2026-07-13T00:30:00-03:00")
    cloud_jobs.asyncio.run(cloud_jobs.run_daily_pipeline(target_date=None, now=now))

    assert captured["plant_id"] == plant_id
    assert captured["target_date"].isoformat() == "2026-07-12"
    assert captured["expected_daily_production_kwh"] == Decimal("12.5")
    assert captured["outbox_max_attempts"] == 10
    assert session.committed is True
    get_settings.cache_clear()


def test_daily_pipeline_commits_failed_ledger_state(monkeypatch) -> None:
    plant_id = uuid.UUID("00000000-0000-0000-0000-000000000035")
    monkeypatch.setenv("MPLACAS_CLOUD_JOB_PLANT_ID", str(plant_id))
    monkeypatch.setenv("MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH", "12.5")
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALERT_CHAT_ID", "synthetic-chat")
    get_settings.cache_clear()
    session = FakeSession()

    async def failing_runtime(*args, **kwargs):
        raise RuntimeError("pipeline failed after ledger update")

    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: session)
    monkeypatch.setattr(cloud_jobs, "run_ledger_backed_daily_pipeline", failing_runtime)

    with pytest.raises(RuntimeError, match="pipeline failed"):
        cloud_jobs.asyncio.run(
            cloud_jobs.run_daily_pipeline(
                target_date="2026-07-15",
                now=datetime.fromisoformat("2026-07-16T00:30:00-03:00"),
            )
        )

    assert session.committed is True
    assert session.rolled_back is False
    get_settings.cache_clear()


def test_daily_pipeline_help() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["daily-pipeline", "--help"])
    assert exc.value.code == 0


def test_outbox_dispatch_uses_configured_retry_policy(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALERT_CHAT_ID", "synthetic-chat")
    monkeypatch.setenv("MPLACAS_OUTBOX_DISPATCH_BATCH_SIZE", "25")
    monkeypatch.setenv("MPLACAS_OUTBOX_MAX_ATTEMPTS", "7")
    monkeypatch.setenv("MPLACAS_OUTBOX_STALE_LOCK_TIMEOUT_MINUTES", "9")
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    async def fake_dispatch(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(evaluated=2, sent=2, skipped=0, failed=0)

    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(cloud_jobs, "dispatch_due_alert_outbox", fake_dispatch)

    summary = cloud_jobs.asyncio.run(cloud_jobs.run_outbox_dispatch())

    assert summary.sent == 2
    assert captured["limit"] == 25
    assert captured["max_attempts"] == 7
    assert captured["stale_after"].total_seconds() == 9 * 60
    assert captured["destination_ref"].startswith("telegram:")
    get_settings.cache_clear()


def test_outbox_dispatch_job_fails_when_delivery_is_rescheduled(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_TELEGRAM_BOT_TOKEN", "synthetic-token")
    monkeypatch.setenv("MPLACAS_TELEGRAM_ALERT_CHAT_ID", "synthetic-chat")
    get_settings.cache_clear()

    async def fake_dispatch(*args, **kwargs):
        return SimpleNamespace(evaluated=1, sent=0, skipped=0, failed=1)

    monkeypatch.setattr(cloud_jobs, "SessionFactory", lambda: FakeSession())
    monkeypatch.setattr(cloud_jobs, "dispatch_due_alert_outbox", fake_dispatch)

    with pytest.raises(RuntimeError, match="outbox deliveries failed"):
        cloud_jobs.asyncio.run(cloud_jobs.run_outbox_dispatch())
    get_settings.cache_clear()
