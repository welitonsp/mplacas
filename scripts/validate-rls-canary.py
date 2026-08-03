from __future__ import annotations

import argparse
import asyncio
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

from mplacas.db.connection import database_connect_args, normalize_database_url
from mplacas.db.rls_inventory import RLS_TABLES


_CANARY_PATTERN = re.compile(r"^mplacas_rls_canary_[0-9]{8}_[0-9a-f]{8}$")
_RLS_REVISION_PARENT = "20260802_0039"


def _canary_name() -> str:
    date_stamp = datetime.now(UTC).strftime("%Y%m%d")
    return f"mplacas_rls_canary_{date_stamp}_{secrets.token_hex(4)}"


def _validated_urls(raw_url: str, canary_name: str) -> tuple[URL, URL]:
    if not _CANARY_PATTERN.fullmatch(canary_name):
        raise ValueError("refusing unsafe canary database name")
    normalized = normalize_database_url(raw_url)
    admin_url = make_url(normalized)
    if admin_url.get_backend_name() != "postgresql":
        raise ValueError("RLS canary requires PostgreSQL")
    if admin_url.host is None or "-pooler" in admin_url.host.casefold():
        raise ValueError("RLS canary requires the direct, non-pooled Neon endpoint")
    if admin_url.database == canary_name:
        raise ValueError("admin database and canary database must be different")
    return admin_url, admin_url.set(database=canary_name)


def _engine(url: URL, *, autocommit: bool = False):
    options: dict[str, object] = {
        "pool_size": 1,
        "max_overflow": 0,
        "connect_args": database_connect_args(url.render_as_string(hide_password=False)),
    }
    if autocommit:
        options["isolation_level"] = "AUTOCOMMIT"
    return create_async_engine(url, **options)


async def _create_database(admin_url: URL, canary_name: str) -> None:
    engine = _engine(admin_url, autocommit=True)
    try:
        async with engine.connect() as connection:
            exists = (
                await connection.execute(
                    text("SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = :name)"),
                    {"name": canary_name},
                )
            ).scalar_one()
            if exists:
                raise RuntimeError("generated canary database already exists")
            await connection.execute(
                text(f'CREATE DATABASE "{canary_name}" TEMPLATE template0')
            )
    finally:
        await engine.dispose()


async def _drop_database(admin_url: URL, canary_name: str) -> None:
    if not _CANARY_PATTERN.fullmatch(canary_name):
        raise ValueError("refusing unsafe canary database drop")
    last_error: Exception | None = None
    for attempt in range(1, 4):
        engine = _engine(admin_url, autocommit=True)
        try:
            async with engine.connect() as connection:
                current_database = (
                    await connection.execute(text("SELECT current_database()"))
                ).scalar_one()
                if current_database == canary_name:
                    raise RuntimeError("refusing to drop the connected database")
                await connection.execute(
                    text(f'DROP DATABASE IF EXISTS "{canary_name}" WITH (FORCE)')
                )
                return
        except Exception as exc:  # noqa: BLE001 - cleanup must retry provider failures
            last_error = exc
            if attempt < 3:
                await asyncio.sleep(2 * attempt)
        finally:
            await engine.dispose()
    assert last_error is not None
    raise last_error


async def _rls_state(canary_url: URL) -> tuple[int, int, int]:
    engine = _engine(canary_url)
    try:
        async with engine.connect() as connection:
            enabled = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relname = ANY(:tables) "
                        "AND c.relrowsecurity AND c.relforcerowsecurity"
                    ),
                    {"tables": list(RLS_TABLES)},
                )
            ).scalar_one()
            policies = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM pg_policies "
                        "WHERE schemaname = 'public' "
                        "AND policyname = 'mplacas_rls_isolation'"
                    )
                )
            ).scalar_one()
            functions = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM pg_proc p "
                        "JOIN pg_namespace n ON n.oid = p.pronamespace "
                        "WHERE n.nspname = 'public' AND p.proname IN "
                        "('mplacas_current_organization_id', "
                        "'mplacas_platform_bypass_allowed')"
                    )
                )
            ).scalar_one()
            return int(enabled), int(policies), int(functions)
    finally:
        await engine.dispose()


async def _application_table_count(canary_url: URL) -> int:
    engine = _engine(canary_url)
    try:
        async with engine.connect() as connection:
            return int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM pg_class c "
                            "JOIN pg_namespace n ON n.oid = c.relnamespace "
                            "WHERE n.nspname = 'public' AND c.relname = ANY(:tables) "
                            "AND c.relkind = 'r'"
                        ),
                        {"tables": list(RLS_TABLES)},
                    )
                ).scalar_one()
            )
    finally:
        await engine.dispose()


def _run(args: list[str], env: dict[str, str], *, attempts: int = 1) -> None:
    safe_command = " ".join(args)
    print(f"canary_command={safe_command}", flush=True)
    for attempt in range(1, attempts + 1):
        try:
            subprocess.run(args, check=True, env=env)
            return
        except subprocess.CalledProcessError:
            if attempt >= attempts:
                raise
            print(f"canary_command_retry={attempt}", flush=True)
            time.sleep(3 * attempt)


def _assert_rls_state(canary_url: URL, expected: tuple[int, int, int]) -> None:
    actual = asyncio.run(_rls_state(canary_url))
    if actual != expected:
        raise RuntimeError(f"unexpected RLS catalog state: expected={expected}, actual={actual}")
    print(
        f"rls_enabled={actual[0]} policies={actual[1]} helper_functions={actual[2]}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run destructive RLS migration cycles only in a generated disposable database."
    )
    parser.add_argument(
        "--database-url-env",
        default="MPLACAS_MIGRATION_DATABASE_URL",
        help="Environment variable containing a direct PostgreSQL admin URL.",
    )
    parser.add_argument(
        "--full-history-cycle",
        action="store_true",
        help="Also downgrade all historical migrations to base and rebuild them.",
    )
    args = parser.parse_args()
    raw_url = os.getenv(args.database_url_env)
    if not raw_url:
        raise SystemExit(f"{args.database_url_env} is required")

    canary_name = _canary_name()
    admin_url, canary_url = _validated_urls(raw_url, canary_name)
    canary_env = os.environ.copy()
    canary_url_text = canary_url.render_as_string(hide_password=False)
    canary_env["MPLACAS_DATABASE_URL"] = canary_url_text
    canary_env["MPLACAS_TEST_POSTGRES_URL"] = canary_url_text
    canary_env["MPLACAS_RLS_ACTIVATION_APPROVED"] = "ENABLE-RLS-20260802"
    canary_env.setdefault("MPLACAS_ENV", "test")
    canary_env.setdefault(
        "MPLACAS_JWT_SECRET",
        "rls-canary-jwt-secret-that-is-long-enough-for-validation",
    )

    print(f"canary_database={canary_name}", flush=True)
    asyncio.run(_create_database(admin_url, canary_name))
    try:
        _run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            canary_env,
            attempts=3,
        )
        _run(
            [sys.executable, "-m", "alembic", "check"], canary_env, attempts=3
        )
        _assert_rls_state(canary_url, (24, 24, 2))
        _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_postgres_application_rls.py",
                "tests/test_postgres_rls.py",
                "-q",
            ],
            canary_env,
        )

        _run(
            [sys.executable, "-m", "alembic", "downgrade", _RLS_REVISION_PARENT],
            canary_env,
            attempts=3,
        )
        _assert_rls_state(canary_url, (0, 0, 0))
        _run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            canary_env,
            attempts=3,
        )
        _assert_rls_state(canary_url, (24, 24, 2))
        _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_postgres_application_rls.py",
                "-q",
            ],
            canary_env,
        )

        if args.full_history_cycle:
            _run(
                [sys.executable, "-m", "alembic", "downgrade", "base"],
                canary_env,
                attempts=3,
            )
            remaining_tables = asyncio.run(_application_table_count(canary_url))
            if remaining_tables != 0:
                raise RuntimeError(
                    f"full rollback left {remaining_tables} application tables behind"
                )
            print("full_rollback_application_tables=0", flush=True)

            _run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                canary_env,
                attempts=3,
            )
            _run(
                [sys.executable, "-m", "alembic", "check"],
                canary_env,
                attempts=3,
            )
            _assert_rls_state(canary_url, (24, 24, 2))
            _run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_postgres_application_rls.py",
                    "-q",
                ],
                canary_env,
            )
        print("rls_canary=passed", flush=True)
        return 0
    finally:
        canary_env["MPLACAS_DATABASE_URL"] = "redacted"
        canary_env["MPLACAS_TEST_POSTGRES_URL"] = "redacted"
        canary_env["MPLACAS_RLS_ACTIVATION_APPROVED"] = "redacted"
        asyncio.run(_drop_database(admin_url, canary_name))
        print(f"canary_database_dropped={canary_name}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
