from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.core.authorization import PlantScope, UNRESTRICTED_PLANT_SCOPE
from mplacas.intelligence.executive_service import (
    build_executive_dashboard,
    build_executive_dashboard_for_bill,
)
from mplacas.reports.contract import MonthlyEnergyReport
from mplacas.reports.report_projection import project_executive_dashboard


async def _build_monthly_report(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    bill_id: uuid.UUID | None,
    expected_production_kwh: Decimal | None = None,
    stable_tolerance_percent: Decimal = Decimal("2.0"),
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> MonthlyEnergyReport:
    if bill_id is None:
        dashboard = await build_executive_dashboard(
            session,
            plant_id=plant_id,
            expected_production_kwh=expected_production_kwh,
            stable_tolerance_percent=stable_tolerance_percent,
            plant_scope=plant_scope,
        )
    else:
        dashboard = await build_executive_dashboard_for_bill(
            session,
            bill_id=bill_id,
            plant_id=plant_id,
            expected_production_kwh=expected_production_kwh,
            stable_tolerance_percent=stable_tolerance_percent,
            plant_scope=plant_scope,
        )
    return project_executive_dashboard(dashboard)


async def build_latest_monthly_report(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    expected_production_kwh: Decimal | None = None,
    stable_tolerance_percent: Decimal = Decimal("2.0"),
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> MonthlyEnergyReport:
    return await _build_monthly_report(
        session,
        plant_id=plant_id,
        bill_id=None,
        expected_production_kwh=expected_production_kwh,
        stable_tolerance_percent=stable_tolerance_percent,
        plant_scope=plant_scope,
    )


async def build_monthly_report_for_bill(
    session: AsyncSession,
    *,
    bill_id: uuid.UUID,
    plant_id: uuid.UUID,
    plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
) -> MonthlyEnergyReport:
    """Build a canonical report for one confirmed bill without caller-provided assumptions."""
    return await _build_monthly_report(
        session,
        plant_id=plant_id,
        bill_id=bill_id,
        expected_production_kwh=None,
        stable_tolerance_percent=Decimal("2.0"),
        plant_scope=plant_scope,
    )
