from __future__ import annotations

import logging
from datetime import date, timedelta

from mplacas.collection.queue import CollectionQueueRepository
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_platform_context
from mplacas.providers.accounts import ProviderLogin
from mplacas.collection.worker import SLOW_RETRY_SECONDS
from mplacas.providers.base import ProviderAuthError, ProviderError, ProviderRateLimitedError
from mplacas.providers.factory import ENERGY_SOURCES, build_resilient_provider
from mplacas.services.collection import CollectionResult, SolarCollectionService

logger = logging.getLogger(__name__)

COLLECTION_TASK_TYPE = "solar_daily"


async def run_solar_collection(
    *,
    target_date: date,
    plant_id,
    credentials: ProviderLogin,
    provider: str,
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
    except (ProviderRateLimitedError, ProviderAuthError) as exc:
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
