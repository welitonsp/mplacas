from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RlsScope(StrEnum):
    ORGANIZATION = "organization"
    PLANT = "plant"
    DEVICE = "device"
    DAILY_ENERGY = "daily_energy"
    PLATFORM = "platform"


@dataclass(frozen=True, slots=True)
class RlsTable:
    scope: RlsScope
    ownership_column: str | None = None


RLS_TABLES: dict[str, RlsTable] = {
    "organizations": RlsTable(RlsScope.ORGANIZATION, "id"),
    "plants": RlsTable(RlsScope.ORGANIZATION, "organization_id"),
    "api_credentials": RlsTable(RlsScope.ORGANIZATION, "organization_id"),
    "auth_sessions": RlsTable(RlsScope.ORGANIZATION, "organization_id"),
    "operational_users": RlsTable(RlsScope.ORGANIZATION, "organization_id"),
    "user_invitations": RlsTable(RlsScope.ORGANIZATION, "organization_id"),
    "collection_tasks": RlsTable(RlsScope.PLANT, "plant_id"),
    "daily_climate_observations": RlsTable(RlsScope.PLANT, "plant_id"),
    "daily_pv_loss_assessments": RlsTable(RlsScope.PLANT, "plant_id"),
    "daily_pv_performance_results": RlsTable(RlsScope.PLANT, "plant_id"),
    "daily_solar_model_results": RlsTable(RlsScope.PLANT, "plant_id"),
    "devices": RlsTable(RlsScope.PLANT, "plant_id"),
    "monthly_report_snapshots": RlsTable(RlsScope.PLANT, "plant_id"),
    "outbox_events": RlsTable(RlsScope.PLANT, "plant_id"),
    "pipeline_executions": RlsTable(RlsScope.PLANT, "plant_id"),
    "report_export_tasks": RlsTable(RlsScope.PLANT, "plant_id"),
    "seasonal_pv_baseline_results": RlsTable(RlsScope.PLANT, "plant_id"),
    "utility_bills": RlsTable(RlsScope.PLANT, "plant_id"),
    "daily_energy": RlsTable(RlsScope.DEVICE, "device_id"),
    "daily_energy_versions": RlsTable(RlsScope.DAILY_ENERGY, "daily_energy_id"),
    "alert_delivery_records": RlsTable(RlsScope.PLATFORM),
    "audit_events": RlsTable(RlsScope.PLATFORM),
    "job_runs": RlsTable(RlsScope.PLATFORM),
    "login_rate_limits": RlsTable(RlsScope.PLATFORM),
}


def application_rls_tables() -> frozenset[str]:
    return frozenset(RLS_TABLES)
