from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import CursorResult, delete
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.alerts.db_models import AlertDeliveryRecord
from mplacas.collection.db_models import CollectionTaskRecord, CollectionTaskStatus
from mplacas.events.db_models import OutboxEventRecord, OutboxEventStatus
from mplacas.operations.models import JobRun, JobStatus
from mplacas.orchestration.db_models import (
    PipelineExecutionRecord,
    PipelineExecutionStatus,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetentionOutcome:
    table: str
    deleted: int


@dataclass(frozen=True, slots=True)
class RetentionReport:
    outcomes: tuple[RetentionOutcome, ...]

    @property
    def total_deleted(self) -> int:
        return sum(outcome.deleted for outcome in self.outcomes)


@dataclass(frozen=True, slots=True)
class RetentionWindows:
    """Janelas de retenção por tabela, em dias.

    As janelas de log operacional são curtas; a do ledger de deduplicação de
    alertas é longa e conservadora, pois remover um fingerprint ainda relevante
    poderia permitir o reenvio de um alerta antigo.
    """

    job_runs_days: int = 90
    pipeline_executions_days: int = 90
    outbox_events_days: int = 30
    collection_tasks_days: int = 30
    alert_delivery_records_days: int = 365

    def __post_init__(self) -> None:
        for name, value in (
            ("job_runs_days", self.job_runs_days),
            ("pipeline_executions_days", self.pipeline_executions_days),
            ("outbox_events_days", self.outbox_events_days),
            ("collection_tasks_days", self.collection_tasks_days),
            ("alert_delivery_records_days", self.alert_delivery_records_days),
        ):
            if value < 1:
                raise ValueError(f"{name} must be at least 1 day")


class RetentionService:
    """Remove registros terminais e antigos de tabelas operacionais.

    Regras invioláveis:
    - nunca remove registros não terminais (em execução, pendentes ou em
      processamento);
    - nunca toca em dados de produção (`daily_energy`, observações climáticas,
      faturas): são o objeto da reconciliação, não log operacional;
    - opera por corte de tempo sobre um carimbo terminal, respeitando a janela
      específica de cada tabela.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def purge(
        self,
        *,
        windows: RetentionWindows | None = None,
        now: datetime | None = None,
    ) -> RetentionReport:
        windows = windows or RetentionWindows()
        current_time = now or datetime.now(UTC)
        outcomes: list[RetentionOutcome] = []

        outcomes.append(
            await self._purge_table(
                "job_runs",
                delete(JobRun).where(
                    JobRun.status.in_((JobStatus.SUCCEEDED, JobStatus.FAILED)),
                    JobRun.started_at < current_time - timedelta(days=windows.job_runs_days),
                ),
            )
        )
        outcomes.append(
            await self._purge_table(
                "pipeline_executions",
                delete(PipelineExecutionRecord).where(
                    PipelineExecutionRecord.status.in_(
                        (
                            PipelineExecutionStatus.SUCCEEDED,
                            PipelineExecutionStatus.FAILED,
                        )
                    ),
                    PipelineExecutionRecord.started_at
                    < current_time - timedelta(days=windows.pipeline_executions_days),
                ),
            )
        )
        outcomes.append(
            await self._purge_table(
                "outbox_events",
                delete(OutboxEventRecord).where(
                    OutboxEventRecord.status.in_(
                        (OutboxEventStatus.DELIVERED, OutboxEventStatus.FAILED)
                    ),
                    OutboxEventRecord.created_at
                    < current_time - timedelta(days=windows.outbox_events_days),
                ),
            )
        )
        outcomes.append(
            await self._purge_table(
                "collection_tasks",
                delete(CollectionTaskRecord).where(
                    CollectionTaskRecord.status.in_(
                        (CollectionTaskStatus.COMPLETED, CollectionTaskStatus.FAILED)
                    ),
                    CollectionTaskRecord.created_at
                    < current_time - timedelta(days=windows.collection_tasks_days),
                ),
            )
        )
        outcomes.append(
            await self._purge_table(
                "alert_delivery_records",
                delete(AlertDeliveryRecord).where(
                    AlertDeliveryRecord.sent_at
                    < current_time - timedelta(days=windows.alert_delivery_records_days),
                ),
            )
        )

        report = RetentionReport(outcomes=tuple(outcomes))
        logger.info(
            "retention_purge_completed",
            extra={
                "total_deleted": report.total_deleted,
                "by_table": {o.table: o.deleted for o in report.outcomes},
            },
        )
        return report

    async def _purge_table(self, table: str, statement) -> RetentionOutcome:
        result = await self._session.execute(statement)
        deleted = result.rowcount if isinstance(result, CursorResult) else 0
        return RetentionOutcome(table=table, deleted=deleted or 0)
