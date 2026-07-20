from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.alerts.db_models import AlertDeliveryRecord


class SqlAlertDeliveryLedger:
    """Database-backed ledger that records only confirmed deliveries."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        provider: str,
        destination_ref: str,
    ) -> None:
        if not provider.strip() or not destination_ref.strip():
            raise ValueError("provider and destination_ref cannot be blank")
        self._session = session
        self._provider = provider.strip()
        self._destination_ref = destination_ref.strip()

    async def was_sent(self, fingerprint: str) -> bool:
        if not fingerprint.strip():
            raise ValueError("fingerprint cannot be blank")
        result = await self._session.execute(
            select(AlertDeliveryRecord.id).where(
                AlertDeliveryRecord.fingerprint == fingerprint
            )
        )
        return result.scalar_one_or_none() is not None

    async def mark_sent(self, fingerprint: str) -> None:
        if not fingerprint.strip():
            raise ValueError("fingerprint cannot be blank")
        values = {
            "id": uuid.uuid4(),
            "fingerprint": fingerprint,
            "provider": self._provider,
            "destination_ref": self._destination_ref,
        }
        dialect = self._session.sync_session.get_bind().dialect.name
        if dialect == "postgresql":
            await self._session.execute(
                postgresql_insert(AlertDeliveryRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["fingerprint"])
            )
        elif dialect == "sqlite":
            await self._session.execute(
                sqlite_insert(AlertDeliveryRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["fingerprint"])
            )
        else:
            raise RuntimeError("alert delivery ledger requires PostgreSQL or SQLite")
