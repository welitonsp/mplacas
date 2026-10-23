"""Busca o histórico de sol (irradiação diária) para todas as usinas (ADR-082).

O ciclo diário só coleta o clima do dia anterior. Para estimar a produção dos
dias sem leitura do inversor no passado, o sistema precisa do sol daqueles
dias: este job busca o arquivo histórico do Open-Meteo em blocos e grava pelo
mesmo caminho idempotente do ciclo diário (``collect_and_persist_daily_climate``).
Não gera alerta nem análise.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

from mplacas.climate.collection_service import collect_and_persist_daily_climate
from mplacas.climate.provider import ClimateProvider
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_platform_context

logger = logging.getLogger(__name__)


def climate_chunks(start: date, end: date, maximum_days: int) -> list[tuple[date, date]]:
    """Divide o intervalo em blocos de no máximo ``maximum_days`` dias."""
    if end < start:
        raise ValueError("end date cannot be before start date")
    if maximum_days < 1:
        raise ValueError("maximum_days must be positive")
    chunks: list[tuple[date, date]] = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=maximum_days - 1), end)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


async def run_climate_history(
    *,
    start: date,
    end: date,
    plants: list[tuple[uuid.UUID, str]],
    provider: ClimateProvider,
    maximum_days: int,
) -> list[str]:
    """Busca e grava o clima de cada usina; devolve as falhas (usina e bloco)."""
    failures: list[str] = []
    for plant_id, plant_name in plants:
        for chunk_start, chunk_end in climate_chunks(start, end, maximum_days):
            try:
                async with SessionFactory() as session:
                    await set_platform_context(session)
                    result = await collect_and_persist_daily_climate(
                        session,
                        plant_id=plant_id,
                        provider=provider,
                        start_date=chunk_start,
                        end_date=chunk_end,
                        maximum_days=maximum_days,
                    )
                    await session.commit()
                logger.info(
                    "climate_history_chunk_completed",
                    extra={
                        "plant_id": str(plant_id),
                        "start_date": chunk_start.isoformat(),
                        "end_date": chunk_end.isoformat(),
                        "received": result.received,
                    },
                )
            except Exception:
                logger.exception(
                    "climate_history_chunk_failed",
                    extra={"plant_id": str(plant_id), "start_date": chunk_start.isoformat()},
                )
                failures.append(f"{plant_name} {chunk_start}..{chunk_end}")
    return failures
