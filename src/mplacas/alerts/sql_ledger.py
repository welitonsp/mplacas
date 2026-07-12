from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
        self._session.add(
            AlertDeliveryRecord(
                fingerprint=fingerprint,
                provider=self._provider,
                destination_ref=self._destination_ref,
            )
        )
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
