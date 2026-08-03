from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PrincipalWithOrganization(Protocol):
    @property
    def organization_id(self) -> uuid.UUID | None: ...


def _uses_postgresql(session: AsyncSession) -> bool:
    get_bind = getattr(session, "get_bind", None)
    if get_bind is None:
        # Lightweight test doubles are not database connections. A real
        # AsyncSession always exposes get_bind(), so production cannot skip
        # PostgreSQL context initialization through this branch.
        return False
    bind = get_bind()
    if bind is None:
        return True
    return getattr(bind.dialect, "name", None) == "postgresql"


def _record_context(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID | None,
    platform_bypass: bool,
) -> None:
    info = getattr(session, "info", None)
    if info is None:
        return
    info["mplacas.organization_id"] = organization_id
    info["mplacas.platform_bypass"] = platform_bypass


async def set_tenant_context(session: AsyncSession, organization_id: uuid.UUID) -> None:
    """Bind a tenant to the current transaction using a PostgreSQL LOCAL setting."""

    _record_context(
        session,
        organization_id=organization_id,
        platform_bypass=False,
    )
    if not _uses_postgresql(session):
        return

    await session.execute(
        text("SELECT set_config('mplacas.organization_id', :organization_id, true)"),
        {"organization_id": str(organization_id)},
    )
    await session.execute(
        text("SELECT set_config('mplacas.platform_bypass', 'off', true)")
    )


async def set_platform_context(session: AsyncSession) -> None:
    """Request platform bypass; RLS must additionally require a privileged DB role."""

    _record_context(session, organization_id=None, platform_bypass=True)
    if not _uses_postgresql(session):
        return

    await session.execute(
        text("SELECT set_config('mplacas.organization_id', '', true)")
    )
    await session.execute(
        text("SELECT set_config('mplacas.platform_bypass', 'on', true)")
    )


async def set_principal_context(
    session: AsyncSession, principal: PrincipalWithOrganization
) -> None:
    """Bind tenant principals and require explicit platform context for global callers."""

    await set_organization_context(session, principal.organization_id)


async def set_organization_context(
    session: AsyncSession, organization_id: uuid.UUID | None
) -> None:
    """Bind an optional organization, treating absence as explicit platform work."""

    if organization_id is None:
        await set_platform_context(session)
    else:
        await set_tenant_context(session, organization_id)
