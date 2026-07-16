from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from mplacas.core.security import require_operations_read
from mplacas.db.session import SessionFactory
from mplacas.intelligence.cycle_service import EnergyCycleNotFoundError
from mplacas.reports.exporters import (
    PDF_MEDIA_TYPE,
    XLSX_MEDIA_TYPE,
    build_monthly_report_pdf,
    build_monthly_report_xlsx,
)
from mplacas.reports.service import (
    MonthlyEnergyReport,
    build_latest_monthly_report,
    monthly_report_to_csv,
    serialize_monthly_report,
)

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_operations_read)],
)


async def _build_report(
    *,
    plant_id: uuid.UUID,
    expected_production_kwh: Decimal | None,
    stable_tolerance_percent: Decimal,
) -> MonthlyEnergyReport:
    async with SessionFactory() as session:
        try:
            return await build_latest_monthly_report(
                session,
                plant_id=plant_id,
                expected_production_kwh=expected_production_kwh,
                stable_tolerance_percent=stable_tolerance_percent,
            )
        except EnergyCycleNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


def _download_headers(filename: str) -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
    }


@router.get("/monthly/latest")
async def latest_monthly_report(
    response: Response,
    plant_id: uuid.UUID = Query(...),
    expected_production_kwh: Decimal | None = Query(default=None, ge=0),
    stable_tolerance_percent: Decimal = Query(default=Decimal("2.0"), ge=0, le=100),
) -> dict[str, object]:
    report = await _build_report(
        plant_id=plant_id,
        expected_production_kwh=expected_production_kwh,
        stable_tolerance_percent=stable_tolerance_percent,
    )
    response.headers["Cache-Control"] = "no-store"
    return serialize_monthly_report(report)


@router.get("/monthly/latest.csv")
async def latest_monthly_report_csv(
    plant_id: uuid.UUID = Query(...),
    expected_production_kwh: Decimal | None = Query(default=None, ge=0),
    stable_tolerance_percent: Decimal = Query(default=Decimal("2.0"), ge=0, le=100),
) -> Response:
    report = await _build_report(
        plant_id=plant_id,
        expected_production_kwh=expected_production_kwh,
        stable_tolerance_percent=stable_tolerance_percent,
    )
    filename = f"mplacas-monthly-{report.reference_month}-{report.plant_id}.csv"
    return Response(
        content=monthly_report_to_csv(report),
        media_type="text/csv; charset=utf-8",
        headers=_download_headers(filename),
    )


@router.get("/monthly/latest.pdf")
async def latest_monthly_report_pdf(
    plant_id: uuid.UUID = Query(...),
    expected_production_kwh: Decimal | None = Query(default=None, ge=0),
    stable_tolerance_percent: Decimal = Query(default=Decimal("2.0"), ge=0, le=100),
) -> Response:
    report = await _build_report(
        plant_id=plant_id,
        expected_production_kwh=expected_production_kwh,
        stable_tolerance_percent=stable_tolerance_percent,
    )
    filename = f"mplacas-monthly-{report.reference_month}-{report.plant_id}.pdf"
    return Response(
        content=build_monthly_report_pdf(report),
        media_type=PDF_MEDIA_TYPE,
        headers=_download_headers(filename),
    )


@router.get("/monthly/latest.xlsx")
async def latest_monthly_report_xlsx(
    plant_id: uuid.UUID = Query(...),
    expected_production_kwh: Decimal | None = Query(default=None, ge=0),
    stable_tolerance_percent: Decimal = Query(default=Decimal("2.0"), ge=0, le=100),
) -> Response:
    report = await _build_report(
        plant_id=plant_id,
        expected_production_kwh=expected_production_kwh,
        stable_tolerance_percent=stable_tolerance_percent,
    )
    filename = f"mplacas-monthly-{report.reference_month}-{report.plant_id}.xlsx"
    return Response(
        content=build_monthly_report_xlsx(report),
        media_type=XLSX_MEDIA_TYPE,
        headers=_download_headers(filename),
    )
