"""Per-inverter production and rendimento metrics.

Moved from `mplacas.alerts.production_alert` (ADR-074, Decision 2) without
altering any function body. This module owns the one and only implementation
of the per-device rendimento median and its assessment, so the alert path
(`mplacas.alerts.production_alert`) and any future read path never diverge.

`assess_devices` gained one addition on top of that pure move (2026-08-12,
ADR-074 correction, P1 review of T1c): `DeviceYieldAssessment.
relative_to_own_median_deviation_percent`, the percent-deviation reading that
`devices/read_service.py` exposes for `DeviceStatusSection.tsx` — see the
field docstring below. Nothing else in this module changed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.models import DailyEnergy, Device

#: How many days before the target date feed the local irradiation/rendimento
#: medians. Matches `mplacas.reports.daily_digest.RENDIMENTO_LOOKBACK_DAYS`.
RENDIMENTO_LOOKBACK_DAYS = 30

#: Same idea as `RENDIMENTO_NORMAL_THRESHOLD`, applied per inverter against
#: its own historical median (inverters have different chronic baselines and
#: must never be compared against each other, only against themselves).
DEVICE_NORMAL_THRESHOLD = Decimal("0.85")

#: Same reasoning as `mplacas.intelligence.anomaly_engine.
#: DEFAULT_MINIMUM_IRRADIATION_SAMPLE_DAYS`: a rendimento median built from
#: too few historical days is unstable, and a single noisy day can swing it
#: enough to look like a chronic baseline. Since a per-device drop now
#: outranks the weather explanation (see `assess_production_alert`), an
#: unstable one- or two-day "median" is a direct path for ordinary cloudy-day
#: noise to be misread as equipment failure. Five days matches the
#: irradiation floor for the same reason.
MINIMUM_RENDIMENTO_SAMPLE_DAYS = 5


@dataclass(frozen=True, slots=True)
class DeviceProductionMetrics:
    """A single inverter's production and rendimento for the target day."""

    device_id: uuid.UUID
    serial_number: str
    #: `None` when the inverter reported no `DailyEnergy` row at all for the
    #: target day (lost communication) — never inferred as zero, since zero
    #: production and no data are different facts and the message must not
    #: conflate them (see `_device_lines`, "sem dados").
    production_kwh: Decimal | None
    #: production_kwh / plant irradiation for the target day. `None` when
    #: there is no irradiation reading, or no production reading, to divide.
    rendimento: Decimal | None
    #: This device's own historical rendimento median — never another
    #: device's, since inverters have different chronic baselines.
    rendimento_median: Decimal | None


@dataclass(frozen=True, slots=True)
class DeviceYieldAssessment:
    device: DeviceProductionMetrics
    #: device.rendimento / device.rendimento_median. `None` when either side
    #: is unavailable — never invented.
    relative_to_own_median: Decimal | None
    #: `(relative_to_own_median - 1) * 100` — the same ratio re-expressed as a
    #: percent deviation from this inverter's own median (1 = exactly the
    #: median, so the deviation is 0). Added 2026-08-12 (ADR-074 correction,
    #: P1 review of T1c): this used to be computed in the frontend
    #: (`device-contracts.ts::relativeToMedianPercent`), but subtracting the
    #: constant `1` before rescaling shifts the reference point away from
    #: zero — that is domain math, not a unit rescale (the precedent for
    #: "acceptable" frontend rescaling, `photovoltaic-contracts.ts::
    #: ratioToPercent`, only ever does `x * 100`, never `(x - k) * 100`).
    #: Algebraically identical to the already-flagged violation in
    #: `frontend/src/lib/dashboard/yield.ts:54`. `None` under the exact same
    #: condition as `relative_to_own_median` — never invented independently.
    relative_to_own_median_deviation_percent: Decimal | None
    dropped: bool


def assess_devices(
    devices: tuple[DeviceProductionMetrics, ...],
    device_normal_threshold: Decimal,
) -> tuple[DeviceYieldAssessment, ...]:
    assessed = []
    for device in devices:
        relative: Decimal | None = None
        deviation_percent: Decimal | None = None
        dropped = False
        if (
            device.rendimento is not None
            and device.rendimento_median is not None
            and device.rendimento_median > 0
        ):
            relative = device.rendimento / device.rendimento_median
            deviation_percent = (relative - Decimal(1)) * Decimal(100)
            dropped = relative < device_normal_threshold
        assessed.append(
            DeviceYieldAssessment(
                device=device,
                relative_to_own_median=relative,
                relative_to_own_median_deviation_percent=deviation_percent,
                dropped=dropped,
            )
        )
    return tuple(assessed)


async def gather_device_metrics(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    target_date: date,
    irradiation: Decimal | None,
) -> tuple[DeviceProductionMetrics, ...]:
    """One entry per inverter registered on the plant, target day or not.

    A device that lost communication for the whole day has no `DailyEnergy`
    row — it must still show up (as "sem dados", see `_device_lines`)
    instead of silently vanishing from the alert. In a two-inverter plant
    that is the single most serious failure mode there is, and it must never
    be the one the message can't mention.
    """
    device_rows = (
        await session.execute(
            select(Device.id, Device.serial_number)
            .where(Device.plant_id == plant_id)
            .order_by(Device.serial_number)
        )
    ).all()

    energy_rows = (
        await session.execute(
            select(Device.id, func.sum(DailyEnergy.energy_kwh))
            .join(DailyEnergy, DailyEnergy.device_id == Device.id)
            .where(
                Device.plant_id == plant_id,
                DailyEnergy.production_date == target_date,
            )
            .group_by(Device.id)
        )
    ).all()
    production_by_device = {device_id: total for device_id, total in energy_rows}

    reporting_device_ids = tuple(
        device_id
        for device_id, _serial_number in device_rows
        if production_by_device.get(device_id) is not None
    )
    rendimento_medians: dict[uuid.UUID, Decimal] = {}
    if reporting_device_ids and irradiation is not None and irradiation > 0:
        rendimento_medians = await _device_rendimento_medians(
            session,
            device_ids=reporting_device_ids,
            plant_id=plant_id,
            before=target_date,
        )

    devices: list[DeviceProductionMetrics] = []
    for device_id, serial_number in device_rows:
        device_production = production_by_device.get(device_id)
        device_rendimento = None
        device_rendimento_median = None
        if device_production is not None and irradiation is not None and irradiation > 0:
            device_rendimento = device_production / irradiation
            device_rendimento_median = rendimento_medians.get(device_id)
        devices.append(
            DeviceProductionMetrics(
                device_id=device_id,
                serial_number=serial_number,
                production_kwh=device_production,
                rendimento=device_rendimento,
                rendimento_median=device_rendimento_median,
            )
        )
    return tuple(devices)


async def _device_rendimento_medians(
    session: AsyncSession,
    *,
    device_ids: tuple[uuid.UUID, ...],
    plant_id: uuid.UUID,
    before: date,
) -> dict[uuid.UUID, Decimal]:
    """Load all inverter baselines with two queries, independent of fleet size.

    The former implementation executed one energy query and one climate query
    per inverter. Besides slowing large plants down, that N+1 shape made alert
    latency depend on fleet size. Grouping the history by device/day and
    sharing the plant climate series keeps the exact same median semantics.
    """
    start = before - timedelta(days=RENDIMENTO_LOOKBACK_DAYS)
    end = before - timedelta(days=1)
    if end < start or not device_ids:
        return {}

    energy_rows = (
        await session.execute(
            select(
                DailyEnergy.device_id,
                DailyEnergy.production_date,
                func.sum(DailyEnergy.energy_kwh),
            )
            .where(
                DailyEnergy.device_id.in_(device_ids),
                DailyEnergy.production_date >= start,
                DailyEnergy.production_date <= end,
            )
            .group_by(DailyEnergy.device_id, DailyEnergy.production_date)
        )
    ).all()
    if not energy_rows:
        return {}

    climate_rows = (
        await session.execute(
            select(
                DailyClimateObservationRecord.observation_date,
                DailyClimateObservationRecord.irradiation_kwh_m2,
            ).where(
                DailyClimateObservationRecord.plant_id == plant_id,
                DailyClimateObservationRecord.observation_date >= start,
                DailyClimateObservationRecord.observation_date <= end,
            )
        )
    ).all()
    irradiation_by_day = {
        observation_date: irradiation
        for observation_date, irradiation in climate_rows
        if irradiation is not None and irradiation > 0
    }

    ratios_by_device: dict[uuid.UUID, list[Decimal]] = {}
    for device_id, production_date, production in energy_rows:
        irradiation = irradiation_by_day.get(production_date)
        if production is None or irradiation is None:
            continue
        ratios_by_device.setdefault(device_id, []).append(production / irradiation)

    return {
        device_id: median(ratios)
        for device_id, ratios in ratios_by_device.items()
        if len(ratios) >= MINIMUM_RENDIMENTO_SAMPLE_DAYS
    }
