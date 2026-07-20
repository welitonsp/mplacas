from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.billing.read_repository import ConfirmedBill
from mplacas.db.models import DailyEnergy, Device


async def energy_fingerprint(
    session: AsyncSession,
    *,
    confirmed_bill: ConfirmedBill,
) -> str:
    """Impressão digital dos dados de energia do ciclo de uma fatura confirmada.

    Combina contagem, soma e o carimbo de atualização mais recente das leituras
    diárias na janela do ciclo. Qualquer alteração nos dados subjacentes —
    consolidação de leitura provisória, chegada de dado tardio, correção —
    altera a impressão, invalidando o cache automaticamente. É a garantia de
    que o cache nunca serve um dashboard obsoleto.
    """
    bill = confirmed_bill.bill
    row = (
        await session.execute(
            select(
                func.count(DailyEnergy.id),
                func.coalesce(func.sum(DailyEnergy.energy_kwh), 0),
                func.max(DailyEnergy.updated_at),
            )
            .join(Device)
            .where(
                Device.plant_id == confirmed_bill.plant_id,
                DailyEnergy.production_date >= bill.cycle_start,
                DailyEnergy.production_date <= bill.cycle_end,
            )
        )
    ).one()
    count, total, latest = row
    payload = "|".join(
        (
            str(count or 0),
            str(Decimal(total or 0)),
            latest.isoformat() if latest is not None else "none",
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DashboardCacheKey:
    bill_id: uuid.UUID
    plant_id: uuid.UUID
    expected_production_kwh: str
    stable_tolerance_percent: str
    fingerprint: str


def build_cache_key(
    *,
    bill_id: uuid.UUID,
    plant_id: uuid.UUID,
    expected_production_kwh: Decimal | None,
    stable_tolerance_percent: Decimal,
    fingerprint: str,
) -> DashboardCacheKey:
    return DashboardCacheKey(
        bill_id=bill_id,
        plant_id=plant_id,
        expected_production_kwh=(
            "none" if expected_production_kwh is None else str(expected_production_kwh)
        ),
        stable_tolerance_percent=str(stable_tolerance_percent),
        fingerprint=fingerprint,
    )
