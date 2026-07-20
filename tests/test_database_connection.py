from __future__ import annotations

from pathlib import Path

import pytest

from mplacas.db.connection import (
    database_connect_args,
    normalize_database_url,
    require_postgresql_async_url,
)


def test_normalizes_postgresql_scheme_and_strips_asyncpg_unsupported_params() -> None:
    result = normalize_database_url(
        "postgresql://user:pass@ep-example.neon.tech/neondb"
        "?sslmode=require&channel_binding=require&application_name=mplacas"
    )
    assert result.startswith("postgresql+asyncpg://")
    assert "sslmode" not in result
    assert "channel_binding" not in result
    assert "application_name=mplacas" in result


def test_preserves_sqlite_url() -> None:
    value = "sqlite+aiosqlite:///./mplacas.db"
    assert normalize_database_url(value) == value


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://user:pass@ep-example.neon.tech/neondb",
        "postgresql+asyncpg://user:pass@ep-example-pooler.neon.tech/neondb",
    ],
)
def test_neon_connections_require_ssl(url: str) -> None:
    assert database_connect_args(url) == {"ssl": "require"}


def test_local_postgresql_does_not_force_ssl() -> None:
    assert database_connect_args(
        "postgresql+asyncpg://postgres@localhost:5432/postgres"
    ) == {}


def test_require_postgresql_rejects_sqlite() -> None:
    with pytest.raises(ValueError, match="PostgreSQL|postgresql"):
        require_postgresql_async_url("sqlite:///test.db")


def test_alembic_uses_shared_connection_arguments() -> None:
    source = Path("migrations/env.py").read_text(encoding="utf-8")
    assert "database_connect_args(_database_url)" in source
    assert "poolclass=pool.NullPool" in source
