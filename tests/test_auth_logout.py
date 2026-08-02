from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.auth.db_models import AuthSessionRecord
from mplacas.auth.router import LogoutRequest, logout
from mplacas.auth.session_service import AuthSessionService
from mplacas.core.config import get_settings
from mplacas.db.base import Base
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.credentials.db_models import OperationalUserRecord


async def test_logout_revokes_refresh_session_and_is_idempotent(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "logout-test-jwt-secret-at-least-32-bytes")
    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        organization = OrganizationRecord(
            id=DEFAULT_ORGANIZATION_ID,
            name="Logout organization",
            slug="logout-organization",
            active=True,
        )
        user = OperationalUserRecord(
            organization_id=organization.id,
            name="logout-user",
            active=True,
        )
        session.add_all([organization, user])
        await session.flush()
        token = await AuthSessionService(session).create(
            user_id=user.id,
            organization_id=organization.id,
            ttl_seconds=3600,
        )
        await session.commit()

        first = await logout(LogoutRequest(refresh_token=token), session)
        second = await logout(LogoutRequest(refresh_token=token), session)
        record = (
            await session.scalars(select(AuthSessionRecord))
        ).one()

        assert first.status_code == 204
        assert second.status_code == 204
        assert record.active is False
        assert record.revoked_at is not None

    await engine.dispose()
    get_settings.cache_clear()


async def test_logout_hides_invalid_token() -> None:
    class NoDatabaseSession:
        pass

    response = await logout(
        LogoutRequest(refresh_token="invalid"),
        NoDatabaseSession(),  # type: ignore[arg-type]
    )
    assert response.status_code == 204
