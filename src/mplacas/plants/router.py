"""HTTP layer for ``/plants``.

Each endpoint opens the session, applies the caller's tenant context, delegates
the domain work to ``PlantService``, translates domain errors to HTTP status
codes, records the audit event (which needs the ``Request``) and owns the
commit. Queries and mutation rules live in ``plants.service``.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request, status

from mplacas.audit.repository import AuditEventRepository
from mplacas.core.tenancy import AdminPlantPath, ReadPlantPath, ReadPrincipal
from mplacas.db.models import Plant
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_principal_context
from mplacas.plants.schemas import (
    PlantExpansionProposalUpdateRequest,
    PlantExpansionProposalView,
    PlantFinancialConfigurationUpdateRequest,
    PlantFinancialConfigurationView,
    PlantLocationUpdateRequest,
    PlantSetupView,
    PlantTechnicalConfigurationUpdateRequest,
    PlantTechnicalConfigurationView,
)
from mplacas.plants.service import (
    DeviceNotFoundError,
    PlantListEntry,
    PlantNotFoundError,
    PlantService,
)

router = APIRouter(prefix="/plants", tags=["plants"])


def _plant_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plant not found")


def _plant_list_item(entry: PlantListEntry) -> dict[str, object]:
    plant = entry.plant
    return {
        "id": str(plant.id),
        "name": plant.name,
        "installed_power_kwp": (
            str(plant.installed_power_kwp)
            if plant.installed_power_kwp is not None
            else None
        ),
        "is_default": entry.is_default,
    }


def _plant_location_view(plant: Plant) -> dict[str, object]:
    return {
        "plant_id": str(plant.id),
        "latitude": plant.latitude,
        "longitude": plant.longitude,
    }


@router.get("")
async def list_plants(principal: ReadPrincipal) -> dict[str, object]:
    """List the plants visible to the caller (ADR-069, Etapa A + E8).

    Filters by ``principal.organization_id`` when set — a static platform
    operational key has none, and lists across every organization, mirroring
    ``organizations.router.list_organizations``. Then intersects with
    ``principal.plant_scope``, since a persisted credential (ADR-043) may
    carry a scope restricted to a subset of the organization's plants.

    Each item also carries ``is_default``, derived from
    ``organizations.default_plant_id`` (ADR-069, § E.8). For a static
    platform key, plants from multiple organizations are listed together, so
    ``is_default`` is resolved per-plant against *its own* organization's
    default — never a single global default — using one extra query that
    fetches every relevant organization's ``default_plant_id`` in bulk,
    avoiding an N+1 query per item.
    """
    async with SessionFactory() as session:
        await set_principal_context(session, principal)
        entries = await PlantService(session).list_visible(
            organization_id=principal.organization_id,
            plant_scope=principal.plant_scope,
        )

    items = [_plant_list_item(entry) for entry in entries]
    return {"count": len(items), "items": items}


@router.get("/{plant_id}/setup", response_model=PlantSetupView)
async def get_plant_setup(scoped: ReadPlantPath) -> PlantSetupView:
    """Estado do cadastro da usina (área "Dados da usina" do frontend).

    Uma leitura com tudo o que o dono informou e o checklist do que falta. Os
    PATCH de configuração técnica, localização e investimento continuam sendo
    as rotas de escrita; esta é só a leitura que as reúne.
    """
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        service = PlantService(session)
        try:
            plant = await service.get(scoped.plant_id)
        except PlantNotFoundError:
            raise _plant_not_found() from None
        return await service.setup_status(plant)


@router.get(
    "/{plant_id}/technical-configuration",
    response_model=PlantTechnicalConfigurationView,
)
async def get_plant_technical_configuration(
    scoped: ReadPlantPath,
) -> PlantTechnicalConfigurationView:
    """Return plant geometry and power ratings within the caller's tenant."""
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        service = PlantService(session)
        try:
            plant = await service.get(scoped.plant_id)
        except PlantNotFoundError:
            raise _plant_not_found() from None
        return await service.technical_configuration(plant)


@router.patch(
    "/{plant_id}/technical-configuration",
    response_model=PlantTechnicalConfigurationView,
)
async def update_plant_technical_configuration(
    request: Request,
    scoped: AdminPlantPath,
    payload: PlantTechnicalConfigurationUpdateRequest,
) -> PlantTechnicalConfigurationView:
    """Atomically update plant and inverter technical configuration."""
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        service = PlantService(session)
        try:
            plant = await service.get(scoped.plant_id)
        except PlantNotFoundError:
            raise _plant_not_found() from None

        try:
            await service.update_technical_configuration(plant, payload)
        except DeviceNotFoundError:
            # Plant fields may already be mutated in this session; discard
            # them so the update is all-or-nothing.
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="device not found",
            ) from None

        await AuditEventRepository(session).record(
            request,
            action="plant.technical_configuration_updated",
            resource_type="plant",
            resource_id=str(plant.id),
            outcome="SUCCEEDED",
            details=payload.model_dump(mode="json", exclude_unset=True),
        )
        response = await service.technical_configuration(plant)
        await session.commit()
        return response


@router.get(
    "/{plant_id}/financial-configuration",
    response_model=PlantFinancialConfigurationView,
)
async def get_plant_financial_configuration(
    scoped: ReadPlantPath,
) -> PlantFinancialConfigurationView:
    """Return the plant's CAPEX input (ADR-067) within the caller's tenant."""
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        try:
            plant = await PlantService(session).get(scoped.plant_id)
        except PlantNotFoundError:
            raise _plant_not_found() from None
        return PlantService.financial_configuration(plant)


@router.patch(
    "/{plant_id}/financial-configuration",
    response_model=PlantFinancialConfigurationView,
)
async def update_plant_financial_configuration(
    request: Request,
    scoped: AdminPlantPath,
    payload: PlantFinancialConfigurationUpdateRequest,
) -> PlantFinancialConfigurationView:
    """Set or clear the plant's CAPEX input feeding the financial-return
    indicator (ADR-067).

    ``AdminPlantPath`` resolves ``plant_id`` from the URL path and validates
    it against the caller's organization scope, returning 404 (not 403) for
    a plant belonging to another organization — the same convention used by
    every other plant-scoped router (see ``core.tenancy`` and
    ``update_plant_location`` below).
    """
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        service = PlantService(session)
        try:
            plant = await service.get(scoped.plant_id)
        except PlantNotFoundError:
            raise _plant_not_found() from None

        await service.update_financial_configuration(plant, payload)
        await AuditEventRepository(session).record(
            request,
            action="plant.financial_configuration_updated",
            resource_type="plant",
            resource_id=str(plant.id),
            outcome="SUCCEEDED",
            details=payload.model_dump(mode="json", exclude_unset=True),
        )
        response = PlantService.financial_configuration(plant)
        await session.commit()
        return response


@router.patch(
    "/{plant_id}/expansion-proposal",
    response_model=PlantExpansionProposalView,
)
async def update_plant_expansion_proposal(
    request: Request,
    scoped: AdminPlantPath,
    payload: PlantExpansionProposalUpdateRequest,
) -> PlantExpansionProposalView:
    """Valor da proposta de ampliação (ADR-089, etapa 2), para o retorno.

    Só ADMIN da organização; usina fora do escopo é 404. Quem informou e
    quando fica na auditoria (``plant.expansion_proposal_updated``).
    """
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        service = PlantService(session)
        try:
            plant = await service.get(scoped.plant_id)
        except PlantNotFoundError:
            raise _plant_not_found() from None

        await service.update_expansion_proposal(plant, payload, today=date.today())
        await AuditEventRepository(session).record(
            request,
            action="plant.expansion_proposal_updated",
            resource_type="plant",
            resource_id=str(plant.id),
            outcome="SUCCEEDED",
            details=payload.model_dump(mode="json"),
        )
        response = PlantService.expansion_proposal(plant)
        await session.commit()
        return response


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
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        service = PlantService(session)
        # ``AdminPlantPath`` already proved ``plant_id`` exists and is in scope
        # (it queries ``Plant.id`` to build the caller's ``PlantScope``), so a
        # missing row here would indicate a race (e.g. the plant was deleted
        # between scope resolution and this fetch), not an authorization gap.
        try:
            plant = await service.get(scoped.plant_id)
        except PlantNotFoundError:
            raise _plant_not_found() from None

        await service.update_location(plant, payload)
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
