from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.db.tenant_context import set_platform_context, set_tenant_context


@pytest.mark.postgres_integration
@pytest.mark.asyncio
async def test_rls_is_fail_closed_and_platform_bypass_is_role_gated() -> None:
    url = os.getenv("MPLACAS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("MPLACAS_TEST_POSTGRES_URL is required")

    suffix = uuid.uuid4().hex
    table = f"rls_poc_{suffix}"
    tenant_role = f"rls_tenant_{suffix}"
    platform_role = f"rls_platform_{suffix}"
    marker_role = f"rls_platform_marker_{suffix}"
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    policy = f"""
        CREATE POLICY tenant_isolation ON {table}
        USING (
            organization_id::text = current_setting('mplacas.organization_id', true)
            OR (
                current_setting('mplacas.platform_bypass', true) = 'on'
                AND pg_has_role(current_user, '{marker_role}', 'member')
            )
        )
        WITH CHECK (
            organization_id::text = current_setting('mplacas.organization_id', true)
            OR (
                current_setting('mplacas.platform_bypass', true) = 'on'
                AND pg_has_role(current_user, '{marker_role}', 'member')
            )
        )
    """

    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"CREATE ROLE {marker_role} NOLOGIN"))
            await connection.execute(text(f"CREATE ROLE {tenant_role} NOLOGIN"))
            await connection.execute(text(f"CREATE ROLE {platform_role} NOLOGIN"))
            await connection.execute(text(f"GRANT {marker_role} TO {platform_role}"))
            await connection.execute(
                text(
                    f"CREATE TABLE {table} ("
                    "id uuid PRIMARY KEY, organization_id uuid NOT NULL, payload text NOT NULL)"
                )
            )
            await connection.execute(
                text(f"INSERT INTO {table} VALUES (:a, :tenant_a, 'A'), (:b, :tenant_b, 'B')"),
                {"a": uuid.uuid4(), "b": uuid.uuid4(), "tenant_a": tenant_a, "tenant_b": tenant_b},
            )
            await connection.execute(text(f"GRANT SELECT, INSERT ON {table} TO {tenant_role}"))
            await connection.execute(text(f"GRANT SELECT, INSERT ON {table} TO {platform_role}"))
            await connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            await connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
            await connection.execute(text(policy))

        async with factory() as session:
            await session.execute(text(f"SET LOCAL ROLE {tenant_role}"))
            assert (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0

            await set_tenant_context(session, tenant_a)
            rows = (await session.execute(text(f"SELECT payload FROM {table}"))).scalars().all()
            assert rows == ["A"]
            with pytest.raises(DBAPIError):
                await session.execute(
                    text(f"INSERT INTO {table} VALUES (:id, :tenant, 'forbidden')"),
                    {"id": uuid.uuid4(), "tenant": tenant_b},
                )
            await session.rollback()

        async with factory() as session:
            await session.execute(text(f"SET LOCAL ROLE {tenant_role}"))
            await set_platform_context(session)
            assert (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0

        async with factory() as session:
            await session.execute(text(f"SET LOCAL ROLE {platform_role}"))
            assert (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0
            await set_platform_context(session)
            assert (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 2
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
            await connection.execute(text(f"DROP ROLE IF EXISTS {platform_role}"))
            await connection.execute(text(f"DROP ROLE IF EXISTS {tenant_role}"))
            await connection.execute(text(f"DROP ROLE IF EXISTS {marker_role}"))
        await engine.dispose()
