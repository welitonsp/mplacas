from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import CursorResult, delete
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.climate.db_models import DailyClimateObservationRecord
from mplacas.db.models import DailyEnergy

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TimeSeriesRetentionWindows:
    """Janelas de retenção para séries temporais de produção e clima.

    Defaults a 1825 dias (5 anos) para ambas as séries, alinhado à exigência
    fiscal brasileira de guarda de documentos contábeis por cinco anos.
    ``daily_energy_versions`` é excluído por CASCADE quando o registro pai cai.
    """

    daily_energy_days: int = 1825
    climate_observations_days: int = 1825

    def __post_init__(self) -> None:
        for name, value in (
            ("daily_energy_days", self.daily_energy_days),
            ("climate_observations_days", self.climate_observations_days),
        ):
            if value < 1:
                raise ValueError(f"{name} must be at least 1 day")


class TimeSeriesRetentionService:
    """Remove registros antigos de séries temporais de produção e clima.

    Invariantes ADR-048:
    - Purga somente por data de produção/observação, nunca por coleta.
    - ``daily_energy_versions`` cai por CASCADE — sem DELETE explícito.
    - Nunca toca em faturas, snapshots de relatório ou registros operacionais:
      esses são domínio do ``RetentionService`` original.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def purge(
        self,
        *,
        windows: TimeSeriesRetentionWindows | None = None,
        today: date | None = None,
    ) -> tuple[int, int]:
        """Purga registros antigos. Retorna (energy_deleted, climate_deleted)."""
        windows = windows or TimeSeriesRetentionWindows()
        reference_date = today or datetime.now(UTC).date()

        energy_cutoff = reference_date - timedelta(days=windows.daily_energy_days)
        climate_cutoff = reference_date - timedelta(days=windows.climate_observations_days)

        energy_result = await self._session.execute(
            delete(DailyEnergy).where(DailyEnergy.production_date < energy_cutoff)
        )
        energy_deleted = (
            energy_result.rowcount if isinstance(energy_result, CursorResult) else 0
        ) or 0

        climate_result = await self._session.execute(
            delete(DailyClimateObservationRecord).where(
                DailyClimateObservationRecord.observation_date < climate_cutoff
            )
        )
        climate_deleted = (
            climate_result.rowcount if isinstance(climate_result, CursorResult) else 0
        ) or 0

        logger.info(
            "timeseries_retention_purge_completed",
            extra={
                "daily_energy_deleted": energy_deleted,
                "climate_observations_deleted": climate_deleted,
                "energy_cutoff": energy_cutoff.isoformat(),
                "climate_cutoff": climate_cutoff.isoformat(),
            },
        )
        return energy_deleted, climate_deleted
