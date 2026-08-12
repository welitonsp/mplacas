"""Read-only queries backing ``devices/router.py`` (ADR-074, Decision 3).

Composes `devices.metrics.gather_device_metrics` / `assess_devices` — the one
and only implementation of per-device production/rendimento and its
assessment — with a target-day resolution query and a device-level
unavailability taxonomy. No new calculation happens here (ADR-074 Restriction
7 / Decision 6): this module only orchestrates reads and derives which of the
three mutually exclusive reasons (`NOT_REPORTED`, `NO_IRRADIATION_READING`,
`INSUFFICIENT_DEVICE_HISTORY`) explains a device whose yield could not be
assessed.

Deliberately does **not** call `mplacas.alerts.production_alert.
gather_production_alert_metrics`: that function requires
`expected_daily_production_kwh` and raises `ProductionAlertDataNotFoundError`
when no device reported at all — exactly the day this endpoint most needs to
describe (ADR-074 Decision 4). It also never derives device health from
`DeviceYieldAssessment.dropped`, which is `False` both when a device is
healthy and when it could not be assessed at all — `UNKNOWN` is derived
solely from `relative_to_own_median is None` (ADR-074, "armadilha
obrigatória").

Like every other read service in the project, every public function here
expects the caller to have already opened a session with tenant context
applied (``set_principal_context``) before invoking it — this module adds no
authorization logic of its own, that is the router's job via
``core.tenancy.ReadPlant``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.models import DailyEnergy, Device
from mplacas.devices.metrics import (
    DEVICE_NORMAL_THRESHOLD,
    DeviceProductionMetrics,
    DeviceYieldAssessment,
    assess_devices,
    gather_device_metrics,
)

#: No `DailyEnergy` row exists anywhere for the plant, so there is no day to
#: report on at all.
NO_PRODUCTION_HISTORY_REASON = "NO_PRODUCTION_HISTORY"

#: No `DailyClimateObservationRecord` (or one with a null/non-positive
#: `irradiation_kwh_m2`) exists for the resolved `observation_date`.
NO_CLIMATE_OBSERVATION_REASON = "NO_CLIMATE_OBSERVATION"

#: The three per-device yield-unavailability reasons (ADR-074, Decision 3
#: taxonomy table) — mutually exclusive, checked in this priority order.
NOT_REPORTED_REASON = "NOT_REPORTED"
NO_IRRADIATION_READING_REASON = "NO_IRRADIATION_READING"
INSUFFICIENT_DEVICE_HISTORY_REASON = "INSUFFICIENT_DEVICE_HISTORY"

REPORTING_STATUS_REPORTED = "REPORTED"
REPORTING_STATUS_NOT_REPORTED = "NOT_REPORTED"

YIELD_STATUS_NORMAL = "NORMAL"
YIELD_STATUS_DROPPED = "DROPPED"
YIELD_STATUS_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class DeviceDailyStatus:
    """One inverter's reporting + yield status for the resolved day."""

    assessment: DeviceYieldAssessment
    reporting_status: str
    #: Most recent `production_date` this device ever reported, independent
    #: of the resolved `observation_date`. `None` when the device never
    #: reported at all.
    last_reported_date: date | None
    yield_status: str
    yield_unavailable_reason: str | None


@dataclass(frozen=True, slots=True)
class DailyStatusResult:
    plant_id: uuid.UUID
    #: Most recent date with any `DailyEnergy` row across the plant's
    #: devices. `None` when the plant has no production history at all.
    observation_date: date | None
    observation_date_unavailable_reason: str | None
    irradiation_kwh_m2: Decimal | None
    irradiation_unavailable_reason: str | None
    device_count: int
    reporting_device_count: int
    device_normal_threshold: Decimal
    devices: tuple[DeviceDailyStatus, ...]


async def _resolve_observation_date(session: AsyncSession, *, plant_id: uuid.UUID) -> date | None:
    """Most recent day with any `DailyEnergy` row for the plant's devices.

    No helper existed for this before ADR-074 (`grep -rn "max(DailyEnergy.
    production_date)" src/mplacas/` was empty when the ADR was written) — this
    is date resolution, not a new metric.
    """
    return await session.scalar(
        select(func.max(DailyEnergy.production_date))
        .join(Device, Device.id == DailyEnergy.device_id)
        .where(Device.plant_id == plant_id)
    )


async def _resolve_irradiation(
    session: AsyncSession, *, plant_id: uuid.UUID, observation_date: date
) -> Decimal | None:
    climate = await session.scalar(
        select(DailyClimateObservationRecord)
        .where(
            DailyClimateObservationRecord.plant_id == plant_id,
            DailyClimateObservationRecord.observation_date == observation_date,
        )
        .limit(1)
    )
    if climate is None or climate.irradiation_kwh_m2 is None or climate.irradiation_kwh_m2 <= 0:
        return None
    return climate.irradiation_kwh_m2


async def _resolve_last_reported_dates(
    session: AsyncSession, *, device_ids: tuple[uuid.UUID, ...]
) -> dict[uuid.UUID, date]:
    if not device_ids:
        return {}
    rows = (
        await session.execute(
            select(DailyEnergy.device_id, func.max(DailyEnergy.production_date))
            .where(DailyEnergy.device_id.in_(device_ids))
            .group_by(DailyEnergy.device_id)
        )
    ).all()
    return {device_id: last_date for device_id, last_date in rows}


def _derive_yield_unavailable_reason(
    device: DeviceProductionMetrics, irradiation: Decimal | None
) -> str:
    """Priority order fixed by the ADR-074 Decision 3 taxonomy table.

    Only called when `relative_to_own_median is None` for this device — i.e.
    it never runs for a device whose yield status is already known.
    """
    if device.production_kwh is None:
        return NOT_REPORTED_REASON
    if irradiation is None:
        return NO_IRRADIATION_READING_REASON
    return INSUFFICIENT_DEVICE_HISTORY_REASON


async def get_daily_status(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    device_normal_threshold: Decimal = DEVICE_NORMAL_THRESHOLD,
) -> DailyStatusResult:
    """Compose the per-inverter daily status payload. Always resolves.

    Never raises for a plant with no production/climate history — every
    unavailability is a field + reason (ADR-074 Restriction 3). A device with
    no `DailyEnergy` row for the resolved day still appears, with
    `reporting_status = "NOT_REPORTED"` (ADR-074 Restriction 1).
    """
    observation_date = await _resolve_observation_date(session, plant_id=plant_id)
    observation_date_reason = (
        None if observation_date is not None else NO_PRODUCTION_HISTORY_REASON
    )

    irradiation: Decimal | None = None
    irradiation_reason: str | None = NO_CLIMATE_OBSERVATION_REASON
    if observation_date is not None:
        irradiation = await _resolve_irradiation(
            session, plant_id=plant_id, observation_date=observation_date
        )
        irradiation_reason = None if irradiation is not None else NO_CLIMATE_OBSERVATION_REASON

    # `gather_device_metrics` needs a concrete `target_date` even when the
    # plant has no production history at all: with `observation_date is
    # None` there is, by construction, no `DailyEnergy` row for *any* date on
    # this plant, so the specific date passed here cannot change which
    # devices report — it only has to be a valid date for the query.
    target_date = observation_date if observation_date is not None else date.today()

    metrics = await gather_device_metrics(
        session,
        plant_id=plant_id,
        target_date=target_date,
        irradiation=irradiation,
    )
    assessed = assess_devices(metrics, device_normal_threshold)

    device_ids = tuple(device.device_id for device in metrics)
    last_reported_by_device = await _resolve_last_reported_dates(session, device_ids=device_ids)

    statuses: list[DeviceDailyStatus] = []
    for assessment in assessed:
        device = assessment.device
        reporting_status = (
            REPORTING_STATUS_REPORTED
            if device.production_kwh is not None
            else REPORTING_STATUS_NOT_REPORTED
        )
        if assessment.relative_to_own_median is not None:
            # Health is derived from `relative_to_own_median`, never from
            # `assessment.dropped` alone — `dropped` is `False` both when a
            # device is healthy and when it could not be assessed
            # (ADR-074, "armadilha obrigatória").
            yield_status = YIELD_STATUS_DROPPED if assessment.dropped else YIELD_STATUS_NORMAL
            yield_reason = None
        else:
            yield_status = YIELD_STATUS_UNKNOWN
            yield_reason = _derive_yield_unavailable_reason(device, irradiation)
        statuses.append(
            DeviceDailyStatus(
                assessment=assessment,
                reporting_status=reporting_status,
                last_reported_date=last_reported_by_device.get(device.device_id),
                yield_status=yield_status,
                yield_unavailable_reason=yield_reason,
            )
        )

    reporting_device_count = sum(
        1 for status in statuses if status.reporting_status == REPORTING_STATUS_REPORTED
    )

    return DailyStatusResult(
        plant_id=plant_id,
        observation_date=observation_date,
        observation_date_unavailable_reason=observation_date_reason,
        irradiation_kwh_m2=irradiation,
        irradiation_unavailable_reason=irradiation_reason,
        device_count=len(statuses),
        reporting_device_count=reporting_device_count,
        device_normal_threshold=device_normal_threshold,
        devices=tuple(statuses),
    )
