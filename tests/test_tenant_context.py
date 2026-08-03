from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.core.principal import OperationsPrincipal, OperationsRole
from mplacas.db.tenant_context import (
    set_platform_context,
    set_principal_context,
    set_tenant_context,
)


async def test_tenant_context_is_transaction_local_and_disables_bypass() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.get_bind.return_value = None
    session.info = {}
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
    session.get_bind.return_value = None
    session.info = {}

    await set_platform_context(session)

    statements = [str(call.args[0]) for call in session.execute.await_args_list]
    assert statements == [
        "SELECT set_config('mplacas.organization_id', '', true)",
        "SELECT set_config('mplacas.platform_bypass', 'on', true)",
    ]


async def test_principal_context_selects_tenant_or_platform() -> None:
    tenant_session = AsyncMock(spec=AsyncSession)
    tenant_session.get_bind.return_value = None
    tenant_session.info = {}
    platform_session = AsyncMock(spec=AsyncSession)
    platform_session.get_bind.return_value = None
    platform_session.info = {}
    organization_id = uuid.uuid4()

    await set_principal_context(
        tenant_session,
        OperationsPrincipal(
            role=OperationsRole.READ,
            credential_id="tenant",
            organization_id=organization_id,
        ),
    )
    await set_principal_context(
        platform_session,
        OperationsPrincipal(role=OperationsRole.ADMIN, credential_id="platform"),
    )

    assert tenant_session.info == {
        "mplacas.organization_id": organization_id,
        "mplacas.platform_bypass": False,
    }
    assert platform_session.info == {
        "mplacas.organization_id": None,
        "mplacas.platform_bypass": True,
    }
