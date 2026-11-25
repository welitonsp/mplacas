"""Exclusão definitiva na PostgreSQL real: ordem das FKs RESTRICT e contexto de plataforma.

Tudo roda numa transação que é desfeita no fim, então o banco de teste não muda.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.db.models import Plant
from mplacas.db.tenant_context import set_platform_context
from mplacas.providers.purge_discontinued import build_plan, execute_purge

from test_purge_discontinued_plants import _seed_world


@pytest.mark.postgres_integration
@pytest.mark.asyncio
async def test_exclusao_na_postgres_apaga_a_growatt_e_preserva_a_nepviewer() -> None:
    url = os.getenv("MPLACAS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("MPLACAS_TEST_POSTGRES_URL is required")
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    gw, nep_a, nep_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            await set_platform_context(session)
            await _seed_world(session, org_a, org_b, gw, nep_a, nep_b)
            plan = await build_plan(session)
            assert gw in plan.plant_ids
            assert nep_a not in plan.plant_ids and nep_b not in plan.plant_ids
            result = await execute_purge(session, plan)
            assert result.deleted["utility_bills"] >= 1
            remaining = set(
                (await session.execute(select(Plant.id).where(Plant.id.in_([gw, nep_a, nep_b]))))
                .scalars()
                .all()
            )
            assert remaining == {nep_a, nep_b}
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.postgres_integration
@pytest.mark.asyncio
async def test_exclusao_com_commit_sob_rls_force_com_papel_nao_superusuario() -> None:
    """Apply completo, com commit, num papel NÃO superusuário membro de ``mplacas_platform``
    (padrão de ``test_postgres_application_rls``): o RLS FORCE vale de verdade e o contexto de
    plataforma tem de bastar para ler, apagar e gravar o evento de plataforma.
    """
    from sqlalchemy import delete, text

    from mplacas.audit.db_models import AuditEventRecord
    from mplacas.credentials.db_models import ApiCredentialRecord, OperationalUserRecord
    from mplacas.organizations.db_models import OrganizationRecord
    from mplacas.providers.purge_discontinued import CATEGORIES

    url = os.getenv("MPLACAS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("MPLACAS_TEST_POSTGRES_URL is required")
    suffix = uuid.uuid4().hex
    platform_role = f"mplacas_purge_platform_{suffix}"
    platform_marker = "mplacas_platform"
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    gw, nep_a, nep_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    marker_created = False
    roles_created = False
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            marker_created = not bool(
                (
                    await connection.execute(
                        text("SELECT to_regrole(:role_name) IS NOT NULL"),
                        {"role_name": platform_marker},
                    )
                ).scalar_one()
            )
            if marker_created:
                await connection.execute(text(f'CREATE ROLE "{platform_marker}" NOLOGIN'))
            await connection.execute(text(f'CREATE ROLE "{platform_role}" NOLOGIN'))
            roles_created = True
            await connection.execute(
                text(f'GRANT "{platform_role}" TO CURRENT_USER WITH SET TRUE')
            )
            await connection.execute(text(f'GRANT "{platform_marker}" TO "{platform_role}"'))
            await connection.execute(
                text(f'GRANT USAGE ON SCHEMA public TO "{platform_role}"')
            )
            await connection.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                    f'TO "{platform_role}"'
                )
            )
        # Semeia como dono (o dono do banco de teste), com commit.
        async with factory() as session:
            await set_platform_context(session)
            await _seed_world(session, org_a, org_b, gw, nep_a, nep_b)
            await session.commit()

        async with factory() as session:
            await set_platform_context(session)
            await session.execute(text(f'SET LOCAL ROLE "{platform_role}"'))
            plan = await build_plan(session, lock=True)
            assert gw in plan.plant_ids
            assert nep_a not in plan.plant_ids and nep_b not in plan.plant_ids
            result = await execute_purge(session, plan)
            assert result.deleted["utility_bills"] >= 1
            await session.commit()

        async with factory() as session:
            await set_platform_context(session)
            remaining = set(
                (await session.execute(select(Plant.id).where(Plant.id.in_([gw, nep_a, nep_b]))))
                .scalars()
                .all()
            )
            assert remaining == {nep_a, nep_b}
            event = (
                await session.execute(
                    select(AuditEventRecord).where(
                        AuditEventRecord.action == "plant.purged_discontinued_provider",
                        AuditEventRecord.organization_id.is_(None),
                    )
                )
            ).scalars().all()
            assert event
    finally:
        async with engine.begin() as connection:
            ids = [gw, nep_a, nep_b]
            for category in CATEGORIES:
                await connection.execute(delete(category.table).where(category.owned(ids)))
            for model in (ApiCredentialRecord, OperationalUserRecord):
                await connection.execute(
                    delete(model).where(model.organization_id.in_([org_a, org_b]))
                )
            await connection.execute(
                delete(AuditEventRecord).where(
                    AuditEventRecord.organization_id.in_([org_a, org_b])
                )
            )
            await connection.execute(
                delete(OrganizationRecord).where(OrganizationRecord.id.in_([org_a, org_b]))
            )
            existing_roles = set(
                (
                    await connection.execute(
                        text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:names)"),
                        {"names": [platform_role, platform_marker]},
                    )
                ).scalars()
            )
            if roles_created and platform_role in existing_roles:
                await connection.execute(text(f'DROP OWNED BY "{platform_role}"'))
                await connection.execute(text(f'DROP ROLE "{platform_role}"'))
            if marker_created and platform_marker in existing_roles:
                await connection.execute(text(f'DROP ROLE IF EXISTS "{platform_marker}"'))
        await engine.dispose()
