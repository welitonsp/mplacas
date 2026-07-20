from __future__ import annotations

import uuid
from collections import OrderedDict
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.core.authorization import UNRESTRICTED_PLANT_SCOPE, PlantScope
from mplacas.billing.read_repository import ConfirmedBillReadRepository
from mplacas.intelligence.dashboard_cache import (
    DashboardCacheKey,
    build_cache_key,
    energy_fingerprint,
)
from mplacas.intelligence.executive_service import (
    EnergyCycleNotFoundError,
    ExecutiveEnergyDashboard,
    build_executive_dashboard,
)


class ExecutiveDashboardReadModel:
    """Read-model com cache invalidado por impressão digital dos dados.

    O cache é consultado por uma chave que inclui a impressão digital dos dados
    de energia do ciclo. Como a impressão muda sempre que os dados mudam, um
    acerto de cache só ocorre quando o dashboard seria idêntico — nunca há risco
    de servir resultado obsoleto. O custo por acesso cai de recomputar o caminho
    executivo inteiro para uma consulta agregada leve.
    """

    def __init__(self, *, max_entries: int = 128) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._max_entries = max_entries
        self._entries: OrderedDict[DashboardCacheKey, ExecutiveEnergyDashboard] = (
            OrderedDict()
        )
        self.hits = 0
        self.misses = 0

    async def get(
        self,
        session: AsyncSession,
        *,
        plant_id: uuid.UUID,
        expected_production_kwh: Decimal | None = None,
        stable_tolerance_percent: Decimal = Decimal("2.0"),
        plant_scope: PlantScope = UNRESTRICTED_PLANT_SCOPE,
    ) -> ExecutiveEnergyDashboard:
        latest_bill = await ConfirmedBillReadRepository(
            session,
            plant_scope=plant_scope,
        ).latest(plant_id=plant_id)
        if latest_bill is None:
            raise EnergyCycleNotFoundError("confirmed bill not found for plant")

        fingerprint = await energy_fingerprint(session, confirmed_bill=latest_bill)
        key = build_cache_key(
            bill_id=latest_bill.id,
            plant_id=plant_id,
            expected_production_kwh=expected_production_kwh,
            stable_tolerance_percent=stable_tolerance_percent,
            fingerprint=fingerprint,
        )

        cached = self._entries.get(key)
        if cached is not None:
            self._entries.move_to_end(key)
            self.hits += 1
            return cached

        dashboard = await build_executive_dashboard(
            session,
            plant_id=plant_id,
            expected_production_kwh=expected_production_kwh,
            stable_tolerance_percent=stable_tolerance_percent,
            plant_scope=plant_scope,
        )
        self._store(key, dashboard)
        self.misses += 1
        return dashboard

    def _store(
        self, key: DashboardCacheKey, dashboard: ExecutiveEnergyDashboard
    ) -> None:
        self._entries[key] = dashboard
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()
