from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.collection.job import COLLECTION_TASK_TYPE
from mplacas.collection.queue import CollectionTask
from mplacas.collection.worker import CollectionWorker, WorkerResult
from mplacas.core.config import get_settings
from mplacas.db.session import SessionFactory
from mplacas.providers.nepviewer.factory import build_resilient_nepviewer
from mplacas.services.collection import SolarCollectionService

logger = logging.getLogger(__name__)


def build_collection_handler(*, plant_name: str):
    """Cria o handler que o worker usa para reprocessar um dia deferido.

    O handler roda a coleta na sessão do worker (``collect_in_session``), sem
    gerenciar a transação: o commit/rollback fica com o worker, uma transação
    por tarefa. Um novo provedor resiliente é montado por tarefa e fechado ao
    final, garantindo que uma tarefa não vaze estado para outra.
    """
    settings = get_settings()
    if settings.nep_account is None or settings.nep_password is None:
        raise RuntimeError("NEPViewer credentials must be configured for collection drain")
    account = settings.nep_account
    password = settings.nep_password.get_secret_value()
    base_url = str(settings.nep_base_url)
    timeout = settings.request_timeout_seconds

    async def handler(session: AsyncSession, task: CollectionTask) -> None:
        target = date.fromisoformat(task.target_date)
        client, provider = build_resilient_nepviewer(
            account=account,
            password=password,
            base_url=base_url,
            timeout_seconds=timeout,
        )
        try:
            service = SolarCollectionService(session, provider)
            await service.collect_in_session(
                plant_name=plant_name,
                start=target,
                end=target,
                consolidate_through=target,
                expect_complete=True,
            )
        finally:
            await client.aclose()

    return handler


async def drain_collection_queue(
    *,
    plant_name: str,
    max_attempts: int = 10,
    limit: int = 100,
) -> WorkerResult:
    """Drena a fila de coleta, reprocessando dias deferidos.

    Cada tarefa é isolada: uma que falhe de novo é reagendada com backoff (ou
    marcada como falha após o máximo de tentativas) sem afetar as demais.
    """
    handler = build_collection_handler(plant_name=plant_name)
    worker = CollectionWorker(
        SessionFactory,
        task_type=COLLECTION_TASK_TYPE,
        handler=handler,
        max_attempts=max_attempts,
    )
    result = await worker.run_once(limit=limit)
    logger.info(
        "collection_drain_completed",
        extra={
            "claimed": result.claimed,
            "completed": result.completed,
            "rescheduled": result.rescheduled,
            "failed": result.failed,
        },
    )
    return result
