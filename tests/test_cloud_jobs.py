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
    assert session.committed is True
    get_settings.cache_clear()


def test_daily_pipeline_help() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["daily-pipeline", "--help"])
    assert exc.value.code == 0
