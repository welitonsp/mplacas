from datetime import date
from decimal import Decimal
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.db.models import DailyEnergy, DailyEnergyVersion, DataStatus


class DailyEnergyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        device_id: uuid.UUID,
        production_date: date,
        energy_kwh: Decimal,
        status: DataStatus,
        source: str = "NEPVIEWER_V2",
    ) -> tuple[DailyEnergy, bool]:
        result = await self._session.execute(
            select(DailyEnergy).where(
                DailyEnergy.device_id == device_id,
                DailyEnergy.production_date == production_date,
            )
        )
        current = result.scalar_one_or_none()

        if current is None:
            current = DailyEnergy(
                device_id=device_id,
                production_date=production_date,
                energy_kwh=energy_kwh,
                status=status,
                source=source,
            )
            self._session.add(current)
            await self._session.flush()
            return current, True

        changed = current.energy_kwh != energy_kwh or current.status != status
        if not changed:
            return current, False

        self._session.add(
            DailyEnergyVersion(
                daily_energy_id=current.id,
                energy_kwh=current.energy_kwh,
                status=current.status,
            )
        )
        current.energy_kwh = energy_kwh
        current.status = status
        current.source = source
        await self._session.flush()
        return current, True
