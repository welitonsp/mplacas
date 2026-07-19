from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from mplacas.core.config import get_settings
from mplacas.main import app
import mplacas.cloud_run as cloud_run
import mplacas.main as main_module


class ReadySession:
    async def __aenter__(self) -> ReadySession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def execute(self, statement) -> int:
        return 1


class FailingSession:
    async def __aenter__(self) -> FailingSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def execute(self, statement) -> None:
        raise RuntimeError("postgresql://user:secret@db/mplacas")


def test_health_is_process_only() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_returns_ready_when_database_responds(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "SessionFactory", lambda: ReadySession())

    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database_ready"] is True
    assert "secret" not in response.text


def test_ready_returns_503_when_database_fails(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "SessionFactory", lambda: FailingSession())

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["database_ready"] is False
    assert "secret" not in response.text
    assert "postgresql://" not in response.text


def test_ready_returns_503_when_configuration_is_invalid(monkeypatch) -> None:
    def invalid_settings():
        raise RuntimeError("postgresql://user:secret@db/mplacas")

    monkeypatch.setattr(main_module, "get_settings", invalid_settings)

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "configuration_valid": False,
        "database_ready": False,
    }
    assert "secret" not in response.text


def test_ready_returns_503_on_timeout(monkeypatch) -> None:
    settings = SimpleNamespace(
        readiness_timeout_seconds=0.01,
        env="test",
        nep_configured=False,
        telegram_configured=False,
        telegram_alerts_configured=False,
        climate_archive_base_url="https://example.invalid",
        pipeline_stale_lock_timeout_minutes=60,
        explanation_provider_configured=False,
        operations_api_key=None,
        timezone="America/Sao_Paulo",
    )

    async def timeout_wait_for(awaitable, *, timeout):
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "SessionFactory", lambda: ReadySession())
    monkeypatch.setattr(main_module.asyncio, "wait_for", timeout_wait_for)

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json()["database_ready"] is False


def test_cloud_run_uses_port_and_host(monkeypatch) -> None:
    monkeypatch.setenv("PORT", "9090")
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    class FakeObservability:
        def shutdown(self) -> None:
            captured["observability_shutdown"] = True

    def fake_observability(**kwargs):
        captured["observability"] = kwargs
        return FakeObservability()

    def fake_run(*args, **kwargs) -> None:
        captured["args"] = args
        captured.update(kwargs)

    monkeypatch.setattr(cloud_run.uvicorn, "run", fake_run)
    monkeypatch.setattr(cloud_run, "configure_observability", fake_observability)

    assert cloud_run.main() == 0
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9090
    assert captured["proxy_headers"] is True
    assert captured["access_log"] is False
    assert captured["log_config"] is None
    assert captured["observability_shutdown"] is True
    get_settings.cache_clear()
