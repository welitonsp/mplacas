from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from mplacas.collection.queue import CollectionQueueRepository
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_platform_context
from mplacas.core.config import get_settings
from mplacas.providers.accounts import GROWATT_TOKEN, ProviderLogin
from mplacas.collection.worker import SLOW_RETRY_SECONDS
from mplacas.providers.base import (
    ProviderAuthError,
    ProviderBlockedError,
    ProviderError,
    ProviderRateLimitedError,
)
from mplacas.providers.factory import ENERGY_SOURCES, build_resilient_provider
from mplacas.providers.growatt.openapi import GrowattOpenApiClient
from mplacas.services.collection import CollectionResult, SolarCollectionService

logger = logging.getLogger(__name__)

COLLECTION_TASK_TYPE = "solar_daily"


async def run_solar_collection(
    *,
    target_date: date,
    plant_id,
    credentials: ProviderLogin,
    provider: str,
    now: datetime | None = None,
) -> CollectionResult | None:
    """Coleta a produção diária de uma usina com a conexão dela (ADR-091).

    Monta o provedor NEPViewer já envolvido pela camada de retry/detecção de
    dados incompletos. Se, mesmo após o retry, a API seguir indisponível ou
    incompleta, a coleta do dia é enfileirada para nova tentativa posterior,
    em vez de falhar em definitivo.
    """
    client, solar_provider = build_resilient_provider(
        provider, account=credentials.login, password=credentials.password
    )
    try:
        async with SessionFactory() as session:
            await set_platform_context(session)
            service = SolarCollectionService(
                session,
                solar_provider,
                provider_name=provider,
                energy_source=ENERGY_SOURCES[provider],
            )
            result = await service.collect(
                plant_id=plant_id,
                start=target_date,
                end=target_date,
                consolidate_through=target_date,
            )
        logger.info(
            "solar_collection_job_completed",
            extra={
                "plant_id": str(plant_id),
                "target_date": target_date.isoformat(),
                "devices_seen": result.devices_seen,
                "records_received": result.records_received,
                "records_changed": result.records_changed,
            },
        )
        return result
    except ProviderAuthError as exc:
        handled, meter = await _meter_fallback(
            exc, client=client, plant_id=plant_id, provider=provider, now=now
        )
        if handled:
            return meter
        await _enqueue_retry(
            plant_id=plant_id,
            target_date=target_date,
            available_after=timedelta(seconds=SLOW_RETRY_SECONDS),
        )
        logger.warning(
            "solar_collection_job_blocked",
            extra={
                "plant_id": str(plant_id),
                "target_date": target_date.isoformat(),
                "error_code": type(exc).__name__,
            },
        )
        raise
    except ProviderRateLimitedError as exc:
        # Bloqueio do fabricante ou senha recusada: o dia volta à fila só daqui
        # a 1 h (nunca na drenagem logo em seguida) e a falha sobe para a
        # conexão aparecer como "falha" em Minha usina (ADR-092).
        await _enqueue_retry(
            plant_id=plant_id,
            target_date=target_date,
            available_after=timedelta(seconds=SLOW_RETRY_SECONDS),
        )
        logger.warning(
            "solar_collection_job_blocked",
            extra={
                "plant_id": str(plant_id),
                "target_date": target_date.isoformat(),
                "error_code": type(exc).__name__,
            },
        )
        raise
    except ProviderError as exc:
        await _enqueue_retry(plant_id=plant_id, target_date=target_date)
        logger.warning(
            "solar_collection_job_deferred",
            extra={
                "plant_id": str(plant_id),
                "target_date": target_date.isoformat(),
                "error_code": type(exc).__name__,
            },
        )
        return None
    finally:
        await client.aclose()


# Até esta hora (local) ainda é noite: o total lido cobre a véspera inteira.
METER_NIGHT_UNTIL_HOUR = 5


async def _meter_fallback(
    exc: ProviderAuthError,
    *,
    client: object,
    plant_id,
    provider: str,
    now: datetime | None,
) -> tuple[bool, CollectionResult | None]:
    """Token Growatt sem permissão de histórico: lê o total da lista (ADR-098).

    Só quando a própria lista de usinas funcionou (o token é válido e só o
    histórico é recusado). Fora da madrugada a leitura não serve para o dia
    anterior e é descartada sem erro.
    """
    if (
        provider != GROWATT_TOKEN
        or isinstance(exc, ProviderBlockedError)
        or not isinstance(client, GrowattOpenApiClient)
        or not client.listed_plants
    ):
        return False, None
    local_now = (now or datetime.now(UTC)).astimezone(ZoneInfo(get_settings().timezone))
    if local_now.hour >= METER_NIGHT_UNTIL_HOUR:
        logger.info(
            "solar_meter_reading_skipped_daylight",
            extra={"plant_id": str(plant_id), "local_hour": local_now.hour},
        )
        # Nada coletado: "adiado", nunca sucesso (a conexão não fica verde à toa).
        return True, None
    try:
        totals = await client.meter_totals()
        async with SessionFactory() as session:
            await set_platform_context(session)
            result = await SolarCollectionService(
                session,
                client,
                provider_name=provider,
                energy_source=ENERGY_SOURCES[provider],
            ).record_meter_totals(
                plant_id=plant_id, totals=totals, reading_date=local_now.date()
            )
            await session.commit()
    except Exception as meter_exc:
        logger.warning(
            "solar_meter_reading_failed",
            extra={"plant_id": str(plant_id), "error_code": type(meter_exc).__name__},
        )
        raise meter_exc from None
    logger.info(
        "solar_meter_reading_recorded",
        extra={
            "plant_id": str(plant_id),
            "reading_date": local_now.date().isoformat(),
            "devices": result.devices_seen,
            "days_derived": result.records_received,
        },
    )
    return True, result


async def _enqueue_retry(
    *, plant_id, target_date: date, available_after: timedelta | None = None
) -> None:
    async with SessionFactory() as session:
        await set_platform_context(session)
        await CollectionQueueRepository(session).enqueue(
            plant_id=plant_id,
            task_type=COLLECTION_TASK_TYPE,
            target_date=target_date.isoformat(),
            available_after=available_after,
        )
        await session.commit()
