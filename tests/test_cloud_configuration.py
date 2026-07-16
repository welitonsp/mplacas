from __future__ import annotations

import pytest
from pydantic import ValidationError

from mplacas.core.config import Settings


def test_production_configuration_accepts_postgresql_and_operational_key() -> None:
    settings = Settings(
        _env_file=None,
        env="production",
        database_url="postgresql+asyncpg://user:secret@db.example/mplacas",
        operations_api_key="synthetic-key",
        operations_read_api_key="synthetic-read-key",
        port=8080,
    )

    assert settings.env == "production"
    assert settings.port == 8080
    assert "user:secret" not in repr(settings)
    assert settings.safe_summary()["database_backend"] == "postgresql"
    assert settings.safe_summary()["operational_read_auth_configured"] is True
    assert settings.safe_summary()["external_http_allowed_host_count"] == 2


def test_production_rejects_sqlite() -> None:
    with pytest.raises(ValidationError, match="SQLite is not allowed"):
        Settings(
            _env_file=None,
            env="production",
            database_url="sqlite+aiosqlite:///./mplacas.db",
            operations_api_key="synthetic-key",
        )


def test_production_requires_operational_key() -> None:
    with pytest.raises(ValidationError, match="operational API key"):
        Settings(
            _env_file=None,
            env="production",
            database_url="postgresql+asyncpg://user@db.example/mplacas",
        )


def test_production_rejects_external_host_outside_allowlist() -> None:
    with pytest.raises(ValidationError, match="MPLACAS_CLIMATE_ARCHIVE_BASE_URL"):
        Settings(
            _env_file=None,
            env="production",
            database_url="postgresql+asyncpg://user@db.example/mplacas",
            operations_api_key="synthetic-key",
            climate_archive_base_url="https://unexpected.example/archive",
        )


def test_production_rejects_non_https_external_url() -> None:
    with pytest.raises(ValidationError, match="MPLACAS_EXPLANATION_API_URL"):
        Settings(
            _env_file=None,
            env="production",
            database_url="postgresql+asyncpg://user@db.example/mplacas",
            operations_api_key="synthetic-key",
            external_http_allowed_hosts=(
                "api.nepviewer.net,archive-api.open-meteo.com,explain.example"
            ),
            explanation_api_url="http://explain.example/explain",
        )


def test_production_accepts_allowlisted_explanation_host() -> None:
    settings = Settings(
        _env_file=None,
        env="production",
        database_url="postgresql+asyncpg://user@db.example/mplacas",
        operations_api_key="synthetic-key",
        external_http_allowed_hosts=(
            "api.nepviewer.net,archive-api.open-meteo.com,explain.example"
        ),
        explanation_api_url="https://explain.example/explain",
    )

    assert settings.explanation_provider_configured is True


def test_port_must_be_valid() -> None:
    with pytest.raises(ValidationError, match="PORT"):
        Settings(_env_file=None, port=70000)


def test_development_and_test_allow_sqlite() -> None:
    development = Settings(_env_file=None, env="development")
    test = Settings(_env_file=None, env="test")

    assert development.env == "development"
    assert test.env == "test"
    assert development.safe_summary()["database_backend"] == "sqlite"
