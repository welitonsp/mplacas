"""Read-only queries backing ``photovoltaic/router.py`` (ADR-065).

Every public function here expects the caller to have already opened a
session with tenant context applied (``set_principal_context`` /
``set_tenant_context`` / ``set_platform_context`` — see
``db/tenant_context.py``) *before* invoking it, exactly like every other
read service in the project. The four underlying tables are under
PostgreSQL RLS in production (see
``migrations/versions/20260802_0040_enable_postgresql_rls.py``); this module
adds no authorization logic of its own — that is the router's job via
``core.tenancy.ReadPlant`` — it only shapes the queries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.photovoltaic.db_models import (
    DailyPvLossAssessmentRecord,
    DailyPvPerformanceRecord,
    SeasonalPvBaselineRecord,
)
from mplacas.photovoltaic.loss_taxonomy import LOSS_TAXONOMY_MODEL_VERSION, LossCategory
from mplacas.photovoltaic.performance import PERFORMANCE_MODEL_VERSION
from mplacas.photovoltaic.poa import MODEL_VERSION as SOLAR_MODEL_VERSION
from mplacas.photovoltaic.seasonal_baseline import (
    BASELINE_MODEL_VERSION,
    MINIMUM_REPORTING_AVAILABILITY,
    REFERENCE_WINDOW_DAYS,
)

MAX_PERFORMANCE_SERIES_DAYS = REFERENCE_WINDOW_DAYS

# Fixed order for the eight loss categories, matching
# `loss_taxonomy.classify_daily_losses` (`loss_taxonomy.py:110-119`) — the
# UI must not reorder by severity.
_LOSS_CATEGORY_ORDER = {category.value: index for index, category in enumerate(LossCategory)}

PERFORMANCE_UNAVAILABLE_REASON = "NO_PERFORMANCE_RESULTS"
LOSSES_UNAVAILABLE_REASON = "NO_LOSS_ASSESSMENTS"


class PhotovoltaicPerformanceNotFoundError(LookupError):
    """No performance result exists for the requested plant."""


class PhotovoltaicLossAssessmentNotFoundError(LookupError):
    """No loss assessment exists for the requested plant."""


class InvalidPerformanceWindowError(ValueError):
    """The requested `/performance` date window is not acceptable."""


class PhotovoltaicBaselineNotFoundError(LookupError):
    """No baseline result exists for the requested plant.

    Carries the derived reason (ADR-065 section 6) so the router can embed it
    in the 404 detail.
    """

    def __init__(self, reason: str, reference_complete_on: date | None = None) -> None:
        self.reason = reason
        self.reference_complete_on = reference_complete_on
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class PhotovoltaicSummary:
    plant_id: uuid.UUID
    performance: DailyPvPerformanceRecord | None
    performance_unavailable_reason: str | None
    baseline: SeasonalPvBaselineRecord | None
    baseline_unavailable_reason: str | None
    reference_complete_on: date | None
    losses: tuple[DailyPvLossAssessmentRecord, ...] | None
    losses_unavailable_reason: str | None


async def get_latest_performance(
    session: AsyncSession, *, plant_id: uuid.UUID
) -> DailyPvPerformanceRecord:
    """Most recent performance result, unique per day by version pair.

    Filters by both `performance_model_version` and `solar_model_version`
    simultaneously — the pair that makes `uq_daily_pv_performance_identity`
    (`db_models.py:87-93`) unique per plant/day — so the result is
    deterministic instead of ambiguous across POA climate sources
    (see `loss_taxonomy_service.py:58-61` for the same ambiguity handled
    defensively on the write path).
    """
    record = await session.scalar(
        select(DailyPvPerformanceRecord)
        .where(
            DailyPvPerformanceRecord.plant_id == plant_id,
            DailyPvPerformanceRecord.performance_model_version == PERFORMANCE_MODEL_VERSION,
            DailyPvPerformanceRecord.solar_model_version == SOLAR_MODEL_VERSION,
        )
        .order_by(DailyPvPerformanceRecord.observation_date.desc())
        .limit(1)
    )
    if record is None:
        raise PhotovoltaicPerformanceNotFoundError(
            "no photovoltaic performance result for this plant"
        )
    return record


def _validate_performance_window(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise InvalidPerformanceWindowError("end_date cannot be before start_date")
    window_days = (end_date - start_date).days + 1
    if window_days > MAX_PERFORMANCE_SERIES_DAYS:
        raise InvalidPerformanceWindowError(
            f"date window cannot exceed {MAX_PERFORMANCE_SERIES_DAYS} days"
        )


async def get_performance_series(
    session: AsyncSession,
    *,
    plant_id: uuid.UUID,
    start_date: date,
    end_date: date,
) -> tuple[DailyPvPerformanceRecord, ...]:
    """Daily performance series for a plotting window (max 366 days).

    Empty results are not an error — the caller returns 200 with an empty
    list (ADR-065 section 5).
    """
    _validate_performance_window(start_date, end_date)
    records = (
        await session.scalars(
            select(DailyPvPerformanceRecord)
            .where(
                DailyPvPerformanceRecord.plant_id == plant_id,
                DailyPvPerformanceRecord.performance_model_version
                == PERFORMANCE_MODEL_VERSION,
                DailyPvPerformanceRecord.solar_model_version == SOLAR_MODEL_VERSION,
                DailyPvPerformanceRecord.observation_date >= start_date,
                DailyPvPerformanceRecord.observation_date <= end_date,
            )
            .order_by(DailyPvPerformanceRecord.observation_date.asc())
        )
    ).all()
    return tuple(records)


async def _derive_baseline_unavailable_reason(
    session: AsyncSession, *, plant_id: uuid.UUID, today: date | None = None
) -> tuple[str, date | None]:
    """Derive why no defensible baseline exists yet (ADR-065 section 6).

    Reimplements, in SQL, the part of `seasonal_baseline._eligible`
    (`seasonal_baseline.py:171-180`) expressible without loading rows into
    Python: `performance_model_version` match, `data_quality_status ==
    'FINAL'`, `reporting_availability_ratio >= MINIMUM_REPORTING_AVAILABILITY`.
    If `_eligible` changes, this predicate must be revisited alongside it —
    a test fixes the correspondence between the two (see
    `test_photovoltaic_read_service.py`).
    """
    resolved_today = today if today is not None else date.today()
    count, min_observation_date = (
        await session.execute(
            select(
                func.count(DailyPvPerformanceRecord.id),
                func.min(DailyPvPerformanceRecord.observation_date),
            ).where(
                DailyPvPerformanceRecord.plant_id == plant_id,
                DailyPvPerformanceRecord.performance_model_version
                == PERFORMANCE_MODEL_VERSION,
                DailyPvPerformanceRecord.data_quality_status == "FINAL",
                DailyPvPerformanceRecord.reporting_availability_ratio.is_not(None),
                DailyPvPerformanceRecord.reporting_availability_ratio
                >= MINIMUM_REPORTING_AVAILABILITY,
            )
        )
    ).one()
    if not count or min_observation_date is None:
        return "NO_PERFORMANCE_HISTORY", None

    reference_end = min_observation_date + timedelta(days=REFERENCE_WINDOW_DAYS - 1)
    if resolved_today <= reference_end:
        reference_complete_on = reference_end + timedelta(days=1)
        return "REFERENCE_YEAR_INCOMPLETE", reference_complete_on

    return "INSUFFICIENT_SEASONAL_SAMPLES", None


async def get_latest_baseline(
    session: AsyncSession, *, plant_id: uuid.UUID, today: date | None = None
) -> SeasonalPvBaselineRecord:
    """Most recent seasonal baseline, or a derived-reason 404.

    Raises :class:`PhotovoltaicBaselineNotFoundError`, which carries the
    reason code and (when applicable) `reference_complete_on` for the
    router to embed in the 404 detail.
    """
    record = await session.scalar(
        select(SeasonalPvBaselineRecord)
        .where(
            SeasonalPvBaselineRecord.plant_id == plant_id,
            SeasonalPvBaselineRecord.baseline_model_version == BASELINE_MODEL_VERSION,
        )
        .order_by(SeasonalPvBaselineRecord.observation_date.desc())
        .limit(1)
    )
    if record is not None:
        return record
    reason, reference_complete_on = await _derive_baseline_unavailable_reason(
        session, plant_id=plant_id, today=today
    )
    raise PhotovoltaicBaselineNotFoundError(reason, reference_complete_on)


async def get_latest_losses(
    session: AsyncSession, *, plant_id: uuid.UUID
) -> tuple[DailyPvLossAssessmentRecord, ...]:
    """All loss categories for the most recent assessed date, fixed order.

    Ordered like `classify_daily_losses` (`loss_taxonomy.py:110-119`):
    COMMUNICATION, UNAVAILABILITY, CLIPPING, SOILING, SHADING, TEMPERATURE,
    DEGRADATION, UNEXPLAINED.
    """
    latest_date = await session.scalar(
        select(func.max(DailyPvLossAssessmentRecord.observation_date)).where(
            DailyPvLossAssessmentRecord.plant_id == plant_id,
            DailyPvLossAssessmentRecord.taxonomy_model_version
            == LOSS_TAXONOMY_MODEL_VERSION,
        )
    )
    if latest_date is None:
        raise PhotovoltaicLossAssessmentNotFoundError(
            "no photovoltaic loss assessment for this plant"
        )
    records = (
        await session.scalars(
            select(DailyPvLossAssessmentRecord).where(
                DailyPvLossAssessmentRecord.plant_id == plant_id,
                DailyPvLossAssessmentRecord.observation_date == latest_date,
                DailyPvLossAssessmentRecord.taxonomy_model_version
                == LOSS_TAXONOMY_MODEL_VERSION,
            )
        )
    ).all()
    return tuple(
        sorted(records, key=lambda record: _LOSS_CATEGORY_ORDER[record.category])
    )


async def get_summary(
    session: AsyncSession, *, plant_id: uuid.UUID, today: date | None = None
) -> PhotovoltaicSummary:
    """Compose performance/baseline/losses for the dashboard in one session.

    Always resolves — never raises for a missing sub-result. Each block is
    nullable and paired with a reason code (ADR-065 section 4/5).
    """
    performance: DailyPvPerformanceRecord | None
    performance_reason: str | None
    try:
        performance = await get_latest_performance(session, plant_id=plant_id)
        performance_reason = None
    except PhotovoltaicPerformanceNotFoundError:
        performance = None
        performance_reason = PERFORMANCE_UNAVAILABLE_REASON

    baseline: SeasonalPvBaselineRecord | None
    baseline_reason: str | None
    reference_complete_on: date | None
    try:
        baseline = await get_latest_baseline(session, plant_id=plant_id, today=today)
        baseline_reason = None
        reference_complete_on = None
    except PhotovoltaicBaselineNotFoundError as exc:
        baseline = None
        baseline_reason = exc.reason
        reference_complete_on = exc.reference_complete_on

    losses: tuple[DailyPvLossAssessmentRecord, ...] | None
    losses_reason: str | None
    try:
        losses = await get_latest_losses(session, plant_id=plant_id)
        losses_reason = None
    except PhotovoltaicLossAssessmentNotFoundError:
        losses = None
        losses_reason = LOSSES_UNAVAILABLE_REASON

    return PhotovoltaicSummary(
        plant_id=plant_id,
        performance=performance,
        performance_unavailable_reason=performance_reason,
        baseline=baseline,
        baseline_unavailable_reason=baseline_reason,
        reference_complete_on=reference_complete_on,
        losses=losses,
        losses_unavailable_reason=losses_reason,
    )
