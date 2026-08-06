"""Shared envelope shape for the fan-out execution handlers (ADR-069 § E.11.2).

Used by ``alerts/router.py``, ``climate/router.py`` and
``orchestration/router.py`` — the four endpoints that switched from
``AdminPlant`` (a single resolved plant) to ``AdminPlantFanout`` (a set of
plants, § E.5) in the same etapa (E7). Kept as a standalone module rather
than inlined in one of the four routers because all four need the identical
``{count, succeeded, failed, skipped, items}`` shape and none of them should
own it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.db.models import Plant

FanoutOutcome = Literal["succeeded", "failed", "skipped"]


@dataclass(frozen=True, slots=True)
class FanoutItem:
    """One plant's outcome within a fan-out response (ADR-069 § E.11.2)."""

    plant_id: uuid.UUID
    plant_name: str
    outcome: FanoutOutcome
    error: dict[str, str] | None
    result: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "plant_id": str(self.plant_id),
            "plant_name": self.plant_name,
            "outcome": self.outcome,
            "error": self.error,
            "result": self.result,
        }


def fanout_envelope(items: list[FanoutItem]) -> dict[str, Any]:
    """Build the ``{count, succeeded, failed, skipped, items}`` envelope."""

    return {
        "count": len(items),
        "succeeded": sum(1 for item in items if item.outcome == "succeeded"),
        "failed": sum(1 for item in items if item.outcome == "failed"),
        "skipped": sum(1 for item in items if item.outcome == "skipped"),
        "items": [item.as_dict() for item in items],
    }


def error_detail(exc: BaseException, *, message: str) -> dict[str, str]:
    """Build the item-level ``error`` object (ADR-069 § E.11.2).

    ``code`` mirrors the identifier the handlers already emit in structured
    logs today (``type(exc).__name__.upper()``); ``message`` must be the
    already-sanitized text the handler would otherwise put in the
    ``HTTPException`` ``detail`` for that same exception — never a new
    message invented for the fan-out path.
    """

    return {"code": type(exc).__name__.upper(), "message": message}


async def fetch_plant_name(session: AsyncSession, plant_id: uuid.UUID) -> str:
    """Look up ``Plant.name`` for the envelope item, defensively.

    Falls back to the stringified id if the plant vanished between
    resolution (``resolve_admin_plant_fanout``) and this per-plant session —
    a narrow race, not expected in practice, but the envelope must never
    raise trying to describe a failure.
    """

    result = await session.execute(select(Plant.name).where(Plant.id == plant_id))
    name = result.scalar_one_or_none()
    return name if name is not None else str(plant_id)
