"""Read-only HTTP surface for per-inverter daily status (ADR-074, Decision 3).

Thin router: the handler opens a session, applies tenant context, delegates
to `read_service.py` for queries and `serialization.py` for shaping the
response, then closes. No calculation happens here — that stays the
exclusive responsibility of `devices/metrics.py`.
"""

from __future__ import annotations

from fastapi import APIRouter

from mplacas.core.tenancy import ReadPlant
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_principal_context
from mplacas.devices.read_service import get_daily_status
from mplacas.devices.serialization import serialize_daily_status

router = APIRouter(
    prefix="/devices",
    tags=["devices"],
)


@router.get("/daily-status")
async def daily_status(scoped: ReadPlant) -> dict[str, object]:
    """Per-inverter reporting + yield status for the most recent day.

    Always 200 within the caller's scope (ADR-074, Decision 3) —
    unavailability is a field plus one of three reason codes
    (`NOT_REPORTED`, `NO_IRRADIATION_READING`, `INSUFFICIENT_DEVICE_HISTORY`),
    never a 4xx. A device that lost communication for the whole day still
    appears in `devices[]`, with `reporting_status: "NOT_REPORTED"` — it must
    never silently vanish (ADR-074 Restriction 1).
    """
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        result = await get_daily_status(session, plant_id=scoped.plant_id)
    return serialize_daily_status(result)
