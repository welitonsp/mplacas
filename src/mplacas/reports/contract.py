from __future__ import annotations

import uuid
from dataclasses import dataclass

REPORT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class ReportMetric:
    key: str
    label: str
    value: str
    unit: str | None
    nature: str
    source: str


@dataclass(frozen=True, slots=True)
class ReportDiagnostic:
    code: str
    severity: str
    message: str
    recommended_action: str


@dataclass(frozen=True, slots=True)
class ReportTrendMetric:
    key: str
    label: str
    absolute_delta: str
    unit: str
    percent_delta: str | None
    direction: str


@dataclass(frozen=True, slots=True)
class MonthlyReportTrend:
    current_reference_month: str
    previous_reference_month: str
    metrics: tuple[ReportTrendMetric, ...]
    diagnostics: tuple[ReportDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class MonthlyEnergyReport:
    schema_version: str
    calculation_version: str
    plant_id: uuid.UUID
    bill_id: uuid.UUID
    reference_month: str
    status: str
    headline: str
    metrics: tuple[ReportMetric, ...]
    quality: tuple[ReportMetric, ...]
    diagnostics: tuple[ReportDiagnostic, ...]
    priority_actions: tuple[str, ...]
    trend: MonthlyReportTrend | None
