from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.db.models import DataStatus, Device, Plant
from mplacas.db.repositories.daily_energy import DailyEnergyRepository
from mplacas.db.repositories.plant import PlantRepository
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID
from mplacas.providers.base import SolarProvider


class CollectionPlantError(RuntimeError):
    """A coleta não pode gravar nesta usina (usina ausente ou inversor de outra).

    Não é falha do fabricante: não vai para a fila de nova tentativa.
    """


@dataclass(frozen=True, slots=True)
class CollectionResult:
    devices_seen: int
    records_received: int
    records_changed: int


class SolarCollectionService:
    """Sincroniza dispositivos e produção diária de forma idempotente e transacional."""

    def __init__(self, session: AsyncSession, provider: SolarProvider) -> None:
        self._session = session
        self._provider = provider
        self._energy = DailyEnergyRepository(session)
        self._plants = PlantRepository(session)

    async def collect(
        self,
        *,
        plant_name: str | None = None,
        plant_id: uuid.UUID | None = None,
        start: date,
        end: date,
        consolidate_through: date | None = None,
        expect_complete: bool = False,
    ) -> CollectionResult:
        """Coleta gerenciando a própria transação (commit/rollback)."""
        try:
            result = await self.collect_in_session(
                plant_name=plant_name,
                plant_id=plant_id,
                start=start,
                end=end,
                consolidate_through=consolidate_through,
                expect_complete=expect_complete,
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return result

    async def collect_in_session(
        self,
        *,
        plant_name: str | None = None,
        plant_id: uuid.UUID | None = None,
        start: date,
        end: date,
        consolidate_through: date | None = None,
        expect_complete: bool = False,
    ) -> CollectionResult:
        """Coleta sem gerenciar a transação: commit/rollback ficam com o chamador.

        Usado pelo worker de drenagem, cuja disciplina transacional (uma
        transação por tarefa) precisa governar a persistência.
        """
        if end < start:
            raise ValueError("A data final não pode ser anterior à inicial")

        plant = await self._resolve_plant(plant_name=plant_name, plant_id=plant_id)
        devices = await self._provider.list_devices()
        received = 0
        changed = 0

        for remote in devices:
            device = await self._get_or_create_device(
                plant=plant,
                serial_number=remote.serial_number,
                model_name=remote.model_name,
            )
            rows = await self._provider.get_daily_energy(
                remote.serial_number, start, end, expect_complete=expect_complete
            )
            received += len(rows)
            for row in rows:
                status = (
                    DataStatus.CONSOLIDATED
                    if consolidate_through is not None
                    and row.production_date <= consolidate_through
                    else DataStatus.PROVISIONAL
                )
                _, was_changed = await self._energy.upsert(
                    device_id=device.id,
                    production_date=row.production_date,
                    energy_kwh=Decimal(row.energy_kwh),
                    status=status,
                )
                changed += int(was_changed)

        return CollectionResult(
            devices_seen=len(devices),
            records_received=received,
            records_changed=changed,
        )

    async def _resolve_plant(
        self, *, plant_name: str | None, plant_id: uuid.UUID | None
    ) -> Plant:
        """Usina pelo id (conexão por usina, ADR-091) ou pelo nome (caminho antigo)."""
        if (plant_name is None) == (plant_id is None):
            raise ValueError("informe plant_id ou plant_name, não os dois")
        if plant_id is not None:
            plant = await self._session.get(Plant, plant_id)
            if plant is None:
                raise CollectionPlantError("plant not found")
            return plant
        assert plant_name is not None
        return await self._get_or_create_plant(plant_name)

    async def _get_or_create_plant(self, name: str) -> Plant:
        # Jobs de coleta em nuvem rodam sob configuração estática de
        # plataforma (settings.cloud_job_plant_name), sem organização por
        # requisição — usam a organização default legada (ADR-052/069).
        return await self._plants.get_or_create(
            name, organization_id=DEFAULT_ORGANIZATION_ID
        )

    async def _get_or_create_device(
        self, *, plant: Plant, serial_number: str, model_name: str | None
    ) -> Device:
        result = await self._session.execute(
            select(Device).where(
                Device.provider == "NEPVIEWER",
                Device.serial_number == serial_number,
            )
        )
        device = result.scalar_one_or_none()
        if device is None:
            device = Device(
                plant_id=plant.id,
                provider="NEPVIEWER",
                serial_number=serial_number,
                model_name=model_name,
            )
            self._session.add(device)
            await self._session.flush()
        elif device.plant_id != plant.id:
            # ADR-091: o mesmo número de série em outra usina nunca é
            # reaproveitado — gravaria a produção de um cliente em outro.
            raise CollectionPlantError(
                f"device already belongs to another plant (device_id={device.id})"
            )
        elif model_name and device.model_name != model_name:
            device.model_name = model_name
        return device
