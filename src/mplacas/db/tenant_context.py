from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_tenant_context(session: AsyncSession, organization_id: uuid.UUID) -> None:
    """Bind a tenant to the current transaction using a PostgreSQL LOCAL setting."""

    await session.execute(
        text("SELECT set_config('mplacas.organization_id', :organization_id, true)"),
        {"organization_id": str(organization_id)},
    )
    await session.execute(
        text("SELECT set_config('mplacas.platform_bypass', 'off', true)")
    )


async def set_platform_context(session: AsyncSession) -> None:
    """Request platform bypass; RLS must additionally require a privileged DB role."""

    await session.execute(
        text("SELECT set_config('mplacas.organization_id', '', true)")
    )
    await session.execute(
        text("SELECT set_config('mplacas.platform_bypass', 'on', true)")
    )
