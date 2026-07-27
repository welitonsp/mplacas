from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import Response, status

from mplacas import main


class _ReadySession:
    async def __aenter__(self) -> _ReadySession:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement) -> None:
        return None


def _settings(*, env: str, jwt_configured: bool) -> SimpleNamespace:
    return SimpleNamespace(
        env=env,
        readiness_timeout_seconds=3.0,
        nep_configured=False,
        telegram_configured=False,
        telegram_alerts_configured=False,
        climate_archive_base_url=None,
        pipeline_stale_lock_timeout_minutes=60,
        explanation_provider_configured=False,
        operations_api_key=None,
        jwt_configured=jwt_configured,
        timezone="America/Sao_Paulo",
    )


@pytest.mark.asyncio
async def test_ready_degrades_production_without_jwt(monkeypatch) -> None:
    monkeypatch.setattr(main, "get_settings", lambda: _settings(env="production", jwt_configured=False))
    monkeypatch.setattr(main, "SessionFactory", lambda: _ReadySession())

    response = Response()
    body = await main.ready(response)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert body["status"] == "degraded"
    assert body["database_ready"] is True
    assert body["jwt_auth_configured"] is False
    assert body["production_auth_ready"] is False


@pytest.mark.asyncio
async def test_ready_allows_development_without_jwt(monkeypatch) -> None:
    monkeypatch.setattr(main, "get_settings", lambda: _settings(env="development", jwt_configured=False))
    monkeypatch.setattr(main, "SessionFactory", lambda: _ReadySession())

    response = Response()
    body = await main.ready(response)

    assert response.status_code == status.HTTP_200_OK
    assert body["status"] == "ready"
    assert body["jwt_auth_configured"] is False
    assert body["production_auth_ready"] is True


@pytest.mark.asyncio
async def test_ready_allows_production_with_jwt(monkeypatch) -> None:
    monkeypatch.setattr(main, "get_settings", lambda: _settings(env="production", jwt_configured=True))
    monkeypatch.setattr(main, "SessionFactory", lambda: _ReadySession())

    response = Response()
    body = await main.ready(response)

    assert response.status_code == status.HTTP_200_OK
    assert body["status"] == "ready"
    assert body["jwt_auth_configured"] is True
    assert body["production_auth_ready"] is True
