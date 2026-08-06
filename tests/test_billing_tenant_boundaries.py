"""PR-3: cross-tenant boundary tests for ``billing.router``.

Verifies that a caller authenticated for organization B receives 404 (not
403 — same convention as PR-2, so the response does not reveal the existence
of a plant the caller has no access to) when trying to operate on organization
A's plant or bills, on every handler in the router: ``/intake-text``,
``/pending``, ``/{bill_id}/confirm`` and ``/{bill_id}/reject``.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import mplacas.core.tenancy as tenancy
import mplacas.db.session as db_session
import mplacas.billing.router as billing_router
from mplacas.billing.db_models import BillStatus, UtilityBillRecord
from mplacas.core.authorization import PlantScope
from mplacas.core.config import get_settings
from mplacas.core.jwt import encode_access_token
from mplacas.core.principal import OperationsPrincipal
from mplacas.core.security import OperationsRole
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.main import app
from mplacas.organizations.db_models import OrganizationRecord

PLANT_A = uuid.UUID("00000000-0000-0000-0000-0000000000b1")


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _seed(factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create org A (with plant A + a pending bill) and org B (no plants)."""
    async with factory() as session:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        session.add_all(
            [
                OrganizationRecord(
                    id=org_a, name="Org A", slug=f"org-a-{org_a.hex[:8]}", active=True
                ),
                OrganizationRecord(
                    id=org_b, name="Org B", slug=f"org-b-{org_b.hex[:8]}", active=True
                ),
            ]
        )
        session.add(Plant(id=PLANT_A, organization_id=org_a, name="Plant A"))
        bill = UtilityBillRecord(
            id=uuid.uuid4(),
            plant_id=PLANT_A,
            distributor="EQUATORIAL_GO",
            reference_month="2026-06",
            cycle_start=date(2026, 5, 18),
            cycle_end=date(2026, 6, 16),
            billed_days=30,
            imported_kwh=Decimal("278.000"),
            injected_kwh=Decimal("182.000"),
            compensated_kwh=Decimal("278.000"),
            credit_balance_kwh=Decimal("63.980"),
            total_amount_brl=Decimal("80.21"),
            public_lighting_brl=Decimal("30.21"),
            status=BillStatus.PENDING_REVIEW,
            source_hash="cross-tenant-fixture-hash",
        )
        session.add(bill)
        await session.flush()
        await session.commit()
        return org_a, org_b, bill.id


@pytest.fixture
def cross_tenant_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    import asyncio

    factory, engine = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(billing_router, "SessionFactory", factory)

    org_a, org_b, bill_id = asyncio.run(_seed(factory))
    token_b = encode_access_token(uuid.uuid4(), org_b, OperationsRole.ADMIN.value)

    yield org_a, org_b, bill_id, token_b

    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def test_intake_text_cross_tenant_is_not_found(cross_tenant_setup, monkeypatch) -> None:
    _, _, _, token_b = cross_tenant_setup
    client = TestClient(app)

    # Cross-tenant validation must reject the request before the bill text is
    # ever parsed, so the parser's own success/failure is irrelevant here —
    # stub it out to isolate the tenancy check being exercised.
    def fake_parse(text: str):  # pragma: no cover - should never be reached
        raise AssertionError("parser should not run before plant scope is validated")

    monkeypatch.setattr(billing_router, "parse_equatorial_bill_text", fake_parse)

    response = client.post(
        "/billing/intake-text",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "plant_id": str(PLANT_A),
            "text": "org b trying to intake a bill for org a's plant, padded",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}


def test_pending_bills_cross_tenant_is_not_found(cross_tenant_setup) -> None:
    _, _, _, token_b = cross_tenant_setup
    client = TestClient(app)

    response = client.get(
        "/billing/pending",
        headers={"Authorization": f"Bearer {token_b}"},
        params={"plant_id": str(PLANT_A)},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}


def test_confirm_bill_cross_tenant_is_not_found(cross_tenant_setup) -> None:
    """Regression: confirm no longer accepts/needs plant_id (ADR-069 § E.4) —
    the plant is derived from the bill record itself, and a caller from a
    different organization still gets 404 without ever seeing plant A."""
    _, _, bill_id, token_b = cross_tenant_setup
    client = TestClient(app)

    response = client.post(
        f"/billing/{bill_id}/confirm",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}


def test_reject_bill_cross_tenant_is_not_found(cross_tenant_setup) -> None:
    """Regression counterpart of the confirm test above, for reject."""
    _, _, bill_id, token_b = cross_tenant_setup
    client = TestClient(app)

    response = client.post(
        f"/billing/{bill_id}/reject",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}


async def _seed_two_plants(factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create org A with two plants (p1, p2) and one pending bill on p2."""
    async with factory() as session:
        org_a = uuid.uuid4()
        plant_1 = uuid.uuid4()
        plant_2 = uuid.uuid4()
        session.add(
            OrganizationRecord(
                id=org_a, name="Org A2", slug=f"org-a2-{org_a.hex[:8]}", active=True
            )
        )
        session.add(Plant(id=plant_1, organization_id=org_a, name="Plant A1"))
        session.add(Plant(id=plant_2, organization_id=org_a, name="Plant A2"))
        bill = UtilityBillRecord(
            id=uuid.uuid4(),
            plant_id=plant_2,
            distributor="EQUATORIAL_GO",
            reference_month="2026-06",
            cycle_start=date(2026, 5, 18),
            cycle_end=date(2026, 6, 16),
            billed_days=30,
            imported_kwh=Decimal("278.000"),
            injected_kwh=Decimal("182.000"),
            compensated_kwh=Decimal("278.000"),
            credit_balance_kwh=Decimal("63.980"),
            total_amount_brl=Decimal("80.21"),
            public_lighting_brl=Decimal("30.21"),
            status=BillStatus.PENDING_REVIEW,
            source_hash="two-plant-fixture-hash",
        )
        session.add(bill)
        await session.flush()
        await session.commit()
        return org_a, plant_1, plant_2, bill.id


@pytest.fixture
def two_plant_setup(monkeypatch):
    monkeypatch.setenv("MPLACAS_JWT_SECRET", "test-jwt-secret-at-least-32-bytes-long")
    get_settings.cache_clear()

    import asyncio

    factory, engine = asyncio.run(_factory())
    monkeypatch.setattr(db_session, "SessionFactory", factory)
    monkeypatch.setattr(billing_router, "SessionFactory", factory)

    org_a, plant_1, plant_2, bill_id = asyncio.run(_seed_two_plants(factory))
    token_a = encode_access_token(uuid.uuid4(), org_a, OperationsRole.ADMIN.value)

    yield org_a, plant_1, plant_2, bill_id, token_a

    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def _fake_snapshot():
    return SimpleNamespace(
        id=uuid.uuid4(),
        payload_sha256="d" * 64,
        report=SimpleNamespace(schema_version="1.0", calculation_version="0.2.0"),
    )


def test_confirm_bill_without_plant_id_succeeds_in_multi_plant_org(
    two_plant_setup, monkeypatch
) -> None:
    """This was exactly the bug ADR-069 § E.4 fixes: before, an org with 2+
    plants could not confirm a bill without also passing plant_id, because
    the plant was inferred (409) rather than derived from the bill itself."""
    org_a, plant_1, plant_2, bill_id, token_a = two_plant_setup
    client = TestClient(app)

    async def fake_materialize(session, *, bill_id, plant_id):
        return _fake_snapshot()

    monkeypatch.setattr(billing_router, "materialize_monthly_report_snapshot", fake_materialize)

    response = client.post(
        f"/billing/{bill_id}/confirm",
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed"
    # The bill stays associated with the plant it was created on (plant_2),
    # never plant_1 or any inferred/default plant.
    assert body["bill"]["plant_id"] == str(plant_2)


def test_reject_bill_without_plant_id_succeeds_in_multi_plant_org(
    two_plant_setup,
) -> None:
    org_a, plant_1, plant_2, bill_id, token_a = two_plant_setup
    client = TestClient(app)

    response = client.post(
        f"/billing/{bill_id}/reject",
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["bill"]["plant_id"] == str(plant_2)


def test_confirm_bill_outside_restricted_credential_scope_is_not_found(
    two_plant_setup,
) -> None:
    """A restricted PlantScope (e.g. a plant-scoped credential) that does not
    cover the bill's plant must get 404 — same fail-closed convention as the
    cross-organization case, but within the same organization."""
    org_a, plant_1, plant_2, bill_id, _token_a = two_plant_setup
    client = TestClient(app)

    restricted_principal = OperationsPrincipal(
        role=OperationsRole.ADMIN,
        credential_id="test:restricted-to-plant-1",
        plant_scope=PlantScope.restricted({plant_1}),
        organization_id=org_a,
    )
    app.dependency_overrides[tenancy._admin_principal] = lambda: restricted_principal
    try:
        response = client.post(f"/billing/{bill_id}/confirm")
    finally:
        app.dependency_overrides.pop(tenancy._admin_principal, None)

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}


def test_reject_bill_outside_restricted_credential_scope_is_not_found(
    two_plant_setup,
) -> None:
    org_a, plant_1, plant_2, bill_id, _token_a = two_plant_setup
    client = TestClient(app)

    restricted_principal = OperationsPrincipal(
        role=OperationsRole.ADMIN,
        credential_id="test:restricted-to-plant-1",
        plant_scope=PlantScope.restricted({plant_1}),
        organization_id=org_a,
    )
    app.dependency_overrides[tenancy._admin_principal] = lambda: restricted_principal
    try:
        response = client.post(f"/billing/{bill_id}/reject")
    finally:
        app.dependency_overrides.pop(tenancy._admin_principal, None)

    assert response.status_code == 404
    assert response.json() == {"detail": "plant not found"}
