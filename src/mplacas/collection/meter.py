"""Leitura do total acumulado da marca (ADR-098).

Para contas Growatt cujo token só lê ``plant/list``: o total desde a
instalação, lido no escuro, fecha o dia. A diferença entre dois dias fechados
seguidos é a produção do dia.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from mplacas.core.config import get_settings
from mplacas.db.models import Device
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_platform_context
from mplacas.providers.growatt.openapi import GrowattOpenApiClient
from mplacas.services.collection import CollectionResult, SolarCollectionService

logger = logging.getLogger(__name__)

# Fonte própria em ``daily_energy``: a produção derivada do total nunca
# sobrescreve a do histórico da marca (se ele voltar a ser liberado).
METER_ENERGY_SOURCE = "GROWATT_TOTAL_DIFF"
# Escuro o ano todo em Goiás: depois do pôr do sol (até ~18:50 em janeiro) e
# antes do nascer (desde ~05:20 em junho), com folga.
DARK_FROM = time(19, 30)
DARK_UNTIL = time(5, 0)


def covered_date(now: datetime | None = None) -> date | None:
    """Dia já encerrado pelo sol no momento da leitura, ou ``None`` se é dia.

    Às 21:00 do dia D o total já cobre D inteiro; às 03:00 de D+1 também.
    """
    local = (now or datetime.now(UTC)).astimezone(ZoneInfo(get_settings().timezone))
    clock = local.time()
    if clock >= DARK_FROM:
        return local.date()
    if clock < DARK_UNTIL:
        return local.date() - timedelta(days=1)
    return None


async def record_meter_reading(
    client: GrowattOpenApiClient,
    *,
    plant_id: uuid.UUID,
    provider: str,
    day: date,
) -> CollectionResult:
    """Lê o total na marca (a lista do cliente, em cache se já lida) e grava."""
    totals = await client.meter_totals()
    async with SessionFactory() as session:
        await set_platform_context(session)
        # Um token pode enxergar várias usinas: fica só a(s) já ligada(s) a
        # esta usina, para nunca somar a produção de outra.
        own = set(
            await session.scalars(
                select(Device.serial_number).where(
                    Device.plant_id == plant_id, Device.provider == provider
                )
            )
        )
        if own:
            totals = {serial: total for serial, total in totals.items() if serial in own}
        result = await SolarCollectionService(
            session,
            client,
            provider_name=provider,
            energy_source=METER_ENERGY_SOURCE,
        ).record_meter_totals(plant_id=plant_id, totals=totals, covered_date=day)
        await session.commit()
    logger.info(
        "solar_meter_reading_recorded",
        extra={
            "plant_id": str(plant_id),
            "covered_date": day.isoformat(),
            "devices": result.devices_seen,
            "days_derived": result.records_received,
        },
    )
    return result
