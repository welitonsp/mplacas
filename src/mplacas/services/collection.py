from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.db.models import DailyEnergy, DataStatus, Device, MeterReading, Plant
from mplacas.db.repositories.daily_energy import DailyEnergyRepository
from mplacas.providers.accounts import family_members
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

    def __init__(
        self,
        session: AsyncSession,
        provider: SolarProvider,
        *,
        provider_name: str,
        energy_source: str,
    ) -> None:
        """``provider_name`` vai para ``devices.provider`` e ``energy_source`` para
        ``daily_energy.source`` (ADR-092): o mesmo número de série em marcas
        diferentes não se confunde."""
        self._session = session
        self._provider = provider
        self._provider_name = provider_name
        self._energy_source = energy_source
        self._energy = DailyEnergyRepository(session)

    async def collect(
        self,
        *,
        plant_id: uuid.UUID,
        start: date,
        end: date,
        consolidate_through: date | None = None,
        expect_complete: bool = False,
    ) -> CollectionResult:
        """Coleta gerenciando a própria transação (commit/rollback)."""
        try:
            result = await self.collect_in_session(
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
        plant_id: uuid.UUID,
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

        plant = await self._session.get(Plant, plant_id)
        if plant is None:
            raise CollectionPlantError("plant not found")
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
                    source=self._energy_source,
                )
                changed += int(was_changed)

        return CollectionResult(
            devices_seen=len(devices),
            records_received=received,
            records_changed=changed,
        )

    async def record_meter_totals(
        self,
        *,
        plant_id: uuid.UUID,
        totals: dict[str, Decimal],
        covered_date: date,
    ) -> CollectionResult:
        """Guarda o total que fecha ``covered_date`` e deriva a produção dele (ADR-098).

        ``covered_date`` é o dia já encerrado pelo sol quando o total foi lido
        (``collection.meter.covered_date``). Com o total que fechou a véspera,
        a diferença é a produção de ``covered_date``. Nada é inventado: sem a
        véspera (primeira leitura, noite perdida) o dia fica sem dado; total
        menor ou igual (troca de inversor, zeramento, lista ainda não
        atualizada) também. Produção vinda do histórico da marca (outra fonte)
        nunca é sobrescrita.
        """
        plant = await self._session.get(Plant, plant_id)
        if plant is None:
            raise CollectionPlantError("plant not found")
        derived = 0
        changed = 0
        for serial, total in totals.items():
            device = await self._get_or_create_device(
                plant=plant, serial_number=serial, model_name="Usina Growatt"
            )
            current = await self._session.scalar(
                select(MeterReading).where(
                    MeterReading.device_id == device.id,
                    MeterReading.reading_date == covered_date,
                )
            )
            if current is None:
                current = MeterReading(
                    plant_id=plant_id,
                    device_id=device.id,
                    reading_date=covered_date,
                    total_kwh=total,
                    source=self._energy_source,
                )
                self._session.add(current)
            elif total > current.total_kwh:
                # várias leituras na mesma noite: fica a mais nova (maior)
                current.total_kwh = total
            await self._session.flush()
            previous = await self._session.scalar(
                select(MeterReading).where(
                    MeterReading.device_id == device.id,
                    MeterReading.reading_date == covered_date - timedelta(days=1),
                )
            )
            # Total igual ao da véspera quase sempre é a Growatt ainda sem
            # atualizar a lista: não vira um dia de 0 kWh "confirmado".
            if previous is None or current.total_kwh <= previous.total_kwh:
                continue
            existing = await self._session.scalar(
                select(DailyEnergy).where(
                    DailyEnergy.device_id == device.id,
                    DailyEnergy.production_date == covered_date,
                )
            )
            if existing is not None and existing.source != self._energy_source:
                continue
            _, was_changed = await self._energy.upsert(
                device_id=device.id,
                production_date=covered_date,
                energy_kwh=current.total_kwh - previous.total_kwh,
                status=DataStatus.CONSOLIDATED,
                source=self._energy_source,
            )
            derived += 1
            changed += int(was_changed)
        return CollectionResult(
            devices_seen=len(totals), records_received=derived, records_changed=changed
        )

    async def _get_or_create_device(
        self, *, plant: Plant, serial_number: str, model_name: str | None
    ) -> Device:
        # Mesma usina física = mesma FAMÍLIA de marca (Growatt por senha e por
        # token leem o mesmo ``GW-PLANT-<id>``): trocar a conexão reaproveita o
        # aparelho em vez de criar um 2º e dobrar a produção. O ``provider``
        # gravado no aparelho não é reescrito.
        members = family_members(self._provider_name)
        found = (
            await self._session.execute(
                select(Device)
                .where(Device.provider.in_(members), Device.serial_number == serial_number)
                .order_by(Device.created_at, Device.id)
            )
        ).scalars().all()
        # ADR-091: aparelho da MESMA marca em outra usina nunca é reaproveitado.
        for candidate in found:
            if candidate.provider == self._provider_name and candidate.plant_id != plant.id:
                raise CollectionPlantError(
                    f"device already belongs to another plant (device_id={candidate.id})"
                )
        own = [d for d in found if d.plant_id == plant.id]
        if not own and found:
            # só existe em outra usina (sob a outra marca da família): mesma barreira
            raise CollectionPlantError(
                f"device already belongs to another plant (device_id={found[0].id})"
            )
        device = next((d for d in own if d.provider == self._provider_name), None)
        if device is None and own:
            device = own[0]
        if device is None:
            device = Device(
                plant_id=plant.id,
                provider=self._provider_name,
                serial_number=serial_number,
                model_name=model_name,
            )
            self._session.add(device)
            await self._session.flush()
        elif model_name and device.model_name != model_name:
            device.model_name = model_name
        return device
