from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from mplacas.core.security import OperationsPrincipal, require_operations_read
from mplacas.audit.repository import AuditEventRepository
from mplacas.core.tenancy import AdminPlant, ReadPlant
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_principal_context
from mplacas.intelligence.cycle_service import EnergyCycleNotFoundError
from mplacas.reports.contract import MonthlyEnergyReport
from mplacas.reports.export_service import InvalidExportFormat, ReportExportService
from mplacas.reports.exporters import (
    PDF_MEDIA_TYPE,
    XLSX_MEDIA_TYPE,
    build_monthly_report_pdf,
    build_monthly_report_xlsx,
)
from mplacas.reports.history_service import (
    DEFAULT_HISTORY_CYCLES,
    MAX_HISTORY_CYCLES,
    load_monthly_production_history,
    load_recent_monthly_reports,
)
from mplacas.reports.serialization import (
    monthly_report_to_csv,
    serialize_monthly_report,
)
from mplacas.reports.savings_gaps import (
    ReprocessResult,
    SavingsGap,
    list_savings_gaps,
    reprocess_savings_gaps,
)
from mplacas.reports.snapshot import (
    MonthlyReportSnapshot,
    get_or_materialize_latest_monthly_report_snapshot,
)

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
)


async def _build_report(
    *,
    plant_id: uuid.UUID,
    expected_production_kwh: Decimal | None,
    stable_tolerance_percent: Decimal,
    principal: OperationsPrincipal,
) -> MonthlyReportSnapshot:
    # Legacy tuning parameters are intentionally ignored: snapshots use canonical assumptions.
    del expected_production_kwh, stable_tolerance_percent
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        try:
            snapshot = await get_or_materialize_latest_monthly_report_snapshot(
                session,
                plant_id=plant_id,
                plant_scope=principal.plant_scope,
            )
            await session.commit()
            return snapshot
        except EnergyCycleNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _build_report_with_history(
    *,
    plant_id: uuid.UUID,
    principal: OperationsPrincipal,
) -> tuple[MonthlyReportSnapshot, tuple[MonthlyEnergyReport, ...]]:
    """Snapshot do ciclo mais recente e os relatórios gravados anteriores (PDF)."""
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        try:
            snapshot = await get_or_materialize_latest_monthly_report_snapshot(
                session,
                plant_id=plant_id,
                plant_scope=principal.plant_scope,
            )
        except EnergyCycleNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        history = await load_recent_monthly_reports(
            session,
            plant_id=plant_id,
            plant_scope=principal.plant_scope,
        )
        await session.commit()
    return snapshot, history


def _snapshot_headers(snapshot: MonthlyReportSnapshot) -> dict[str, str]:
    return {
        "ETag": f'"{snapshot.payload_sha256}"',
        "X-Mplacas-Report-Snapshot": str(snapshot.id),
    }


def _download_headers(
    filename: str,
    *,
    snapshot: MonthlyReportSnapshot,
) -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        **_snapshot_headers(snapshot),
    }


@router.get("/monthly/latest")
async def latest_monthly_report(
    response: Response,
    scoped: ReadPlant,
    expected_production_kwh: Decimal | None = Query(default=None, ge=0, deprecated=True),
    stable_tolerance_percent: Decimal = Query(
        default=Decimal("2.0"), ge=0, le=100, deprecated=True
    ),
) -> dict[str, object]:
    snapshot = await _build_report(
        plant_id=scoped.plant_id,
        expected_production_kwh=expected_production_kwh,
        stable_tolerance_percent=stable_tolerance_percent,
        principal=scoped.principal,
    )
    response.headers["Cache-Control"] = "no-store"
    for key, value in _snapshot_headers(snapshot).items():
        response.headers[key] = value
    return serialize_monthly_report(snapshot.report)


@router.get("/monthly/latest.csv")
async def latest_monthly_report_csv(
    scoped: ReadPlant,
    expected_production_kwh: Decimal | None = Query(default=None, ge=0, deprecated=True),
    stable_tolerance_percent: Decimal = Query(
        default=Decimal("2.0"), ge=0, le=100, deprecated=True
    ),
) -> Response:
    snapshot = await _build_report(
        plant_id=scoped.plant_id,
        expected_production_kwh=expected_production_kwh,
        stable_tolerance_percent=stable_tolerance_percent,
        principal=scoped.principal,
    )
    report = snapshot.report
    filename = f"mplacas-monthly-{report.reference_month}-{report.plant_id}.csv"
    return Response(
        content=monthly_report_to_csv(report),
        media_type="text/csv; charset=utf-8",
        headers=_download_headers(filename, snapshot=snapshot),
    )


@router.get("/monthly/latest.pdf")
async def latest_monthly_report_pdf(
    scoped: ReadPlant,
    expected_production_kwh: Decimal | None = Query(default=None, ge=0, deprecated=True),
    stable_tolerance_percent: Decimal = Query(
        default=Decimal("2.0"), ge=0, le=100, deprecated=True
    ),
) -> Response:
    # Parâmetros legados ignorados, como em _build_report.
    del expected_production_kwh, stable_tolerance_percent
    snapshot, history = await _build_report_with_history(
        plant_id=scoped.plant_id,
        principal=scoped.principal,
    )
    report = snapshot.report
    filename = f"mplacas-monthly-{report.reference_month}-{report.plant_id}.pdf"
    return Response(
        content=build_monthly_report_pdf(report, history=history),
        media_type=PDF_MEDIA_TYPE,
        headers=_download_headers(filename, snapshot=snapshot),
    )


@router.get("/monthly/latest.xlsx")
async def latest_monthly_report_xlsx(
    scoped: ReadPlant,
    expected_production_kwh: Decimal | None = Query(default=None, ge=0, deprecated=True),
    stable_tolerance_percent: Decimal = Query(
        default=Decimal("2.0"), ge=0, le=100, deprecated=True
    ),
) -> Response:
    snapshot = await _build_report(
        plant_id=scoped.plant_id,
        expected_production_kwh=expected_production_kwh,
        stable_tolerance_percent=stable_tolerance_percent,
        principal=scoped.principal,
    )
    report = snapshot.report
    filename = f"mplacas-monthly-{report.reference_month}-{report.plant_id}.xlsx"
    return Response(
        content=build_monthly_report_xlsx(report),
        media_type=XLSX_MEDIA_TYPE,
        headers=_download_headers(filename, snapshot=snapshot),
    )


@router.get("/monthly/history")
async def monthly_report_history(
    response: Response,
    scoped: ReadPlant,
    limit: int = Query(default=DEFAULT_HISTORY_CYCLES, ge=1, le=MAX_HISTORY_CYCLES),
) -> dict[str, object]:
    # Unlike /monthly/latest, this endpoint never materializes a snapshot: it
    # is a strict read of already-closed cycles for a chart, so a plant with
    # no confirmed bill yet returns 200 with cycles: [], never 404.
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        payload = await load_monthly_production_history(
            session,
            plant_id=scoped.plant_id,
            plant_scope=scoped.principal.plant_scope,
            limit=limit,
        )
    response.headers["Cache-Control"] = "no-store"
    return payload


# ---------------------------------------------------------------------------
# Meses sem economia calculada (ADR-081)
# ---------------------------------------------------------------------------


def _serialize_gap(gap: SavingsGap) -> dict[str, object]:
    return {
        "bill_id": str(gap.bill_id),
        "reference_month": gap.reference_month,
        "cause": gap.cause.value,
        "savings_unavailable_reason": gap.savings_unavailable_reason,
    }


def _serialize_reprocess(result: ReprocessResult) -> dict[str, object]:
    return {
        "bill_id": str(result.bill_id),
        "reference_month": result.reference_month,
        "previous_cause": result.previous_cause.value,
        "outcome": result.outcome.value,
        "estimated_savings_brl": result.estimated_savings_brl,
        "savings_unavailable_reason": result.savings_unavailable_reason,
        "stored_revision": result.stored_revision,
    }


@router.get("/monthly/savings-gaps")
async def monthly_savings_gaps(response: Response, scoped: ReadPlant) -> dict[str, object]:
    """Faturas confirmadas cujo relatório não entrega economia. Leitura pura."""
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        gaps = await list_savings_gaps(
            session,
            plant_id=scoped.plant_id,
            plant_scope=scoped.principal.plant_scope,
        )
    response.headers["Cache-Control"] = "no-store"
    return {"count": len(gaps), "items": [_serialize_gap(gap) for gap in gaps]}


@router.post("/monthly/savings-gaps/reprocess")
async def reprocess_monthly_savings_gaps(
    request: Request,
    response: Response,
    scoped: AdminPlant,
) -> dict[str, object]:
    """Refaz o relatório dos meses sem economia, como nova revisão (ADMIN)."""
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        results = await reprocess_savings_gaps(
            session,
            plant_id=scoped.plant_id,
            plant_scope=scoped.principal.plant_scope,
        )
        stored = [result for result in results if result.stored_revision is not None]
        await AuditEventRepository(session).record(
            request,
            action="reports.reprocess_savings",
            resource_type="plant",
            resource_id=str(scoped.plant_id),
            outcome="SUCCEEDED",
            details={
                "plant_id": str(scoped.plant_id),
                "gaps": len(results),
                "revisions": [
                    {
                        "reference_month": result.reference_month,
                        "bill_id": str(result.bill_id),
                        "revision": result.stored_revision,
                        "snapshot_id": str(result.snapshot_id),
                        "outcome": result.outcome.value,
                    }
                    for result in stored
                ],
            },
        )
        await session.commit()
    response.headers["Cache-Control"] = "no-store"
    return {
        "count": len(results),
        "recalculated": sum(1 for r in results if r.outcome.value == "RECALCULATED"),
        "items": [_serialize_reprocess(result) for result in results],
    }


# ---------------------------------------------------------------------------
# Async export endpoints
# ---------------------------------------------------------------------------


@router.post("/monthly/exports", status_code=202)
async def enqueue_monthly_export(
    scoped: ReadPlant,
    format: str = Query(default="pdf", pattern="^(pdf|xlsx)$"),
) -> dict[str, object]:
    """Enqueue an async export task. Poll GET /monthly/exports/{task_id} for status."""
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        try:
            task = await ReportExportService(session).enqueue(
                plant_id=scoped.plant_id,
                reference_month="latest",
                format=format,
            )
        except InvalidExportFormat as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await session.commit()
        return {
            "task_id": str(task.id),
            "plant_id": str(task.plant_id),
            "format": task.format,
            "status": task.status,
            "created_at": task.created_at.isoformat(),
        }


@router.get("/monthly/exports/{task_id}")
async def get_export_task(
    task_id: uuid.UUID,
    principal: Annotated[OperationsPrincipal, Depends(require_operations_read)],
) -> dict[str, object]:
    """Poll the status of an async export task."""
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        task = await ReportExportService(session).get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="export task not found")
    principal.require_plant_access(task.plant_id)

    result: dict[str, object] = {
        "task_id": str(task.id),
        "plant_id": str(task.plant_id),
        "format": task.format,
        "status": task.status,
        "created_at": task.created_at.isoformat(),
    }
    if task.completed_at is not None:
        result["completed_at"] = task.completed_at.isoformat()
    if task.status == "completed":
        if task.artifact_url is not None:
            result["download_url"] = task.artifact_url
        else:
            result["download_url"] = f"/reports/monthly/exports/{task_id}/download"
    if task.status == "failed" and task.error_message:
        result["error"] = task.error_message
    return result


@router.get("/monthly/exports/{task_id}/download")
async def download_export_artifact(
    task_id: uuid.UUID,
    principal: Annotated[OperationsPrincipal, Depends(require_operations_read)],
) -> Response:
    """Stream the artifact bytes for a completed export task."""
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        task = await ReportExportService(session).get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="export task not found")
    principal.require_plant_access(task.plant_id)
    if task.status != "completed":
        raise HTTPException(status_code=409, detail=f"export task status is {task.status!r}")
    if task.artifact_bytes is None:
        raise HTTPException(status_code=404, detail="artifact bytes not available locally")

    ext = task.format
    filename = f"mplacas-export-{task.plant_id}-{task_id}.{ext}"
    return Response(
        content=task.artifact_bytes,
        media_type=task.artifact_content_type or "application/octet-stream",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
