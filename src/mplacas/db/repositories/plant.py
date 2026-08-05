from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.db.models import Plant
from mplacas.organizations.db_models import OrganizationRecord


class PlantRepository:
    """Resolve `Plant` rows por nome dentro de uma organização, criando quando necessário.

    Centraliza a lógica de "buscar por nome, criar se ausente" para que o
    `id` real (gerado pelo banco/modelo) seja sempre a fonte de verdade,
    em vez de valores arbitrários vindos de configuração externa. A busca e
    a criação são sempre escopadas por `organization_id`: duas organizações
    diferentes podem ter usinas com o mesmo nome sem colidir (ADR-069, E.4).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, name: str, *, organization_id: uuid.UUID) -> Plant:
        result = await self._session.execute(
            select(Plant).where(
                Plant.name == name, Plant.organization_id == organization_id
            )
        )
        plant = result.scalar_one_or_none()
        if plant is None:
            plant = Plant(name=name, organization_id=organization_id)
            self._session.add(plant)
            await self._session.flush()
            await self._elect_default_if_unset(organization_id, plant.id)
        return plant

    async def _elect_default_if_unset(
        self, organization_id: uuid.UUID, plant_id: uuid.UUID
    ) -> None:
        """Elege a usina recém-criada como default se a organização não tem uma.

        Roda na mesma transação da criação, garantindo a invariante do
        ADR-069 §E.4: uma organização com pelo menos uma usina criada por
        este caminho nunca fica com `default_plant_id` nulo.
        """
        organization = await self._session.get(OrganizationRecord, organization_id)
        if organization is not None and organization.default_plant_id is None:
            organization.default_plant_id = plant_id
            await self._session.flush()
