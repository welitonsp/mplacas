"""Shared tenancy helpers usable by both ``core.security`` and ``credentials``.

Kept in its own module to avoid a circular import: ``credentials.service``
needs to derive an organization-scoped :class:`PlantScope`, and
``core.security`` already depends on ``credentials.service`` (via a lazy
import) to resolve persisted credentials.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Path, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.core.authorization import PlantScope
from mplacas.core.principal import OperationsPrincipal
from mplacas.db.models import Plant
from mplacas.db.tenant_context import set_organization_context, set_tenant_context


async def plant_scope_for_organization_in_session(
    session: AsyncSession, organization_id: uuid.UUID
) -> PlantScope:
    """Derive the :class:`PlantScope` an organization is entitled to.

    Uses the given ``session`` rather than opening a new one, so callers that
    already hold a session (e.g. :class:`CredentialService`) stay within the
    same transaction/engine.
    """
    result = await session.execute(
        select(Plant.id).where(Plant.organization_id == organization_id)
    )
    plant_ids = frozenset(row[0] for row in result)

    if not plant_ids:
        return PlantScope.empty()
    return PlantScope.restricted(plant_ids)


async def plant_scope_for_organization(organization_id: uuid.UUID) -> PlantScope:
    """Derive an organization's :class:`PlantScope` using a fresh session.

    For callers (like bearer-token authentication) that do not already hold
    an open session.
    """
    from mplacas.db.session import SessionFactory

    async with SessionFactory() as session:
        await set_tenant_context(session, organization_id)
        return await plant_scope_for_organization_in_session(session, organization_id)


# ---------------------------------------------------------------------------
# Router-facing dependencies: resolve + validate ``plant_id`` against scope
# ---------------------------------------------------------------------------
#
# These wrap ``core.security``'s authentication dependencies with a thin,
# lazily-imported indirection (``_read_principal`` / ``_admin_principal``)
# rather than referencing ``require_operations_read`` / ``require_operations_key``
# directly at module scope. ``core.security`` imports this module at import
# time (see the module docstring above), so a top-level import back into
# ``core.security`` here would create a circular import.


async def _read_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> OperationsPrincipal:
    from mplacas.core.security import require_operations_read

    return await require_operations_read(
        request, authorization=authorization, x_api_key=x_api_key
    )


async def _admin_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> OperationsPrincipal:
    from mplacas.core.security import require_operations_key

    return await require_operations_key(
        request, authorization=authorization, x_api_key=x_api_key
    )


@dataclass(frozen=True, slots=True)
class ScopedPlant:
    """A ``plant_id`` already resolved and validated against the caller's scope.

    Handlers keep accessing ``scoped.principal.plant_scope`` exactly as they
    would have accessed ``principal.plant_scope`` before the migration to this
    dependency — only the manual ``principal.require_plant_access(plant_id)``
    call at the top of each handler is replaced.
    """

    plant_id: uuid.UUID
    principal: OperationsPrincipal


async def resolve_read_plant(
    principal: Annotated[OperationsPrincipal, Depends(_read_principal)],
    plant_id: uuid.UUID = Query(...),
) -> ScopedPlant:
    """Resolve a required ``plant_id`` query param for read-only endpoints.

    Raises 404 (not 403) when the plant falls outside the principal's scope,
    so the response does not reveal the existence of a plant the caller has
    no access to.
    """
    principal.require_plant_access(plant_id)
    return ScopedPlant(plant_id=plant_id, principal=principal)


async def _infer_single_plant_for_organization_in_session(
    session: AsyncSession, organization_id: uuid.UUID | None
) -> uuid.UUID:
    """Infer "the" plant for ``organization_id``, using the given ``session``.

    Shared by :func:`_infer_single_plant_for_organization` (which opens a
    fresh session for callers that do not already hold one) and callers that
    already have an open session in scope (e.g. ``telegram.router``, which
    resolves the organization and the plant within the same session/request).
    """
    query = select(Plant.id)
    if organization_id is not None:
        query = query.where(Plant.organization_id == organization_id)
    plant_ids = list((await session.execute(query.limit(2))).scalars())

    if len(plant_ids) == 1:
        return plant_ids[0]
    if len(plant_ids) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="plant_id is required when more than one plant exists",
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="plant_id is required when no plant can be inferred",
    )


async def _infer_single_plant_for_organization(
    organization_id: uuid.UUID | None,
) -> uuid.UUID:
    """Infer "the" plant when a caller omits ``plant_id``.

    Scoped to ``organization_id`` when the principal carries one (bearer-token
    or persisted-credential principals). Static operational keys have no
    ``organization_id`` and fall back to inference across all plants, matching
    the pre-existing single-tenant behaviour (see
    ``telegram.router._resolve_telegram_plant_scope``).
    """
    from mplacas.db.session import SessionFactory

    async with SessionFactory() as session:
        await set_organization_context(session, organization_id)
        return await _infer_single_plant_for_organization_in_session(
            session, organization_id
        )


async def resolve_admin_plant_scope(
    principal: OperationsPrincipal,
    plant_id: uuid.UUID | None,
) -> ScopedPlant:
    """Resolve + validate a ``plant_id`` an admin caller may supply anywhere.

    Shared by :func:`resolve_admin_plant` (``plant_id`` as a query param) and
    callers that receive ``plant_id`` from elsewhere (e.g. a request body),
    such as ``billing.router.intake_bill_text``. When omitted, infers the
    single plant belonging to the principal's organization (409 if the
    organization has zero or more than one plant).
    """
    resolved = (
        plant_id
        if plant_id is not None
        else await _infer_single_plant_for_organization(principal.organization_id)
    )
    principal.require_plant_access(resolved)
    return ScopedPlant(plant_id=resolved, principal=principal)


async def resolve_admin_plant(
    principal: Annotated[OperationsPrincipal, Depends(_admin_principal)],
    plant_id: uuid.UUID | None = Query(default=None),
) -> ScopedPlant:
    """Resolve an optional ``plant_id`` query param for admin endpoints.

    When omitted, infers the single plant belonging to the principal's
    organization (409 if the organization has zero or more than one plant).
    """
    return await resolve_admin_plant_scope(principal, plant_id)


async def resolve_admin_plant_path(
    principal: Annotated[OperationsPrincipal, Depends(_admin_principal)],
    plant_id: uuid.UUID = Path(...),
) -> ScopedPlant:
    """Resolve a required ``plant_id`` *path* param for admin endpoints.

    Same resolve+validate semantics as :func:`resolve_admin_plant` (404, not
    403, for a plant outside the caller's organization), but for routes that
    carry ``plant_id`` in the URL path (e.g. ``/plants/{plant_id}/...``)
    rather than as a query parameter. A route cannot use
    :func:`resolve_admin_plant` for this case: FastAPI resolves a path
    parameter and a same-named ``Query`` parameter declared by a sub-dependant
    as a conflict, not a merge.
    """
    return await resolve_admin_plant_scope(principal, plant_id)


async def resolve_read_plant_path(
    principal: Annotated[OperationsPrincipal, Depends(_read_principal)],
    plant_id: uuid.UUID = Path(...),
) -> ScopedPlant:
    """Resolve a read-only plant path without disclosing cross-tenant rows."""
    principal.require_plant_access(plant_id)
    return ScopedPlant(plant_id=plant_id, principal=principal)


ReadPlant = Annotated[ScopedPlant, Depends(resolve_read_plant)]
ReadPlantPath = Annotated[ScopedPlant, Depends(resolve_read_plant_path)]
AdminPlant = Annotated[ScopedPlant, Depends(resolve_admin_plant)]
AdminPlantPath = Annotated[ScopedPlant, Depends(resolve_admin_plant_path)]
AdminPrincipal = Annotated[OperationsPrincipal, Depends(_admin_principal)]
ReadPrincipal = Annotated[OperationsPrincipal, Depends(_read_principal)]


# ---------------------------------------------------------------------------
# Platform vs. organization admin discrimination (PR-1 of the onboarding plan)
# ---------------------------------------------------------------------------
#
# ``AdminPrincipal`` alone only proves the caller holds an ADMIN-role
# credential; it does not say whether that credential belongs to the
# platform operator (the static ``MPLACAS_OPERATIONS_API_KEY``, today the only
# admin principal with no ``organization_id``) or to a tenant organization
# (bearer JWT or a persisted credential created for a specific organization).
# The two dependencies below make that distinction explicit for routers that
# need to tell the two apart, without changing any existing router yet.


async def require_platform_admin(
    principal: Annotated[OperationsPrincipal, Depends(_admin_principal)],
) -> OperationsPrincipal:
    """Require an ADMIN principal that belongs to the platform, not a tenant.

    Today, in practice, only the static operational API key qualifies: it is
    the sole admin principal with no ``organization_id`` and an unrestricted
    ``PlantScope``. Any principal with an ``organization_id`` set (bearer JWT
    or persisted credential) is rejected with 403.
    """
    if principal.organization_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this operation requires a platform administrator",
        )
    return principal


async def require_organization_admin(
    principal: Annotated[OperationsPrincipal, Depends(_admin_principal)],
) -> OperationsPrincipal:
    """Require an ADMIN principal that belongs to a specific organization.

    Accepts any ADMIN principal with ``organization_id`` set, regardless of
    whether its ``PlantScope`` ended up restricted-by-inheritance (the normal
    case for a persisted ADMIN credential, which is never plant-restricted
    explicitly — see ``CredentialService.create``) or otherwise; the
    presence of ``organization_id`` is what identifies "which organization",
    not the granularity of the plant scope. Rejects platform principals
    (``organization_id is None``) with 409, since there is no organization to
    administer.
    """
    if principal.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this operation requires an organization; none can be inferred "
            "for a platform administrator",
        )
    return principal


PlatformPrincipal = Annotated[OperationsPrincipal, Depends(require_platform_admin)]
OrgAdminPrincipal = Annotated[OperationsPrincipal, Depends(require_organization_admin)]
