from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


_UNSUPPORTED_ASYNCPG_QUERY_PARAMS = frozenset({"sslmode", "channel_binding"})

# Hosts que não saem da máquina, únicos em que trafegar sem TLS é aceitável.
# Um hostname vazio significa socket Unix, que também não atravessa a rede.
_LOCAL_HOSTNAMES = frozenset({"", "localhost", "127.0.0.1", "::1", "[::1]"})


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
    """Return driver arguments required to reach the target database safely.

    TLS é exigido para qualquer host remoto, não só para um provedor específico.
    A versão anterior desta função casava apenas ``*.neon.tech``, o que fazia
    qualquer outro banco remoto — outro provedor, um endpoint de staging, uma
    URL trocada por engano — conectar em texto claro, silenciosamente. O padrão
    seguro é o inverso: exigir TLS por omissão e abrir exceção só para o que
    comprovadamente não atravessa a rede.
    """
    hostname = (urlsplit(database_url).hostname or "").lower()
    if hostname in _LOCAL_HOSTNAMES:
        return {}
    return {"ssl": "require"}


def require_postgresql_async_url(raw: str) -> str:
    """Normalize *raw* and reject non-PostgreSQL URLs."""
    normalized = normalize_database_url(raw)
    if not normalized.startswith("postgresql+asyncpg://"):
        raise ValueError(
            "database URL must use postgresql://, postgres://, or postgresql+asyncpg://"
        )
    return normalized
