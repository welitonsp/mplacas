from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


_UNSUPPORTED_ASYNCPG_QUERY_PARAMS = frozenset({"sslmode", "channel_binding"})


def normalize_database_url(raw: str) -> str:
    """Normalize database URLs for SQLAlchemy asyncpg without exposing credentials."""
    value = raw.strip()
    if value.startswith("postgres://"):
        value = "postgresql+asyncpg://" + value[len("postgres://") :]
    elif value.startswith("postgresql://"):
        value = "postgresql+asyncpg://" + value[len("postgresql://") :]

    if value.startswith("postgresql+asyncpg://"):
        parts = urlsplit(value)
        params = parse_qs(parts.query, keep_blank_values=True)
        filtered = {
            key: values
            for key, values in params.items()
            if key not in _UNSUPPORTED_ASYNCPG_QUERY_PARAMS
        }
        query = urlencode([(key, item) for key, values in filtered.items() for item in values])
        value = urlunsplit(parts._replace(query=query))

    return value


def database_connect_args(database_url: str) -> dict[str, object]:
    """Return driver arguments required by the target database provider."""
    hostname = (urlsplit(database_url).hostname or "").lower()
    if hostname == "neon.tech" or hostname.endswith(".neon.tech"):
        return {"ssl": "require"}
    return {}


def require_postgresql_async_url(raw: str) -> str:
    """Normalize *raw* and reject non-PostgreSQL URLs."""
    normalized = normalize_database_url(raw)
    if not normalized.startswith("postgresql+asyncpg://"):
        raise ValueError(
            "database URL must use postgresql://, postgres://, or postgresql+asyncpg://"
        )
    return normalized
