"""Shared tenancy helpers usable by both ``core.security`` and ``credentials``.

Kept in its own module to avoid a circular import: ``credentials.service``
needs to derive an organization-scoped :class:`PlantScope`, and
``core.security`` already depends on ``credentials.service`` (via a lazy
import) to resolve persisted credentials.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.core.authorization import PlantScope
from mplacas.db.models import Plant


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
        return await plant_scope_for_organization_in_session(session, organization_id)
