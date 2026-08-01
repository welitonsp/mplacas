from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.db.models import Plant


class PlantRepository:
    """Resolve `Plant` rows por nome, criando quando necessário.

    Centraliza a lógica de "buscar por nome, criar se ausente" para que o
    `id` real (gerado pelo banco/modelo) seja sempre a fonte de verdade,
    em vez de valores arbitrários vindos de configuração externa.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, name: str) -> Plant:
        result = await self._session.execute(select(Plant).where(Plant.name == name))
        plant = result.scalar_one_or_none()
        if plant is None:
            plant = Plant(name=name)
            self._session.add(plant)
            await self._session.flush()
        return plant
