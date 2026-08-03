from __future__ import annotations

import pathlib
import sys
from urllib.parse import parse_qsl, urlsplit


ALLOWED_QUERY_KEYS = frozenset({"sslmode", "channel_binding", "application_name"})


def validate_database_url(value: str, expected: str) -> None:
    if expected not in {"runtime", "migration"}:
        raise ValueError("tipo de endpoint deve ser runtime ou migration")

    canonical = value.strip()
    if not canonical or any(char.isspace() for char in canonical):
        raise ValueError("a connection string contém espaço ou está vazia")

    parsed = urlsplit(canonical)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+asyncpg"}:
        raise ValueError("a connection string deve ser PostgreSQL")
    if not parsed.username or not parsed.password:
        raise ValueError("a connection string deve conter usuário e senha")
    if not parsed.hostname:
        raise ValueError("a connection string não contém hostname")
    if parsed.fragment:
        raise ValueError("a connection string não pode conter fragmento")
    if not parsed.path or parsed.path == "/" or parsed.path.count("/") != 1:
        raise ValueError("a connection string deve conter um único database")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("porta PostgreSQL inválida") from exc

    host = parsed.hostname.lower()
    if not (host == "neon.tech" or host.endswith(".neon.tech")):
        raise ValueError("o endpoint deve pertencer ao Neon")
    is_pooler = "-pooler." in host
    if expected == "runtime" and not is_pooler:
        raise ValueError("database-runtime exige endpoint pooled (-pooler)")
    if expected == "migration" and is_pooler:
        raise ValueError("database-migration exige endpoint direto, sem -pooler")

    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise ValueError("query string PostgreSQL inválida") from exc
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("parâmetro PostgreSQL duplicado")
    if not set(keys).issubset(ALLOWED_QUERY_KEYS):
        raise ValueError("parâmetro PostgreSQL não permitido")
    if any(not key or not item or "://" in item for key, item in pairs):
        raise ValueError("valor de parâmetro PostgreSQL inválido")

    params = dict(pairs)
    if params.get("sslmode") != "require":
        raise ValueError("sslmode=require é obrigatório")
    if params.get("channel_binding") != "require":
        raise ValueError("channel_binding=require é obrigatório")


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("uso: validate_database_url.py ARQUIVO {runtime|migration}")
    value = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
    try:
        validate_database_url(value, sys.argv[2])
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
