from collections.abc import AsyncIterator

from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.core.config import get_settings
from mplacas.db.connection import database_connect_args


def _make_engine():
    settings = get_settings()
    url = settings.database_url
    if url.strip().lower().startswith("sqlite"):
        # SQLite/aiosqlite cria uma thread por conexão. Não preservar essas
        # conexões entre event loops evita workers tentando responder depois
        # que o loop do request/teste já foi encerrado.
        return create_async_engine(
            url,
            poolclass=NullPool,
            connect_args=database_connect_args(url),
        )
    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        connect_args=database_connect_args(url),
    )


engine = _make_engine()
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
