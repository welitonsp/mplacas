from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.auth.db_models import AuthSessionRecord
from mplacas.auth.password import hash_password
from mplacas.auth.session_service import AuthSessionService
from mplacas.core.config import get_settings
from mplacas.core.jwt import decode_token
from mplacas.core.security import OperationsRole
from mplacas.credentials.db_models import OperationalUserRecord
from mplacas.organizations.db_models import OrganizationRecord


@pytest.mark.postgres_integration
@pytest.mark.asyncio
async def test_concurrent_refresh_rotation_has_one_winner_and_revokes_replayed_family(
    monkeypatch,
) -> None:
    database_url = os.getenv("MPLACAS_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("MPLACAS_TEST_POSTGRES_URL is not configured")

    monkeypatch.setenv(
        "MPLACAS_JWT_SECRET",
        "postgres-integration-jwt-secret-at-least-32-bytes",
    )
    get_settings.cache_clear()
    engine = create_async_engine(database_url, pool_size=3, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()

    try:
        async with factory() as session:
            session.add(
                OrganizationRecord(
                    id=organization_id,
                    name="Concurrent Refresh Test",
                    slug=f"refresh-{organization_id.hex}",
                    active=True,
                )
            )
            session.add(
                OperationalUserRecord(
                    id=user_id,
                    organization_id=organization_id,
                    name=f"refresh-{user_id.hex}@test.invalid",
                    role=OperationsRole.READ.value,
                    active=True,
                    password_hash=hash_password("integration-password"),
                )
            )
            await session.flush()
            token = await AuthSessionService(session).create(
                user_id=user_id,
                organization_id=organization_id,
                ttl_seconds=3600,
            )
            claims = decode_token(token, expected_type="refresh")
            family_id = claims.jti
            await session.commit()

        start = asyncio.Event()

        async def rotate_once() -> str | None:
            async with factory() as session:
                await start.wait()
                rotated = await AuthSessionService(session).rotate(
                    token=token,
                    claims=claims,
                    ttl_seconds=3600,
                )
                await session.commit()
                return rotated

        tasks = [asyncio.create_task(rotate_once()) for _ in range(2)]
        start.set()
        results = await asyncio.gather(*tasks)

        assert sum(result is not None for result in results) == 1
        assert family_id is not None
        async with factory() as session:
            family = list(
                (
                    await session.scalars(
                        select(AuthSessionRecord).where(
                            AuthSessionRecord.family_id == family_id
                        )
                    )
                ).all()
            )
        assert len(family) == 2
        assert not any(record.active for record in family)
        assert sum(record.replaced_by_session_id is not None for record in family) == 1
    finally:
        await engine.dispose()
        get_settings.cache_clear()
