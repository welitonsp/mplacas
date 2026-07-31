"""PR-1: every OperationsPrincipal with organization_id set must carry a
restricted PlantScope, regardless of which authentication path produced it.

Covers the three sources of OperationsPrincipal that carry organization_id:
  - JWT bearer tokens (core.security._authenticate_bearer)
  - persisted ADMIN credentials without an explicit plant scope
  - persisted READ credentials with an explicit plant scope
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
from mplacas.core import security
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.credentials.service import CredentialService
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.organizations.db_models import OrganizationRecord

PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_org_with_plant(factory) -> uuid.UUID:
    async with factory() as session:
        organization_id = uuid.uuid4()
        session.add(
            OrganizationRecord(
                id=organization_id,
                name="Tenant",
                slug=f"tenant-{organization_id.hex[:8]}",
                active=True,
            )
        )
        session.add(
            Plant(id=PLANT_A, organization_id=organization_id, name="Plant A")
        )
        await session.flush()
        await session.commit()
        return organization_id


@pytest.mark.asyncio
async def test_jwt_bearer_principal_is_org_restricted(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret")
    get_settings.cache_clear()
    factory = await _factory()
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    organization_id = await _seed_org_with_plant(factory)
    token = encode_access_token(uuid.uuid4(), organization_id, OperationsRole.READ.value)

    principal = await security._authenticate_bearer(token, require_admin=False)

    assert principal is not None
    assert principal.organization_id is not None
    assert principal.plant_scope.is_restricted is True

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_persisted_admin_credential_without_plant_ids_is_org_restricted() -> None:
    factory = await _factory()
    organization_id = await _seed_org_with_plant(factory)

    async with factory() as session:
        _, secret = await CredentialService(session).create(
            name="admin-org",
            role=OperationsRole.ADMIN,
            organization_id=organization_id,
        )
        await session.commit()

    async with factory() as session:
        principal = await CredentialService(session).resolve(secret)

    assert principal is not None
    assert principal.organization_id is not None
    assert principal.plant_scope.is_restricted is True


@pytest.mark.asyncio
async def test_persisted_read_credential_with_plant_ids_is_org_restricted() -> None:
    factory = await _factory()
    organization_id = await _seed_org_with_plant(factory)

    async with factory() as session:
        _, secret = await CredentialService(session).create(
            name="leitor-org",
            role=OperationsRole.READ,
            organization_id=organization_id,
            plant_ids=frozenset({PLANT_A}),
        )
        await session.commit()

    async with factory() as session:
        principal = await CredentialService(session).resolve(secret)

    assert principal is not None
    assert principal.organization_id is not None
    assert principal.plant_scope.is_restricted is True


def test_tenancy_resolves_scoped_plant_hints_without_importing_security() -> None:
    """PR-2: ``core.tenancy`` must not depend on import order for correctness.

    Regression test for a real bug the reviewer reproduced: when
    ``OperationsPrincipal`` was only imported under ``TYPE_CHECKING`` in
    ``core.tenancy`` (with ``core.security`` patching the real class into
    ``tenancy``'s namespace as a side effect of its own import), importing
    ``mplacas.core.tenancy`` on its own — without anything having imported
    ``mplacas.core.security`` first in the same process — left
    ``resolve_read_plant``/``resolve_admin_plant``'s forward reference to
    ``OperationsPrincipal`` unresolved. FastAPI resolves those annotations via
    ``typing.get_type_hints`` when building the dependency graph for
    ``ReadPlant``/``AdminPlant``, so this silently corrupted route
    registration for any router that imported only ``core.tenancy`` — a
    scenario every subsequent PR migrating billing/alerts/climate to
    ReadPlant/AdminPlant would have hit as soon as those routers stopped
    importing ``core.security`` directly.

    Runs in a fresh subprocess (not just a fresh module cache) so that no
    other test in this same process has already imported ``core.security``
    and made the bug impossible to observe.
    """
    script = (
        "import sys\n"
        "assert 'mplacas.core.security' not in sys.modules\n"
        "from mplacas.core import tenancy\n"
        "from typing import get_type_hints\n"
        "get_type_hints(tenancy.resolve_read_plant, include_extras=True)\n"
        "get_type_hints(tenancy.resolve_admin_plant, include_extras=True)\n"
        "get_type_hints(tenancy._read_principal, include_extras=True)\n"
        "get_type_hints(tenancy._admin_principal, include_extras=True)\n"
        "assert 'mplacas.core.security' not in sys.modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
