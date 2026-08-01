from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from mplacas.audit.repository import AuditEventRepository
from mplacas.core.tenancy import AdminPlantPath
from mplacas.db.models import Plant
from mplacas.db.session import SessionFactory

router = APIRouter(prefix="/plants", tags=["plants"])


class PlantLocationUpdateRequest(BaseModel):
    """Geographic coordinates enabling climate collection for a plant.

    Bounds match the ones already enforced defensively in
    ``climate.collection_service.collect_and_persist_daily_climate`` (a plant
    with out-of-range coordinates would otherwise persist here only to be
    rejected there, opaquely, the next time collection runs).
    """

    latitude: Decimal = Field(ge=-90, le=90)
    longitude: Decimal = Field(ge=-180, le=180)


def _plant_location_view(plant: Plant) -> dict[str, object]:
    return {
        "plant_id": str(plant.id),
        "latitude": plant.latitude,
        "longitude": plant.longitude,
    }


@router.patch("/{plant_id}/location")
async def update_plant_location(
    request: Request,
    scoped: AdminPlantPath,
    payload: PlantLocationUpdateRequest,
) -> dict[str, object]:
    """Set the latitude/longitude used by climate collection for a plant.

    ``AdminPlantPath`` resolves ``plant_id`` from the URL path and validates it
    against the caller's organization scope, returning 404 (not 403) for a
    plant belonging to another organization — the same convention used by
    every other plant-scoped router (see ``core.tenancy``).
    """
    plant_id = scoped.plant_id
    async with SessionFactory() as session:
        # ``AdminPlantPath`` already proved ``plant_id`` exists and is in scope
        # (it queries ``Plant.id`` to build the caller's ``PlantScope``), so a
        # missing row here would indicate a race (e.g. the plant was deleted
        # between scope resolution and this fetch), not an authorization gap.
        plant = await session.get(Plant, plant_id)
        if plant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="plant not found"
            )

        plant.latitude = payload.latitude
        plant.longitude = payload.longitude
        await session.flush()

        await AuditEventRepository(session).record(
            request,
            action="plant.location_updated",
            resource_type="plant",
            resource_id=str(plant.id),
            outcome="SUCCEEDED",
            details={
                "latitude": str(payload.latitude),
                "longitude": str(payload.longitude),
            },
        )
        await session.commit()

        return _plant_location_view(plant)
