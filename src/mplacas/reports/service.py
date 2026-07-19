"""Compatibility facade for the monthly report public API.

New code should import contracts, projection, and serialization from their focused modules.
"""

from mplacas.reports.contract import (
    REPORT_SCHEMA_VERSION,
    MonthlyEnergyReport,
    MonthlyReportTrend,
    ReportDiagnostic,
    ReportMetric,
    ReportTrendMetric,
)
from mplacas.reports.projection import (
    build_latest_monthly_report,
    build_monthly_report_for_bill,
)
from mplacas.reports.serialization import monthly_report_to_csv, serialize_monthly_report

__all__ = [
    "REPORT_SCHEMA_VERSION",
    "MonthlyEnergyReport",
    "MonthlyReportTrend",
    "ReportDiagnostic",
    "ReportMetric",
    "ReportTrendMetric",
    "build_latest_monthly_report",
    "build_monthly_report_for_bill",
    "monthly_report_to_csv",
    "serialize_monthly_report",
]
