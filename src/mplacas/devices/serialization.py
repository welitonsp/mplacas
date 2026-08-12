"""Pure dict serialization for the devices read router (ADR-074, Decision 3).

No I/O here — every function takes an already-loaded result from
``read_service.py`` and returns a plain ``dict``. ``Decimal`` is serialized as
``str`` to avoid precision loss, dates use ISO-8601, and nullable fields are
always present in the output (never omitted), even when their value is
``None`` — the same convention as ``photovoltaic/serialization.py``.
"""

from __future__ import annotations

from decimal import Decimal

from mplacas.devices.read_service import DailyStatusResult, DeviceDailyStatus

#: ADR-074, Decision 3 envelope. Fixed here so the frontend never has to know
#: the units out of band.
UNITS: dict[str, str] = {
    "production": "kWh",
    "irradiation": "kWh/m2",
    "rendimento": "kWh/(kWh/m2)",
    "relative_to_own_median": "ratio",
    # Same naming convention as `photovoltaic/serialization.py:BASELINE_UNITS`
    # (`"degradation": "percent"` for the field `degradation_percent`): the
    # units key drops the `_percent` suffix already carried by the field name.
    "relative_to_own_median_deviation": "percent",
}


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def serialize_device(status: DeviceDailyStatus) -> dict[str, object]:
    """Serialize one device entry per ADR-074, Decision 3.

    Identified by ``serial_number`` only — never an invented ordinal
    (ADR-074, Decision 7 / Restriction: the serial is the stable identity,
    an alphabetical position is not).
    """
    device = status.assessment.device
    return {
        "device_id": str(device.device_id),
        "serial_number": device.serial_number,
        "reporting_status": status.reporting_status,
        "production_kwh": _decimal(device.production_kwh),
        "last_reported_date": (
            status.last_reported_date.isoformat() if status.last_reported_date is not None else None
        ),
        "rendimento": _decimal(device.rendimento),
        "rendimento_median": _decimal(device.rendimento_median),
        "relative_to_own_median": _decimal(status.assessment.relative_to_own_median),
        # Percent deviation from this inverter's own median, ready to render —
        # ADR-074 correction (P1 review of T1c, 2026-08-12): the frontend used
        # to compute `(ratio - 1) * 100` itself; that shifts the reference
        # point away from zero and is domain math, not presentation, so it
        # moved to `devices/metrics.py::assess_devices`.
        "relative_to_own_median_deviation_percent": _decimal(
            status.assessment.relative_to_own_median_deviation_percent
        ),
        "yield_status": status.yield_status,
        "yield_unavailable_reason": status.yield_unavailable_reason,
    }


def serialize_daily_status(result: DailyStatusResult) -> dict[str, object]:
    """Serialize the full envelope per ADR-074, Decision 3.

    Device order is preserved as returned by ``get_daily_status`` — stable
    ``serial_number`` order, never reordered by performance (ADR-074
    Restriction 2).
    """
    return {
        "plant_id": str(result.plant_id),
        "observation_date": (
            result.observation_date.isoformat() if result.observation_date is not None else None
        ),
        "observation_date_unavailable_reason": result.observation_date_unavailable_reason,
        "irradiation_kwh_m2": _decimal(result.irradiation_kwh_m2),
        "irradiation_unavailable_reason": result.irradiation_unavailable_reason,
        "device_count": result.device_count,
        "reporting_device_count": result.reporting_device_count,
        "device_normal_threshold": _decimal(result.device_normal_threshold),
        "units": dict(UNITS),
        "devices": [serialize_device(device) for device in result.devices],
    }
