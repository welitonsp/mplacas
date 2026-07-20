from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.core.config import get_settings


def _make_engine():
    settings = get_settings()
    url = settings.database_url
    connect_args: dict = {}
    # Neon (and other managed PostgreSQL) require SSL. asyncpg does not accept
    # sslmode in the connection URL — it must be passed via connect_args.
    if "neon.tech" in url:
        connect_args["ssl"] = "require"
    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        connect_args=connect_args,
    )


engine = _make_engine()
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
