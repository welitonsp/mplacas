from __future__ import annotations

import logging
from datetime import date

from mplacas.collection.queue import CollectionQueueRepository
from mplacas.core.config import get_settings
from mplacas.db.session import SessionFactory
from mplacas.providers.base import ProviderError
from mplacas.providers.nepviewer.factory import build_resilient_nepviewer
from mplacas.services.collection import CollectionResult, SolarCollectionService

logger = logging.getLogger(__name__)

COLLECTION_TASK_TYPE = "solar_daily"


async def run_solar_collection(
    *,
    target_date: date,
    plant_id,
    plant_name: str,
) -> CollectionResult | None:
    """Coleta a produção diária das placas com resiliência e reagendamento.

    Monta o provedor NEPViewer já envolvido pela camada de retry/detecção de
    dados incompletos. Se, mesmo após o retry, a API seguir indisponível ou
    incompleta, a coleta do dia é enfileirada para nova tentativa posterior,
    em vez de falhar em definitivo.
    """
    settings = get_settings()
    if settings.nep_account is None or settings.nep_password is None:
        raise RuntimeError("NEPViewer credentials must be configured for solar collection")

    client, provider = build_resilient_nepviewer(
        account=settings.nep_account,
        password=settings.nep_password.get_secret_value(),
        base_url=str(settings.nep_base_url),
        timeout_seconds=settings.request_timeout_seconds,
    )
    try:
        async with SessionFactory() as session:
            service = SolarCollectionService(session, provider)
            result = await service.collect(
                plant_name=plant_name,
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


async def _enqueue_retry(*, plant_id, target_date: date) -> None:
    async with SessionFactory() as session:
        await CollectionQueueRepository(session).enqueue(
            plant_id=plant_id,
            task_type=COLLECTION_TASK_TYPE,
            target_date=target_date.isoformat(),
        )
        await session.commit()
