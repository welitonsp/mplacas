"""Drain worker for async report export tasks."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from mplacas.core.authorization import UNRESTRICTED_PLANT_SCOPE
from mplacas.db.session import SessionFactory
from mplacas.reports.export_service import ReportExportService
from mplacas.reports.exporters import (
    PDF_MEDIA_TYPE,
    XLSX_MEDIA_TYPE,
    build_monthly_report_pdf,
    build_monthly_report_xlsx,
)
from mplacas.reports.snapshot import get_or_materialize_latest_monthly_report_snapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExportDrainResult:
    claimed: int
    completed: int
    failed: int


async def drain_report_exports(*, batch_size: int = 10) -> ExportDrainResult:
    """Claim pending export tasks and process them, one transaction per task."""
    task_ids = await _claim_batch(batch_size)
    completed = failed = 0

    for task_id in task_ids:
        try:
            await _process_task(task_id)
            completed += 1
        except Exception as exc:
            logger.error(
                "report_export_task_failed",
                extra={"task_id": str(task_id), "error": str(exc)},
            )
            await _fail_task(task_id, error_message=str(exc))
            failed += 1

    logger.info(
        "report_export_drain_completed",
        extra={"claimed": len(task_ids), "completed": completed, "failed": failed},
    )
    return ExportDrainResult(claimed=len(task_ids), completed=completed, failed=failed)


async def _claim_batch(batch_size: int) -> list[uuid.UUID]:
    async with SessionFactory() as session:
        service = ReportExportService(session)
        ids = await service.pending_ids(limit=batch_size)
        for task_id in ids:
            await service.claim(task_id)
        await session.commit()
    return ids


async def _process_task(task_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        service = ReportExportService(session)
        task = await service.get(task_id)
        if task is None or task.status != "processing":
            return

        plant_id = task.plant_id
        await session.commit()

    async with SessionFactory() as session:
        snapshot = await get_or_materialize_latest_monthly_report_snapshot(
            session,
            plant_id=plant_id,
            plant_scope=UNRESTRICTED_PLANT_SCOPE,
        )
        await session.commit()

    report = snapshot.report
    if task.format == "pdf":
        artifact_bytes = build_monthly_report_pdf(report)
        content_type = PDF_MEDIA_TYPE
    else:
        artifact_bytes = build_monthly_report_xlsx(report)
        content_type = XLSX_MEDIA_TYPE

    async with SessionFactory() as session:
        await ReportExportService(session).mark_completed(
            task_id,
            artifact_bytes=artifact_bytes,
            artifact_content_type=content_type,
            artifact_url=None,
        )
        await session.commit()


async def _fail_task(task_id: uuid.UUID, *, error_message: str) -> None:
    try:
        async with SessionFactory() as session:
            await ReportExportService(session).mark_failed(
                task_id,
                error_message=error_message,
            )
            await session.commit()
    except Exception as exc:
        logger.error(
            "report_export_task_fail_record_failed",
            extra={"task_id": str(task_id), "error": str(exc)},
        )
