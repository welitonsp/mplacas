"""Daily production digest — an informational message, not an alert.

Unlike `mplacas.alerts`, which exists to flag problems that require action
and is deliberately filtered by `minimum_severity`, the daily digest always
tells the user how yesterday went, even when everything was normal. It is
built and sent on its own path so it never gets caught by the alert
severity filter.

The module lives under `mplacas.reports` (not `mplacas.alerts`) because it
is not an alert: it has no severity, no fingerprint-based deduplication and
no "recommended action" — it is a periodic summary of already-computed
production data, which is what the rest of the `reports` package is about.
"""

from __future__ import annotations

import html
import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.alerts.telegram import TelegramAlertProvider
from mplacas.billing.read_repository import ConfirmedBillReadRepository
from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.models import DailyEnergy, Device

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://mplacas-frontend.pages.dev/dashboard"

#: How many days before the target date are used to establish a "normal"
#: rendimento (production per unit of irradiation) baseline.
RENDIMENTO_LOOKBACK_DAYS = 30

_MONTH_NAMES_PT = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


class DailyDigestDataNotFoundError(LookupError):
    """There is no production data yet for the requested day."""


@dataclass(frozen=True, slots=True)
class DailyDigestMetrics:
    """Pure data assembled for a single day, before any rendering."""

    plant_id: uuid.UUID
    target_date: date
    production_kwh: Decimal
    expected_daily_production_kwh: Decimal
    irradiation_kwh_m2: Decimal | None
    cloud_cover_percent: Decimal | None
    rendimento: Decimal | None
    rendimento_median: Decimal | None
    month_total_kwh: Decimal | None
    month_days: int | None
    credit_balance_kwh: Decimal | None


@dataclass(frozen=True, slots=True)
class DailyDigestContent:
    """A ready-to-send Telegram message: HTML text plus an inline keyboard."""

    text: str
    reply_markup: dict[str, Any]


async def gather_daily_digest_metrics(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    target_date: date,
    expected_daily_production_kwh: Decimal,
) -> DailyDigestMetrics:
    """Load everything needed to render the digest for `target_date`.

    Raises `DailyDigestDataNotFoundError` when there is no production
    recorded for the target date — sending a "0 kWh" message in that case
    would misrepresent a data gap as an actual zero-production day.
    """
    production = await _sum_energy(session, plant_id=plant_id, start=target_date, end=target_date)
    if production is None:
        raise DailyDigestDataNotFoundError(
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

    rendimento = None
    rendimento_median = None
    if irradiation is not None and irradiation > 0:
        rendimento = production / irradiation
        rendimento_median = await _rendimento_median(
            session, plant_id=plant_id, before=target_date
        )

    month_start = target_date.replace(day=1)
    month_total = await _sum_energy(session, plant_id=plant_id, start=month_start, end=target_date)
    month_days = target_date.day if month_total is not None else None

    latest_bill = await ConfirmedBillReadRepository(session).latest(plant_id=plant_id)
    credit_balance = latest_bill.bill.credit_balance_kwh if latest_bill is not None else None

    return DailyDigestMetrics(
        plant_id=plant_id,
        target_date=target_date,
        production_kwh=production,
        expected_daily_production_kwh=expected_daily_production_kwh,
        irradiation_kwh_m2=irradiation,
        cloud_cover_percent=cloud_cover,
        rendimento=rendimento,
        rendimento_median=rendimento_median,
        month_total_kwh=month_total,
        month_days=month_days,
        credit_balance_kwh=credit_balance,
    )


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


async def _rendimento_median(
    session: AsyncSession, *, plant_id: uuid.UUID, before: date
) -> Decimal | None:
    """Median historical production-per-irradiation over the lookback window.

    The target day itself is excluded so it is compared against a baseline
    it did not contribute to.
    """
    start = before - timedelta(days=RENDIMENTO_LOOKBACK_DAYS)
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

    if not ratios:
        return None
    return median(ratios)


def render_daily_digest(metrics: DailyDigestMetrics) -> DailyDigestContent:
    """Render `metrics` into the HTML message and inline keyboard, pure of I/O."""
    lines: list[str] = [
        f"☀️ Ontem, {html.escape(_format_date_pt(metrics.target_date))}",
        "",
        f"     <b>{_format_number(metrics.production_kwh, 1)} kWh</b>",
    ]

    if metrics.expected_daily_production_kwh > 0:
        percent = (
            metrics.production_kwh / metrics.expected_daily_production_kwh * Decimal(100)
        )
        arrow = "▲" if percent >= 100 else "▼"
        lines.append(f"     {_format_number(percent, 0)}% do esperado {arrow}")

    lines.append("")

    if metrics.irradiation_kwh_m2 is not None and metrics.rendimento is not None:
        sun_line = f"Sol: {_format_number(metrics.irradiation_kwh_m2, 2)} kWh/m²"
        climate_label = _climate_label(metrics.cloud_cover_percent)
        if climate_label is not None:
            sun_line += f" · {html.escape(climate_label)}"
        lines.append(sun_line)

        rendimento_label = _rendimento_label(metrics.rendimento, metrics.rendimento_median)
        rendimento_line = f"Rendimento: {_format_number(metrics.rendimento, 2)}"
        if rendimento_label is not None:
            rendimento_line += f" — {html.escape(rendimento_label)}"
        lines.append(rendimento_line)
        lines.append("")

    if metrics.month_total_kwh is not None and metrics.month_days is not None:
        month_name = html.escape(_MONTH_NAMES_PT[metrics.target_date.month - 1].capitalize())
        lines.append(
            f"{month_name}: {_format_number(metrics.month_total_kwh, 0)} kWh"
            f" em {metrics.month_days} dias"
        )

    if metrics.credit_balance_kwh is not None:
        lines.append(f"Saldo de créditos: {_format_number(metrics.credit_balance_kwh, 0)} kWh")

    while lines and lines[-1] == "":
        lines.pop()

    text = "\n".join(lines)
    reply_markup = {
        "inline_keyboard": [[{"text": "Abrir painel", "url": DASHBOARD_URL}]]
    }
    return DailyDigestContent(text=text, reply_markup=reply_markup)


async def send_daily_digest(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    target_date: date,
    expected_daily_production_kwh: Decimal,
    provider: TelegramAlertProvider,
) -> bool:
    """Build and send the daily digest. Returns False (no-op) when there is no data yet."""
    try:
        metrics = await gather_daily_digest_metrics(
            session,
            plant_id=plant_id,
            target_date=target_date,
            expected_daily_production_kwh=expected_daily_production_kwh,
        )
    except DailyDigestDataNotFoundError:
        logger.info(
            "daily_digest_no_data",
            extra={"plant_id": str(plant_id), "target_date": target_date.isoformat()},
        )
        return False

    content = render_daily_digest(metrics)
    await provider.send_message(
        content.text,
        parse_mode="HTML",
        reply_markup=content.reply_markup,
    )
    logger.info(
        "daily_digest_sent",
        extra={"plant_id": str(plant_id), "target_date": target_date.isoformat()},
    )
    return True


def _format_date_pt(value: date) -> str:
    return f"{value.day} de {_MONTH_NAMES_PT[value.month - 1]}"


def _format_number(value: Decimal, decimals: int) -> str:
    quantum = Decimal(1).scaleb(-decimals)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    text = f"{rounded:,.{decimals}f}"
    # Swap separators from the default en-US grouping to Brazilian-Portuguese
    # (comma decimal, dot thousands) using a placeholder to avoid clashes.
    text = text.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return text


def _climate_label(cloud_cover_percent: Decimal | None) -> str | None:
    if cloud_cover_percent is None:
        return None
    if cloud_cover_percent <= 20:
        return "dia claro"
    if cloud_cover_percent <= 60:
        return "parcialmente nublado"
    return "dia nublado"


def _rendimento_label(rendimento: Decimal, rendimento_median: Decimal | None) -> str | None:
    if rendimento_median is None or rendimento_median <= 0:
        return None
    relative = rendimento / rendimento_median
    if relative >= Decimal("1.05"):
        return "acima do normal"
    if relative <= Decimal("0.95"):
        return "abaixo do normal"
    return "dentro do normal"
