from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.db.tenant_context import set_platform_context, set_tenant_context


async def test_tenant_context_is_transaction_local_and_disables_bypass() -> None:
    session = AsyncMock(spec=AsyncSession)
    organization_id = uuid.uuid4()

    await set_tenant_context(session, organization_id)

    assert session.execute.await_count == 2
    first, second = session.execute.await_args_list
    assert "set_config('mplacas.organization_id', :organization_id, true)" in str(
        first.args[0]
    )
    assert first.args[1] == {"organization_id": str(organization_id)}
    assert "set_config('mplacas.platform_bypass', 'off', true)" in str(second.args[0])


async def test_platform_context_is_explicit_and_clears_tenant() -> None:
    session = AsyncMock(spec=AsyncSession)

    await set_platform_context(session)

    statements = [str(call.args[0]) for call in session.execute.await_args_list]
    assert statements == [
        "SELECT set_config('mplacas.organization_id', '', true)",
        "SELECT set_config('mplacas.platform_bypass', 'on', true)",
    ]
