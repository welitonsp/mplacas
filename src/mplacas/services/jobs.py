from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date

from mplacas.services.collection import CollectionResult, SolarCollectionService
from mplacas.services.collection_policy import CollectionPolicy, CollectionWindow

logger = logging.getLogger(__name__)


class CollectionJobRunner:
    """Executa políticas de coleta sem acoplar o domínio a um scheduler específico."""

    def __init__(
        self,
        service: SolarCollectionService,
        *,
        plant_name: str,
        policy: CollectionPolicy | None = None,
    ) -> None:
        self._service = service
        self._plant_name = plant_name
        self._policy = policy or CollectionPolicy()

    async def run_intraday(self, today: date) -> CollectionResult:
        return await self._run(self._policy.intraday(today))

    async def run_d_plus_one(self, today: date) -> CollectionResult:
        return await self._run(self._policy.d_plus_one(today))

    async def run_weekly_backfill(self, today: date) -> CollectionResult:
        return await self._run(self._policy.weekly_backfill(today))

    async def _run(self, window: CollectionWindow) -> CollectionResult:
        logger.info(
            "solar_collection_started",
            extra={
                "reason": window.reason,
                "start": window.start.isoformat(),
                "end": window.end.isoformat(),
            },
        )
        result = await self._service.collect(
            plant_name=self._plant_name,
            start=window.start,
            end=window.end,
            consolidate_through=window.consolidate_through,
        )
        logger.info(
            "solar_collection_completed",
            extra={"reason": window.reason, **asdict(result)},
        )
        return result
