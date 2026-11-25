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
