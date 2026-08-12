"""Weather-first production alert — tells the user when the plant, not the

sky, is the problem.

`mplacas.intelligence.anomaly_engine` (the generic anomaly classifier) and
`mplacas.reports.daily_digest` (the always-sent informational summary) are
both siblings of this module, not replacements for it. This module answers
a narrower, higher-stakes question: **should we page the user about
yesterday, and if so, is it worth their time to go check the panels or call
the assistência técnica?**

Two rules drive every decision here, both learned from real production data
(Caldas Novas/GO, 92 days):

1. Irradiation, not cloud cover, decides whether "the weather did it". A
   day is only excused as low-sun when its irradiation is well below the
   *local median* for the analyzed window (see
   `mplacas.intelligence.anomaly_engine.is_low_irradiation`) — a fixed
   absolute threshold like "below 2.0 kWh/m^2" never fires in some
   locations and misclassifies every cloudy day as an unexplained anomaly.
2. Cloud cover and rain are narrative color, never a cause. A day can have
   74% cloud cover and still deliver completely normal irradiation (the
   clouds cleared when it mattered, or were high/thin). If irradiation
   contradicts cloud cover, irradiation wins and the cloud number is
   omitted from the message entirely — showing it would look like a false
   excuse for what is actually an equipment problem.

Severity escalates instead of shouting immediately: a first-day drop uses
"⚠️" with "se repetir, verifique" language; two or more consecutive
alerting days escalate to "🚨". The escalation is baked into the delivery
fingerprint precisely so that the existing per-fingerprint dedup never
suppresses a change in severity — a new streak length is new information.
"""

from __future__ import annotations

import html
import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.alerts.ledger import AlertDeliveryLedger
from mplacas.alerts.models import AlertSeverity
from mplacas.alerts.production_alert_dispatch import (
    ProductionAlertDispatchResult,
    dispatch_production_alert,
)
from mplacas.alerts.telegram import TelegramAlertProvider
from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.models import DailyEnergy, Device
from mplacas.devices.metrics import (
    DEVICE_NORMAL_THRESHOLD,
    MINIMUM_RENDIMENTO_SAMPLE_DAYS,
    RENDIMENTO_LOOKBACK_DAYS,
    DeviceProductionMetrics,
    DeviceYieldAssessment,
    assess_devices,
    gather_device_metrics,
)
from mplacas.intelligence.anomaly_engine import (
    DEFAULT_LOW_IRRADIATION_RELATIVE_THRESHOLD,
    DEFAULT_MINIMUM_IRRADIATION_SAMPLE_DAYS,
    is_low_irradiation,
)

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://mplacas-frontend.pages.dev/dashboard"

#: How many days before the target date feed the local irradiation/rendimento
#: medians. Matches `mplacas.reports.daily_digest.RENDIMENTO_LOOKBACK_DAYS`.
LOOKBACK_DAYS = RENDIMENTO_LOOKBACK_DAYS

#: How many trailing days (including the target day) are walked backward to
#: measure the current alerting streak. Bounded so a plant that has been
#: alerting for months does not trigger unbounded historical queries just to
#: decide between "⚠️" and "🚨" — after this many days it is already "🚨" and
#: the exact streak length stops mattering for the message.
MAX_STREAK_LOOKBACK_DAYS = 10

#: A day only counts toward the alert gate when production falls below this
#: fraction of the expected daily production.
PRODUCTION_BELOW_EXPECTED_THRESHOLD = Decimal("0.85")

#: A rendimento (production per unit of irradiation) below this fraction of
#: its historical median is considered a real drop, not noise.
RENDIMENTO_NORMAL_THRESHOLD = Decimal("0.85")

#: Cloud cover above this is described as "nublado" and — when it
#: contradicts a normal irradiation reading — is deliberately omitted from
#: the message instead of being shown as a false excuse (see module
#: docstring, rule 2).
HIGH_CLOUD_COVER_PERCENT = Decimal("60")


class ProductionAlertDataNotFoundError(LookupError):
    """There is no production data yet for the requested day."""


class ProductionAlertReason(StrEnum):
    NONE = "NONE"
    LOW_SUN_AND_LOW_YIELD = "LOW_SUN_AND_LOW_YIELD"
    REAL_DROP_SET = "REAL_DROP_SET"
    REAL_DROP_SINGLE = "REAL_DROP_SINGLE"
    UNEXPLAINED_LOW_PRODUCTION = "UNEXPLAINED_LOW_PRODUCTION"


@dataclass(frozen=True, slots=True)
class ProductionAlertMetrics:
    """Pure data assembled for a single day, before any decision or rendering."""

    plant_id: uuid.UUID
    target_date: date
    production_kwh: Decimal
    expected_daily_production_kwh: Decimal
    irradiation_kwh_m2: Decimal | None
    irradiation_median_kwh_m2: Decimal | None
    irradiation_sample_days: int
    cloud_cover_percent: Decimal | None
    rendimento: Decimal | None
    rendimento_median: Decimal | None
    devices: tuple[DeviceProductionMetrics, ...]


@dataclass(frozen=True, slots=True)
class ProductionAlertAssessment:
    should_alert: bool
    reason: ProductionAlertReason
    devices: tuple[DeviceYieldAssessment, ...]
    #: Whether the target day's irradiation was actually classified as low
    #: relative to the local median. Rendering must consult this rather than
    #: infer it from `reason`, since a per-device drop can legitimately be
    #: the alerting reason on a day that was *also* genuinely low-sun (see
    #: `assess_production_alert`) — the climate line must stay honest about
    #: which one actually happened.
    low_irradiation: bool = False


@dataclass(frozen=True, slots=True)
class ProductionAlertContent:
    """A ready-to-send Telegram message: HTML text, inline keyboard and severity."""

    text: str
    reply_markup: dict[str, Any]
    severity: AlertSeverity
    fingerprint: str


async def gather_production_alert_metrics(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    target_date: date,
    expected_daily_production_kwh: Decimal,
) -> ProductionAlertMetrics:
    """Load everything needed to assess and render the alert for `target_date`."""
    production = await _sum_energy(session, plant_id=plant_id, start=target_date, end=target_date)
    if production is None:
        raise ProductionAlertDataNotFoundError(
            f"no daily_energy recorded for plant {plant_id} on {target_date.isoformat()}"
        )

    climate = await session.scalar(
        select(DailyClimateObservationRecord)
        .where(
            DailyClimateObservationRecord.plant_id == plant_id,
            DailyClimateObservationRecord.observation_date == target_date,
        )
        .limit(1)
    )
    irradiation = climate.irradiation_kwh_m2 if climate is not None else None
    cloud_cover = climate.cloud_cover_percent if climate is not None else None

    irradiation_median, irradiation_sample_days = await _irradiation_median(
        session, plant_id=plant_id, before=target_date
    )

    rendimento = None
    rendimento_median = None
    if irradiation is not None and irradiation > 0:
        rendimento = production / irradiation
        rendimento_median = await _plant_rendimento_median(
            session, plant_id=plant_id, before=target_date
        )

    devices = await gather_device_metrics(
        session,
        plant_id=plant_id,
        target_date=target_date,
        irradiation=irradiation,
    )

    return ProductionAlertMetrics(
        plant_id=plant_id,
        target_date=target_date,
        production_kwh=production,
        expected_daily_production_kwh=expected_daily_production_kwh,
        irradiation_kwh_m2=irradiation,
        irradiation_median_kwh_m2=irradiation_median,
        irradiation_sample_days=irradiation_sample_days,
        cloud_cover_percent=cloud_cover,
        rendimento=rendimento,
        rendimento_median=rendimento_median,
        devices=devices,
    )


def assess_production_alert(
    metrics: ProductionAlertMetrics,
    *,
    production_below_expected_threshold: Decimal = PRODUCTION_BELOW_EXPECTED_THRESHOLD,
    rendimento_normal_threshold: Decimal = RENDIMENTO_NORMAL_THRESHOLD,
    device_normal_threshold: Decimal = DEVICE_NORMAL_THRESHOLD,
    low_irradiation_relative_threshold: Decimal = DEFAULT_LOW_IRRADIATION_RELATIVE_THRESHOLD,
    minimum_irradiation_sample_days: int = DEFAULT_MINIMUM_IRRADIATION_SAMPLE_DAYS,
) -> ProductionAlertAssessment:
    """Weather-first decision tree — see the module docstring for the rules.

    ``Produção abaixo do esperado?`` gates everything else: if production is
    within `production_below_expected_threshold` of what was expected there
    is nothing to explain, and no alert is raised regardless of climate or
    rendimento.
    """
    devices = assess_devices(metrics.devices, device_normal_threshold)

    if metrics.expected_daily_production_kwh <= 0:
        return ProductionAlertAssessment(False, ProductionAlertReason.NONE, devices)

    below_expected = (
        metrics.production_kwh
        < metrics.expected_daily_production_kwh * production_below_expected_threshold
    )
    if not below_expected:
        return ProductionAlertAssessment(False, ProductionAlertReason.NONE, devices)

    rendimento_relative: Decimal | None = None
    if (
        metrics.rendimento is not None
        and metrics.rendimento_median is not None
        and metrics.rendimento_median > 0
    ):
        rendimento_relative = metrics.rendimento / metrics.rendimento_median
    rendimento_known = rendimento_relative is not None
    rendimento_normal = (
        rendimento_relative is not None and rendimento_relative >= rendimento_normal_threshold
    )

    any_device_dropped = any(device.dropped for device in devices)
    #: Whether at least one inverter has a trustworthy relative-to-own-median
    #: reading at all — as opposed to `any_device_dropped`, which is False
    #: both when a device is genuinely fine *and* when its status could not
    #: be computed (missing irradiation, missing/insufficient history). The
    #: "irradiation was normal" branch below must be able to tell these two
    #: apart: silence is not evidence that the day was fine.
    any_device_known = any(device.relative_to_own_median is not None for device in devices)

    low_irradiation = is_low_irradiation(
        metrics.irradiation_kwh_m2,
        metrics.irradiation_median_kwh_m2,
        metrics.irradiation_sample_days,
        relative_threshold=low_irradiation_relative_threshold,
        minimum_sample_days=minimum_irradiation_sample_days,
    )

    if low_irradiation:
        # A specific inverter underperforming its own baseline is evidence
        # of an equipment problem independent of the weather, even on a
        # genuinely cloudy day — the low-sun explanation must never bury a
        # real per-device drop, so it is checked first and wins.
        if any_device_dropped:
            return ProductionAlertAssessment(
                True, _device_drop_reason(devices), devices, low_irradiation=True
            )
        # It was cloudy AND the plant-level rendimento is fine (or we
        # cannot prove otherwise) -> the weather explains it, no alert.
        # Missing rendimento data fails toward alerting rather than
        # silently excusing the day.
        if rendimento_known and rendimento_normal:
            return ProductionAlertAssessment(
                False, ProductionAlertReason.NONE, devices, low_irradiation=True
            )
        return ProductionAlertAssessment(
            True, ProductionAlertReason.LOW_SUN_AND_LOW_YIELD, devices, low_irradiation=True
        )

    # Irradiation was normal (or unknown) — the weather cannot be blamed.
    yield_drop = (rendimento_known and not rendimento_normal) or any_device_dropped
    if not yield_drop:
        if not rendimento_known and not any_device_known:
            # No evidence at all that the day was actually fine: no
            # plant-level rendimento (missing climate reading, or history too
            # thin to trust — see `MINIMUM_RENDIMENTO_SAMPLE_DAYS`) and not a
            # single inverter with a trustworthy median either. Production
            # still missed its target and nothing here excuses it, so a
            # climate-provider outage or a plant too new to have history must
            # never look identical to "nothing to see here" — we fail toward
            # alerting rather than staying silent about an unexplained drop.
            return ProductionAlertAssessment(
                True, ProductionAlertReason.UNEXPLAINED_LOW_PRODUCTION, devices
            )
        return ProductionAlertAssessment(False, ProductionAlertReason.NONE, devices)

    return ProductionAlertAssessment(True, _device_drop_reason(devices), devices)


def _device_drop_reason(
    devices: tuple[DeviceYieldAssessment, ...],
) -> ProductionAlertReason:
    """Whether the dropped devices are an isolated exception or the whole set.

    A single inverter dropping out of a healthy set points to equipment
    failure or localized shade; the whole set dropping together points to
    something affecting every panel (dirt, generalized shade) — see the
    device-line copy in `_device_lines` for how this distinction is
    explained to the user.
    """
    dropped_count = sum(1 for device in devices if device.dropped)
    total_devices = len(devices)
    if devices and 0 < dropped_count < total_devices:
        return ProductionAlertReason.REAL_DROP_SINGLE
    return ProductionAlertReason.REAL_DROP_SET


def render_production_alert(
    metrics: ProductionAlertMetrics,
    assessment: ProductionAlertAssessment,
    *,
    consecutive_days: int,
    dashboard_url: str = DASHBOARD_URL,
) -> ProductionAlertContent:
    """Render `metrics`/`assessment` into the HTML message, pure of I/O.

    `consecutive_days` must count the target day itself, so `1` means "first
    day this happened" and `2+` triggers the 🚨 escalation.
    """
    if assessment.reason is ProductionAlertReason.NONE:
        raise ValueError("cannot render a message for a non-alerting assessment")
    if consecutive_days < 1:
        raise ValueError("consecutive_days must count the target day itself (>= 1)")

    escalated = consecutive_days >= 2
    icon = "🚨" if escalated else "⚠️"
    severity = AlertSeverity.CRITICAL if escalated else AlertSeverity.WARNING

    title = _title(assessment.reason, escalated, consecutive_days)
    lines: list[str] = [f"{icon} {html.escape(title)}"]
    lines.append("")
    lines.append(f"     <b>{_format_number(metrics.production_kwh, 1)} kWh</b>")
    if metrics.expected_daily_production_kwh > 0:
        percent = (
            metrics.production_kwh / metrics.expected_daily_production_kwh * Decimal(100)
        )
        lines.append(f"     {_format_number(percent, 0)}% do esperado ▼")
    lines.append("")

    climate_lines = _climate_lines(metrics, assessment)
    if climate_lines:
        lines.extend(climate_lines)
        lines.append("")

    yield_lines = _yield_lines(metrics, assessment)
    if yield_lines:
        lines.extend(yield_lines)
        lines.append("")

    device_lines = _device_lines(assessment)
    if device_lines:
        lines.extend(device_lines)
        lines.append("")

    lines.append(html.escape(_closing_line(assessment.reason, escalated, consecutive_days)))

    while lines and lines[-1] == "":
        lines.pop()

    text = "\n".join(lines)
    reply_markup = {"inline_keyboard": [[{"text": "Abrir painel", "url": dashboard_url}]]}
    fingerprint = _fingerprint(metrics, assessment, consecutive_days)
    return ProductionAlertContent(
        text=text, reply_markup=reply_markup, severity=severity, fingerprint=fingerprint
    )


async def send_production_alert(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    target_date: date,
    expected_daily_production_kwh: Decimal,
    provider: TelegramAlertProvider,
    ledger: AlertDeliveryLedger,
    dashboard_url: str = DASHBOARD_URL,
    max_streak_lookback_days: int = MAX_STREAK_LOOKBACK_DAYS,
) -> ProductionAlertDispatchResult:
    """Assess, render and deliver the alert for `target_date`, honoring dedup.

    Deduplication is per-fingerprint, but the fingerprint embeds the
    escalation stage (see `_fingerprint`), so a first-day "⚠️" alert and its
    "🚨" escalation on day two are always distinct deliveries even though
    they describe the same underlying streak.
    """
    try:
        metrics = await gather_production_alert_metrics(
            session,
            plant_id=plant_id,
            target_date=target_date,
            expected_daily_production_kwh=expected_daily_production_kwh,
        )
    except ProductionAlertDataNotFoundError:
        logger.info(
            "production_alert_no_data",
            extra={"plant_id": str(plant_id), "target_date": target_date.isoformat()},
        )
        return ProductionAlertDispatchResult(sent=False, reason="no data")

    assessment = assess_production_alert(metrics)
    if not assessment.should_alert:
        return ProductionAlertDispatchResult(sent=False, reason="no alert condition")

    streak = await _count_consecutive_alert_days(
        session,
        plant_id=plant_id,
        target_date=target_date,
        expected_daily_production_kwh=expected_daily_production_kwh,
        max_lookback_days=max_streak_lookback_days,
    )
    content = render_production_alert(
        metrics, assessment, consecutive_days=streak, dashboard_url=dashboard_url
    )

    dispatch_result = await dispatch_production_alert(
        content,
        provider=provider,
        ledger=ledger,
    )
    if not dispatch_result.sent:
        return dispatch_result
    logger.info(
        "production_alert_sent",
        extra={
            "plant_id": str(plant_id),
            "target_date": target_date.isoformat(),
            "reason": assessment.reason.value,
            "consecutive_days": streak,
        },
    )
    return dispatch_result


# --- Assessment helpers -----------------------------------------------------


async def _count_consecutive_alert_days(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    target_date: date,
    expected_daily_production_kwh: Decimal,
    max_lookback_days: int,
) -> int:
    streak = 0
    current = target_date
    for _ in range(max_lookback_days):
        try:
            metrics = await gather_production_alert_metrics(
                session,
                plant_id=plant_id,
                target_date=current,
                expected_daily_production_kwh=expected_daily_production_kwh,
            )
        except ProductionAlertDataNotFoundError:
            break
        assessment = assess_production_alert(metrics)
        if not assessment.should_alert:
            break
        streak += 1
        current = current - timedelta(days=1)
    return streak


def _fingerprint(
    metrics: ProductionAlertMetrics,
    assessment: ProductionAlertAssessment,
    consecutive_days: int,
) -> str:
    escalation_stage = "escalated" if consecutive_days >= 2 else "first"
    return (
        f"production:{metrics.plant_id}:{metrics.target_date.isoformat()}:"
        f"{assessment.reason.value}:{escalation_stage}"
    )


# --- Rendering helpers -------------------------------------------------------


def _title(reason: ProductionAlertReason, escalated: bool, consecutive_days: int) -> str:
    suffix = f" — {consecutive_days}º dia seguido" if escalated else " ontem"
    if reason is ProductionAlertReason.REAL_DROP_SINGLE:
        return f"Um inversor rendendo abaixo do normal{suffix}"
    if reason is ProductionAlertReason.LOW_SUN_AND_LOW_YIELD:
        return f"Pouco sol e rendimento abaixo do normal{suffix}"
    if reason is ProductionAlertReason.UNEXPLAINED_LOW_PRODUCTION:
        return f"Produção abaixo do esperado{suffix}"
    return f"Queda de rendimento{suffix}"


def _climate_lines(
    metrics: ProductionAlertMetrics, assessment: ProductionAlertAssessment
) -> list[str]:
    irradiation = metrics.irradiation_kwh_m2
    if irradiation is None:
        return []

    if assessment.low_irradiation:
        # The day was actually classified as low-sun by `is_low_irradiation`
        # (see module docstring rule 1) — always say so honestly, even when
        # the alerting reason ended up being a per-device drop rather than
        # the weather itself (see `assess_production_alert`).
        line = f"Pouco sol ontem ({_format_number(irradiation, 2)} kWh/m²)."
        return [line]

    cloud_cover = metrics.cloud_cover_percent
    contradicts_weather = cloud_cover is not None and cloud_cover > HIGH_CLOUD_COVER_PERCENT
    if contradicts_weather:
        # Rule 2 (see module docstring): never show a cloud number that
        # would look like a false excuse for a real equipment problem.
        return [
            f"O sol chegou normal ({_format_number(irradiation, 2)} kWh/m²).",
            "A queda não foi o tempo.",
        ]

    if cloud_cover is not None:
        sky_label = "Céu limpo" if cloud_cover <= 20 else "Parcialmente nublado"
        return [
            f"{sky_label} ({_format_number(cloud_cover, 0)}% de nuvens, "
            f"{_format_number(irradiation, 2)} kWh/m²)."
        ]

    return [f"O sol chegou normal ({_format_number(irradiation, 2)} kWh/m²)."]


def _yield_lines(
    metrics: ProductionAlertMetrics,
    assessment: ProductionAlertAssessment,
    *,
    rendimento_normal_threshold: Decimal = RENDIMENTO_NORMAL_THRESHOLD,
) -> list[str]:
    if assessment.reason not in (
        ProductionAlertReason.REAL_DROP_SET,
        ProductionAlertReason.REAL_DROP_SINGLE,
        ProductionAlertReason.LOW_SUN_AND_LOW_YIELD,
    ):
        return []
    if (
        metrics.rendimento is None
        or metrics.rendimento_median is None
        or metrics.rendimento_median <= 0
    ):
        return []
    relative = metrics.rendimento / metrics.rendimento_median
    # Must match the threshold `assess_production_alert` actually used to
    # call the plant-level rendimento "normal" — otherwise a day the
    # decision tree classified as normal (e.g. relative 0.90, alerting only
    # because one inverter dropped) renders a plant-wide "abaixo do normal"
    # line that contradicts the assessment.
    if relative >= rendimento_normal_threshold:
        return []
    drop_percent = (Decimal(1) - relative) * Decimal(100)
    return [f"Rendimento {_format_number(drop_percent, 0)}% abaixo do normal desta usina."]


def _device_lines(assessment: ProductionAlertAssessment) -> list[str]:
    if assessment.reason not in (
        ProductionAlertReason.REAL_DROP_SET,
        ProductionAlertReason.REAL_DROP_SINGLE,
    ):
        return []
    if not assessment.devices:
        return []

    lines: list[str] = []
    for device in assessment.devices:
        serial = html.escape(device.device.serial_number)
        if device.device.production_kwh is None:
            # Lost communication for the whole day — never invent a kWh
            # figure that was not measured (see `DeviceProductionMetrics`).
            lines.append(f"  {serial}   sem dados hoje")
            continue
        production = _format_number(device.device.production_kwh, 1)
        if device.relative_to_own_median is None:
            status = "sem histórico"
        elif device.dropped:
            drop_percent = (Decimal(1) - device.relative_to_own_median) * Decimal(100)
            status = f"−{_format_number(drop_percent, 0)}% ▼"
        else:
            status = "normal"
        lines.append(f"  {serial}   {production} kWh   {status}")
    lines.append("")

    dropped = [device for device in assessment.devices if device.dropped]
    total = len(assessment.devices)
    if assessment.reason is ProductionAlertReason.REAL_DROP_SINGLE:
        lines.append(
            "Só um inversor caiu — padrão de falha de equipamento ou sombra "
            "localizada, não sujeira geral. Vale acionar a assistência."
        )
    elif total == 1:
        lines.append(
            "O único inversor caiu, o que aponta para sujeira ou sombra sobre "
            "o conjunto — não falha de equipamento."
        )
    else:
        drop_percents = [
            (Decimal(1) - device.relative_to_own_median) * Decimal(100)
            for device in dropped
            if device.relative_to_own_median is not None
        ]
        magnitude = (
            f" (−{_format_number(max(drop_percents), 0)}% cada)" if drop_percents else ""
        )
        lines.append(
            f"Os {total} inversores caíram junto{magnitude}, o que aponta para "
            "sujeira ou sombra sobre o conjunto — não falha de equipamento."
        )
    return lines


def _closing_line(reason: ProductionAlertReason, escalated: bool, consecutive_days: int) -> str:
    if reason is ProductionAlertReason.REAL_DROP_SINGLE:
        # The device breakdown already closes with an explicit call to
        # action, so keep this short and only add urgency once escalated.
        if escalated:
            return f"Já são {consecutive_days} dias seguidos — vale agir hoje."
        return "Se repetir amanhã, vale olhar os painéis."
    if escalated:
        return f"Já são {consecutive_days} dias seguidos — vale investigar hoje."
    return "Se repetir amanhã, vale olhar os painéis."


def _format_number(value: Decimal, decimals: int) -> str:
    quantum = Decimal(1).scaleb(-decimals)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    text = f"{rounded:,.{decimals}f}"
    text = text.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return text


# --- Data-gathering helpers ---------------------------------------------------


async def _sum_energy(
    session: AsyncSession, *, plant_id: uuid.UUID, start: date, end: date
) -> Decimal | None:
    total = await session.scalar(
        select(func.sum(DailyEnergy.energy_kwh))
        .join(Device, DailyEnergy.device_id == Device.id)
        .where(
            Device.plant_id == plant_id,
            DailyEnergy.production_date >= start,
            DailyEnergy.production_date <= end,
        )
    )
    return total


async def _irradiation_median(
    session: AsyncSession, *, plant_id: uuid.UUID, before: date
) -> tuple[Decimal | None, int]:
    """Median irradiation over the lookback window, excluding `before`.

    Returns `(median, sample_days)`. `sample_days` is the number of
    historical days with a valid irradiation reading — it feeds
    `is_low_irradiation`'s confidence gate, so callers must not substitute
    it with the window length when readings are missing.
    """
    start = before - timedelta(days=LOOKBACK_DAYS)
    end = before - timedelta(days=1)
    if end < start:
        return None, 0

    rows = (
        await session.scalars(
            select(DailyClimateObservationRecord.irradiation_kwh_m2).where(
                DailyClimateObservationRecord.plant_id == plant_id,
                DailyClimateObservationRecord.observation_date >= start,
                DailyClimateObservationRecord.observation_date <= end,
                DailyClimateObservationRecord.irradiation_kwh_m2.is_not(None),
            )
        )
    ).all()
    values = [value for value in rows if value is not None]
    if not values:
        return None, 0
    return median(values), len(values)


async def _plant_rendimento_median(
    session: AsyncSession, *, plant_id: uuid.UUID, before: date
) -> Decimal | None:
    """Median historical production-per-irradiation over the lookback window.

    Mirrors `mplacas.reports.daily_digest`'s rendimento median calculation.
    """
    start = before - timedelta(days=LOOKBACK_DAYS)
    end = before - timedelta(days=1)
    if end < start:
        return None

    energy_rows = (
        await session.execute(
            select(DailyEnergy.production_date, func.sum(DailyEnergy.energy_kwh))
            .join(Device, DailyEnergy.device_id == Device.id)
            .where(
                Device.plant_id == plant_id,
                DailyEnergy.production_date >= start,
                DailyEnergy.production_date <= end,
            )
            .group_by(DailyEnergy.production_date)
        )
    ).all()
    if not energy_rows:
        return None
    energy_by_day = {row[0]: row[1] for row in energy_rows}
    return await _rendimento_median_from_energy(session, plant_id, start, end, energy_by_day)


async def _rendimento_median_from_energy(
    session: AsyncSession,
    plant_id: uuid.UUID,
    start: date,
    end: date,
    energy_by_day: dict[date, Decimal],
    *,
    minimum_sample_days: int = MINIMUM_RENDIMENTO_SAMPLE_DAYS,
) -> Decimal | None:
    climate_rows = (
        await session.scalars(
            select(DailyClimateObservationRecord).where(
                DailyClimateObservationRecord.plant_id == plant_id,
                DailyClimateObservationRecord.observation_date >= start,
                DailyClimateObservationRecord.observation_date <= end,
            )
        )
    ).all()

    ratios: list[Decimal] = []
    for climate in climate_rows:
        production = energy_by_day.get(climate.observation_date)
        irradiation = climate.irradiation_kwh_m2
        if production is None or irradiation is None or irradiation <= 0:
            continue
        ratios.append(production / irradiation)

    if len(ratios) < minimum_sample_days:
        # Too few historical days to trust the median (see
        # `MINIMUM_RENDIMENTO_SAMPLE_DAYS`) — `None` propagates as "unknown",
        # never as a value computed from noise.
        return None
    return median(ratios)
