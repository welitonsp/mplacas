"""Define a senha do usuário administrador no banco de dados.

Uso:
    MPLACAS_DATABASE_URL=<url> python scripts/set-admin-password.py --username <nome>

A senha é lida interativamente (sem eco) ou via Secret Manager
se MPLACAS_ADMIN_PASSWORD_SECRET estiver definido.

Variáveis de ambiente:
    MPLACAS_DATABASE_URL            DSN do banco (postgresql://, postgres://
                                    ou postgresql+asyncpg://). Obrigatório.
    MPLACAS_ADMIN_PASSWORD_SECRET   Nome de um secret no Secret Manager cujo
                                    conteúdo é a senha em texto puro.
                                    Se não definido, a senha é lida interativamente.
    GOOGLE_CLOUD_PROJECT            Projeto GCP para buscas no Secret Manager.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


# ---------------------------------------------------------------------------
# URL normalization
# ---------------------------------------------------------------------------

def _normalize_database_url(raw: str) -> str:
    """Normalize *raw* to a postgresql+asyncpg:// URL suitable for asyncpg.

    Accepts:
        postgresql://...
        postgres://...
        postgresql+asyncpg://...

    Removes query parameters unsupported by asyncpg:
        sslmode, channel_binding
    """
    url = raw.strip()
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    # Already postgresql+asyncpg:// — leave scheme intact.

    if "postgresql+asyncpg://" not in url:
        raise ValueError(
            "MPLACAS_DATABASE_URL must use postgresql://, postgres://, or "
            "postgresql+asyncpg:// scheme"
        )

    parts = urlsplit(url)
    if "sslmode=" in (parts.query or "") or "channel_binding=" in (parts.query or ""):
        params = {
            k: v
            for k, v in parse_qs(parts.query, keep_blank_values=True).items()
            if k not in ("sslmode", "channel_binding")
        }
        query = urlencode({k: v[0] for k, v in params.items()})
        url = urlunsplit(parts._replace(query=query))

    return url


def _mask_url(url: str) -> str:
    """Return URL with credentials replaced by ***."""
    try:
        parts = urlsplit(url)
        masked = parts._replace(
            netloc=f"***:***@{parts.hostname or ''}:{parts.port or ''}"
            if parts.username
            else parts.netloc
        )
        return urlunsplit(masked)
    except Exception:  # noqa: BLE001
        return "<url-masked>"


# ---------------------------------------------------------------------------
# Password input
# ---------------------------------------------------------------------------

def _read_from_secret_manager(secret_name: str) -> str:
    """Fetch the latest enabled version of *secret_name* from Secret Manager."""
    try:
        from google.cloud import secretmanager  # type: ignore[import-untyped]
    except ImportError:
        print(
            "google-cloud-secret-manager is not installed. "
            "Install it or unset MPLACAS_ADMIN_PASSWORD_SECRET to use interactive input.",
            file=sys.stderr,
        )
        sys.exit(1)

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
    if not project:
        print(
            "GOOGLE_CLOUD_PROJECT must be set when MPLACAS_ADMIN_PASSWORD_SECRET is used.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = secretmanager.SecretManagerServiceClient()
    resource = f"projects/{project}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": resource})
    value = response.payload.data.decode("utf-8").strip()
    if not value:
        print("Secret Manager returned an empty password — aborting.", file=sys.stderr)
        sys.exit(1)
    return value


def _read_password_interactively() -> str:
    password = getpass.getpass("Senha: ")
    if not password:
        print("Senha vazia rejeitada.", file=sys.stderr)
        sys.exit(1)
    if len(password) < 12:
        print("Senha deve ter no mínimo 12 caracteres.", file=sys.stderr)
        sys.exit(1)
    confirm = getpass.getpass("Confirme a senha: ")
    if password != confirm:
        print("As senhas não conferem — abortando.", file=sys.stderr)
        sys.exit(1)
    return password


def _read_password() -> str:
    secret_name = os.environ.get("MPLACAS_ADMIN_PASSWORD_SECRET", "").strip()
    if secret_name:
        print(f"Lendo senha do Secret Manager: {secret_name}", file=sys.stderr)
        password = _read_from_secret_manager(secret_name)
        if len(password) < 12:
            print(
                "Senha do Secret Manager tem menos de 12 caracteres — abortando.",
                file=sys.stderr,
            )
            sys.exit(1)
        return password
    return _read_password_interactively()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Define a senha de um usuário operacional ativo do Mplacas.",
    )
    parser.add_argument(
        "--username",
        required=True,
        help="Nome do usuário operacional a atualizar.",
    )
    args = parser.parse_args()
    username: str = args.username.strip()
    if not username:
        print("--username não pode ser vazio.", file=sys.stderr)
        sys.exit(1)

    raw_url = os.environ.get("MPLACAS_DATABASE_URL", "").strip()
    if not raw_url:
        print(
            "MPLACAS_DATABASE_URL não está definido. "
            "Defina a variável com o DSN do banco antes de executar este script.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        database_url = _normalize_database_url(raw_url)
    except ValueError as exc:
        print(f"URL inválida: {exc}", file=sys.stderr)
        sys.exit(1)

    password = _read_password()

    # Import aqui para que erros de import apareçam após validação dos argumentos.
    from mplacas.auth.password import hash_password

    import asyncio

    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from mplacas.credentials.db_models import OperationalUserRecord

    hostname = urlsplit(database_url).hostname or ""
    connect_args: dict[str, object] = {}
    if "neon.tech" in hostname:
        connect_args["ssl"] = "require"

    async def _run() -> None:
        engine = create_async_engine(
            database_url,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                async with session.begin():
                    result = await session.execute(
                        select(OperationalUserRecord).where(
                            OperationalUserRecord.name == username
                        )
                    )
                    rows = result.scalars().all()

                    if len(rows) == 0:
                        print(f"Usuário '{username}' não encontrado.", file=sys.stderr)
                        sys.exit(1)

                    if len(rows) > 1:
                        print(
                            f"Nome de usuário '{username}' duplicado no banco "
                            f"({len(rows)} registros) — abortando.",
                            file=sys.stderr,
                        )
                        sys.exit(1)

                    user = rows[0]

                    if not user.active:
                        print(
                            f"Usuário '{username}' está inativo — "
                            "recusando atualização de senha.",
                            file=sys.stderr,
                        )
                        sys.exit(1)

                    nonlocal password
                    password_hash = hash_password(password)
                    del password  # Remove referência à senha em texto puro.

                    await session.execute(
                        update(OperationalUserRecord)
                        .where(OperationalUserRecord.id == user.id)
                        .values(password_hash=password_hash)
                    )
        except Exception as exc:
            # Mascarar a URL para não expor credenciais em mensagens de erro.
            masked = _mask_url(database_url)
            print(
                f"Erro de conexão com o banco ({masked}): {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)
        finally:
            await engine.dispose()

    asyncio.run(_run())

    # Confirmar sucesso — nunca imprimir senha ou hash.
    print(f"Senha atualizada para usuário: {username}")


if __name__ == "__main__":
    main()
