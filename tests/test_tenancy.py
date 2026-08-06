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
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.db.session as db_session
from mplacas.core import security
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.security import OperationsRole
from mplacas.core.tenancy import (
    _infer_single_plant_for_organization_in_session,
    require_organization_admin,
    require_platform_admin,
)
from mplacas.credentials.service import CredentialService
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.organizations.db_models import OrganizationRecord

PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
_TEST_ENGINES = []


@pytest.fixture(autouse=True)
async def _dispose_test_engines():
    yield
    while _TEST_ENGINES:
        await _TEST_ENGINES.pop().dispose()


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _TEST_ENGINES.append(engine)
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
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
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


# ---------------------------------------------------------------------------
# PR-1: require_platform_admin / require_organization_admin discrimination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_key_principal_is_platform_admin_not_org_admin(monkeypatch) -> None:
    """The static operational API key (organization_id=None, unrestricted)
    is the platform admin: it passes require_platform_admin and gets 409 from
    require_organization_admin (no organization to administer)."""
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "static-admin-key")
    get_settings.cache_clear()

    fake_request = SimpleNamespace(
        state=SimpleNamespace(), method="POST", url=SimpleNamespace(path="/test")
    )
    principal = await security.require_operations_key(
        request=fake_request, authorization=None, x_api_key="static-admin-key"
    )

    assert principal.organization_id is None
    assert principal.plant_scope.is_restricted is False

    result = await require_platform_admin(principal)
    assert result is principal

    with pytest.raises(HTTPException) as exc_info:
        await require_organization_admin(principal)
    assert exc_info.value.status_code == 409

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_bearer_jwt_principal_is_org_admin_not_platform_admin(monkeypatch) -> None:
    """A bearer JWT ADMIN principal (organization_id set) passes
    require_organization_admin and gets 403 from require_platform_admin."""
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()
    factory = await _factory()
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    organization_id = await _seed_org_with_plant(factory)
    token = encode_access_token(uuid.uuid4(), organization_id, OperationsRole.ADMIN.value)

    principal = await security._authenticate_bearer(token, require_admin=True)
    assert principal is not None
    assert principal.organization_id == organization_id

    result = await require_organization_admin(principal)
    assert result is principal

    with pytest.raises(HTTPException) as exc_info:
        await require_platform_admin(principal)
    assert exc_info.value.status_code == 403

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_persisted_admin_credential_without_plant_ids_passes_org_admin() -> None:
    """A persisted ADMIN credential with an organization is org-restricted via
    inheritance (plant_scope.is_restricted is True) but must still pass
    require_organization_admin: organization_id, not plant-scope granularity,
    is what identifies "which organization" here."""
    factory = await _factory()
    organization_id = await _seed_org_with_plant(factory)

    async with factory() as session:
        _, secret = await CredentialService(session).create(
            name="admin-org-2",
            role=OperationsRole.ADMIN,
            organization_id=organization_id,
        )
        await session.commit()

    async with factory() as session:
        principal = await CredentialService(session).resolve(secret)

    assert principal is not None
    assert principal.organization_id == organization_id
    assert principal.plant_scope.is_restricted is True

    result = await require_organization_admin(principal)
    assert result is principal

    with pytest.raises(HTTPException) as exc_info:
        await require_platform_admin(principal)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# ADR-069 § E.2 -- `_infer_single_plant_for_organization_in_session` resolution
# order: (a) explicit plant_id [handled upstream by
# resolve_admin_plant_scope, not this function]; (b) organization's
# default_plant_id, revalidated by JOIN; (c) the organization's only plant,
# as a fallback; (d) 409.
# ---------------------------------------------------------------------------


async def _seed_org_with_plants(
    factory, plant_count: int, default_plant_index: int | None = None
) -> tuple[uuid.UUID, list[uuid.UUID]]:
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
        plant_ids = [uuid.uuid4() for _ in range(plant_count)]
        for index, plant_id in enumerate(plant_ids):
            session.add(
                Plant(
                    id=plant_id,
                    organization_id=organization_id,
                    name=f"Plant {index}",
                )
            )
        await session.flush()
        if default_plant_index is not None:
            org = await session.get(OrganizationRecord, organization_id)
            assert org is not None
            org.default_plant_id = plant_ids[default_plant_index]
            await session.flush()
        await session.commit()
        return organization_id, plant_ids


@pytest.mark.asyncio
async def test_infer_plant_explicit_plant_id_bypasses_inference(monkeypatch) -> None:
    """Branch (a): resolve_admin_plant_scope uses the explicit plant_id
    directly, never calling into the inference helper at all."""
    from mplacas.core.authorization import PlantScope
    from mplacas.core.principal import OperationsPrincipal
    from mplacas.core.tenancy import resolve_admin_plant_scope

    factory = await _factory()
    organization_id, plant_ids = await _seed_org_with_plants(factory, plant_count=2)
    monkeypatch.setattr(db_session, "SessionFactory", factory)

    principal = OperationsPrincipal(
        role=OperationsRole.ADMIN,
        credential_id="synthetic-test-credential",
        organization_id=organization_id,
        plant_scope=PlantScope.unrestricted(),
    )
    scoped = await resolve_admin_plant_scope(principal, plant_ids[1])
    assert scoped.plant_id == plant_ids[1]


@pytest.mark.asyncio
async def test_infer_plant_uses_valid_default() -> None:
    """Branch (b): the organization's default_plant_id resolves directly,
    without needing to count plants."""
    factory = await _factory()
    organization_id, plant_ids = await _seed_org_with_plants(
        factory, plant_count=2, default_plant_index=1
    )

    async with factory() as session:
        resolved = await _infer_single_plant_for_organization_in_session(
            session, organization_id
        )

    assert resolved == plant_ids[1]


@pytest.mark.asyncio
async def test_infer_plant_falls_back_to_single_plant_without_default() -> None:
    """Branch (c): no default set, but exactly one plant exists."""
    factory = await _factory()
    organization_id, plant_ids = await _seed_org_with_plants(factory, plant_count=1)

    async with factory() as session:
        resolved = await _infer_single_plant_for_organization_in_session(
            session, organization_id
        )

    assert resolved == plant_ids[0]


@pytest.mark.asyncio
async def test_infer_plant_raises_409_with_no_default_and_multiple_plants() -> None:
    """Branch (d): no default, more than one plant -> 409 with an actionable
    message pointing at PATCH /organizations/{id}."""
    factory = await _factory()
    organization_id, _plant_ids = await _seed_org_with_plants(factory, plant_count=2)

    async with factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await _infer_single_plant_for_organization_in_session(
                session, organization_id
            )

    assert exc_info.value.status_code == 409
    assert "default_plant_id" in exc_info.value.detail


@pytest.mark.asyncio
async def test_infer_plant_raises_409_with_zero_plants() -> None:
    factory = await _factory()
    organization_id, _plant_ids = await _seed_org_with_plants(factory, plant_count=0)

    async with factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await _infer_single_plant_for_organization_in_session(
                session, organization_id
            )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_infer_plant_ignores_default_pointing_to_another_organizations_plant() -> None:  # noqa: E501
    """The most important test of this etapa: a stale/foreign default must
    never leak another organization's plant. If ``default_plant_id`` on
    organization A were ever set to a plant owned by organization B (the
    join-revalidation's whole reason to exist -- this should never happen via
    the supported write path, but the resolver must defend against it
    anyway), the JOIN must not match, and resolution must fall through to
    the next branch rather than returning organization B's plant."""
    factory = await _factory()
    organization_a_id, plants_a = await _seed_org_with_plants(factory, plant_count=1)
    _organization_b_id, plants_b = await _seed_org_with_plants(factory, plant_count=1)

    # Simulate a corrupted/foreign default by writing it directly at the ORM
    # layer, bypassing the PATCH endpoint's own ownership validation (which
    # would normally reject this).
    async with factory() as session:
        org_a = await session.get(OrganizationRecord, organization_a_id)
        assert org_a is not None
        org_a.default_plant_id = plants_b[0]
        await session.flush()
        await session.commit()

    async with factory() as session:
        resolved = await _infer_single_plant_for_organization_in_session(
            session, organization_a_id
        )

    # Falls through to branch (c): organization A's own single plant, never
    # organization B's plant.
    assert resolved == plants_a[0]
    assert resolved != plants_b[0]
