"""Consultar usuário operacional ou definir sua senha de forma segura.

Uso:
    MPLACAS_DATABASE_URL=<url> python3 scripts/set-admin-password.py --username <nome> --check-user
    MPLACAS_DATABASE_URL=<url> python3 scripts/set-admin-password.py --username <nome>

A senha nunca é aceita por argumento. Ela é lida sem eco ou, opcionalmente,
obtida do Secret Manager quando MPLACAS_ADMIN_PASSWORD_SECRET está definido.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from urllib.parse import urlsplit, urlunsplit

_DATABASE_URL_RE = re.compile(
    r"(?:postgres|postgresql)(?:\+asyncpg)?://[^\s'\"<>]+",
    flags=re.IGNORECASE,
)


def _mask_url(url: str) -> str:
    """Return a URL with credentials and host redacted."""
    try:
        parts = urlsplit(url)
        if not parts.scheme:
            return "<database-url>"
        port = f":{parts.port}" if parts.port is not None else ""
        return urlunsplit(parts._replace(netloc=f"***:***@***{port}"))
    except (TypeError, ValueError):
        return "<database-url>"


def _sanitize_exception_message(exc: Exception, *database_urls: str) -> str:
    """Remove DSNs and parsed credentials from an exception message."""
    message = _DATABASE_URL_RE.sub("<database-url>", str(exc))
    sensitive_values: set[str] = set()
    for database_url in database_urls:
        if not database_url:
            continue
        sensitive_values.add(database_url)
        try:
            parts = urlsplit(database_url)
        except ValueError:
            continue
        for value in (parts.username, parts.password, parts.hostname):
            if value:
                sensitive_values.add(value)

    for value in sorted(sensitive_values, key=len, reverse=True):
        message = message.replace(value, "***")

    message = message.strip()
    return message[:500] if message else "falha sem detalhes públicos"


def _read_from_secret_manager(secret_name: str) -> str:
    """Read the latest enabled password secret without logging its value."""
    try:
        from google.cloud import secretmanager  # type: ignore[import-untyped]
    except ImportError:
        print(
            "google-cloud-secret-manager não está instalado. "
            "Remova MPLACAS_ADMIN_PASSWORD_SECRET para usar o prompt interativo.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
    if not project:
        print(
            "GOOGLE_CLOUD_PROJECT é obrigatório quando MPLACAS_ADMIN_PASSWORD_SECRET é usado.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    client = secretmanager.SecretManagerServiceClient()
    resource = f"projects/{project}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": resource})
    value = response.payload.data.decode("utf-8").strip()
    if not value:
        print("O Secret Manager retornou uma senha vazia.", file=sys.stderr)
        raise SystemExit(1)
    return value


def _validate_password(password: str) -> str:
    if not password:
        print("Senha vazia rejeitada.", file=sys.stderr)
        raise SystemExit(1)
    if len(password) < 12:
        print("Senha deve ter no mínimo 12 caracteres.", file=sys.stderr)
        raise SystemExit(1)
    return password


def _read_password_interactively() -> str:
    password = _validate_password(getpass.getpass("Senha: "))
    confirmation = getpass.getpass("Confirme a senha: ")
    if password != confirmation:
        print("As senhas não conferem.", file=sys.stderr)
        raise SystemExit(1)
    return password


def _read_password() -> str:
    secret_name = os.environ.get("MPLACAS_ADMIN_PASSWORD_SECRET", "").strip()
    if secret_name:
        print(f"Lendo senha do Secret Manager: {secret_name}", file=sys.stderr)
        return _validate_password(_read_from_secret_manager(secret_name))
    return _read_password_interactively()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consulta ou define a senha de um usuário operacional ativo do Mplacas.",
    )
    parser.add_argument("--username", required=True, help="Nome exato do usuário operacional.")
    parser.add_argument(
        "--check-user",
        action="store_true",
        help="Somente confirma que o usuário existe, é único e está ativo.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    username = args.username.strip()
    if not username:
        print("--username não pode ser vazio.", file=sys.stderr)
        raise SystemExit(1)

    raw_url = os.environ.get("MPLACAS_DATABASE_URL", "").strip()
    if not raw_url:
        print("MPLACAS_DATABASE_URL não está definido.", file=sys.stderr)
        raise SystemExit(1)

    from mplacas.db.connection import (
        database_connect_args,
        require_postgresql_async_url,
    )

    try:
        database_url = require_postgresql_async_url(raw_url)
    except ValueError as exc:
        print(f"URL de banco inválida: {exc}", file=sys.stderr)
        raise SystemExit(1) from None

    password: str | None = None
    if not args.check_user:
        password = _read_password()

    import asyncio

    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from mplacas.auth.password import hash_password
    from mplacas.credentials.db_models import OperationalUserRecord

    async def _run() -> None:
        nonlocal password
        engine = create_async_engine(
            database_url,
            connect_args=database_connect_args(database_url),
            pool_pre_ping=True,
        )
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                result = await session.execute(
                    select(OperationalUserRecord).where(OperationalUserRecord.name == username)
                )
                users = result.scalars().all()

                if not users:
                    print(f"Usuário '{username}' não encontrado.", file=sys.stderr)
                    raise SystemExit(1)
                if len(users) > 1:
                    print(
                        f"Nome de usuário '{username}' duplicado ({len(users)} registros).",
                        file=sys.stderr,
                    )
                    raise SystemExit(1)

                user = users[0]
                if not user.active:
                    print(f"Usuário '{username}' está inativo.", file=sys.stderr)
                    raise SystemExit(1)

                if args.check_user:
                    print(f"Usuário '{username}' encontrado, único e ativo.")
                    return

                assert password is not None
                password_hash = hash_password(password)
                password = None
                await session.execute(
                    update(OperationalUserRecord)
                    .where(OperationalUserRecord.id == user.id)
                    .values(password_hash=password_hash)
                )
                await session.commit()
        except SystemExit:
            raise
        except Exception as exc:
            safe_message = _sanitize_exception_message(exc, raw_url, database_url)
            print(
                f"Falha no banco ({type(exc).__name__}): {safe_message}",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
        finally:
            password = None
            await engine.dispose()

    asyncio.run(_run())

    if not args.check_user:
        print(f"Senha atualizada para usuário: {username}")


if __name__ == "__main__":
    main()
