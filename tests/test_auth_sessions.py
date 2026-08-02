from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.auth.password import hash_password
from mplacas.auth.db_models import AuthSessionRecord
from mplacas.auth.session_service import AuthSessionService, LoginRateLimitService
from mplacas.core.config import get_settings
from mplacas.core.jwt import decode_token
from mplacas.core.security import OperationsRole
from mplacas.credentials.db_models import OperationalUserRecord
from mplacas.db.base import Base
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord

_TEST_ENGINES = []


@pytest.fixture(autouse=True)
async def _dispose_test_engines():
    yield
    while _TEST_ENGINES:
        await _TEST_ENGINES.pop().dispose()


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _TEST_ENGINES.append(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_refresh_session_rotates_and_rejects_reuse(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()
    factory = await _factory()

    async with factory() as session:
        org = OrganizationRecord(
            id=DEFAULT_ORGANIZATION_ID,
            name="Default",
            slug="default",
            active=True,
        )
        user = OperationalUserRecord(
            organization_id=org.id,
            name="operador-read",
            role=OperationsRole.READ.value,
            active=True,
            password_hash=hash_password("senha-segura"),
        )
        session.add_all([org, user])
        await session.flush()

        service = AuthSessionService(session)
        refresh_token = await service.create(
            user_id=user.id,
            organization_id=org.id,
            ttl_seconds=3600,
        )
        claims = decode_token(refresh_token, expected_type="refresh")

        rotated = await service.rotate(
            token=refresh_token,
            claims=claims,
            ttl_seconds=3600,
        )
        assert rotated is not None
        assert rotated != refresh_token
        assert await service.rotate(
            token=refresh_token,
            claims=claims,
            ttl_seconds=3600,
        ) is None

        active_sessions = list(
            (
                await session.scalars(
                    select(AuthSessionRecord).where(AuthSessionRecord.active.is_(True))
                )
            ).all()
        )
        assert active_sessions == []

        rotated_claims = decode_token(rotated, expected_type="refresh")
        assert rotated_claims.sub == user.id
        assert rotated_claims.org_id == org.id
        assert rotated_claims.jti is not None
        assert rotated_claims.jti != claims.jti

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_login_rate_limit_locks_and_clears() -> None:
    factory = await _factory()
    async with factory() as session:
        service = LoginRateLimitService(session)
        key = LoginRateLimitService.key_for(username="Admin", client_host="127.0.0.1")

        assert await service.is_locked(key) is False
        await service.record_failure(
            key,
            max_attempts=2,
            window_seconds=900,
            lockout_seconds=900,
        )
        assert await service.is_locked(key) is False
        await service.record_failure(
            key,
            max_attempts=2,
            window_seconds=900,
            lockout_seconds=900,
        )
        assert await service.is_locked(key) is True

        await service.clear(key)
        assert await service.is_locked(key) is False
