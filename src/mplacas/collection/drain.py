from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.collection.job import COLLECTION_TASK_TYPE
from mplacas.collection.queue import CollectionTask
from mplacas.collection.worker import CollectionWorker, WorkerResult
from mplacas.core.config import get_settings
from mplacas.core.secret_box import SecretBox, secret_box_from_settings
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_platform_context
from mplacas.providers.accounts import ProviderAccountService
from mplacas.providers.db_models import ProviderAccountRecord
from mplacas.providers.nepviewer.factory import build_resilient_nepviewer
from mplacas.services.collection import SolarCollectionService

logger = logging.getLogger(__name__)


def build_collection_handler():
    """Cria o handler que o worker usa para reprocessar um dia deferido.

    O handler roda a coleta na sessão do worker (``collect_in_session``), sem
    gerenciar a transação: o commit/rollback fica com o worker, uma transação
    por tarefa. Um novo provedor resiliente é montado por tarefa e fechado ao
    final, garantindo que uma tarefa não vaze estado para outra.

    A credencial vem só da conexão da usina da tarefa (ADR-091). Usina sem
    conexão falha e o worker reagenda.
    """
    settings = get_settings()
    base_url = str(settings.nep_base_url)
    timeout = settings.request_timeout_seconds
    box_holder: list[SecretBox] = []

    def _box() -> SecretBox:
        if not box_holder:
            box_holder.append(secret_box_from_settings())
        return box_holder[0]

    async def handler(session: AsyncSession, task: CollectionTask) -> None:
        # Garante a leitura de provider_accounts sob RLS mesmo se a sessão
        # vier de outra fábrica (ver _platform_session).
        await set_platform_context(session)
        target = date.fromisoformat(task.target_date)
        record = await session.scalar(
            select(ProviderAccountRecord).where(
                ProviderAccountRecord.plant_id == task.plant_id,
                ProviderAccountRecord.active.is_(True),
            )
        )
        if record is None:
            raise RuntimeError("plant has no provider account for collection")
        credentials = ProviderAccountService(session, _box()).open(record)
        client, provider = build_resilient_nepviewer(
            account=credentials.login,
            password=credentials.password,
            base_url=base_url,
            timeout_seconds=timeout,
        )
        try:
            service = SolarCollectionService(session, provider)
            await service.collect_in_session(
                plant_id=task.plant_id,
                start=target,
                end=target,
                consolidate_through=target,
                expect_complete=True,
            )
        finally:
            await client.aclose()

    return handler


@asynccontextmanager
async def _platform_session():
    """Sessão do worker já no contexto de plataforma (RLS forçado no PostgreSQL).

    O contexto é reaplicado a cada transação pelo listener de
    ``db.tenant_context``, então vale para o claim, o handler e o reagendamento.
    """
    async with SessionFactory() as session:
        await set_platform_context(session)
        yield session


async def _has_active_provider_accounts() -> bool:
    async with SessionFactory() as session:
        await set_platform_context(session)
        found = await session.scalar(
            select(ProviderAccountRecord.id).where(ProviderAccountRecord.active.is_(True)).limit(1)
        )
    return found is not None


async def drain_collection_queue(
    *,
    max_attempts: int = 10,
    limit: int = 100,
) -> WorkerResult:
    """Drena a fila de coleta, reprocessando dias deferidos.

    Cada tarefa é isolada: uma que falhe de novo é reagendada com backoff (ou
    marcada como falha após o máximo de tentativas) sem afetar as demais.
    """
    if not await _has_active_provider_accounts():
        # A coleta diária já falha visivelmente neste caso; aqui só registra.
        logger.error("collection_drain_no_active_accounts")
        return WorkerResult(claimed=0, completed=0, rescheduled=0, failed=0)
    # Com conexões, a chave é obrigatória: falha já, em vez de reagendar.
    secret_box_from_settings()
    handler = build_collection_handler()
    worker = CollectionWorker(
        _platform_session,
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
